"""
Dung-style Abstract Argumentation Framework with strength-weighted grounded semantics.

Reference: Dung, P.M. (1995). On the acceptability of arguments and its fundamental role
in nonmonotonic reasoning, logic programming and n-person games.
Artificial Intelligence, 77(2), 321-357.

Modification: Standard Dung grounded semantics is augmented with argument strength
values so that attack success depends on the relative strength ratio between attacker
and target — a stronger target can resist a weaker attacker.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set


@dataclass
class Argument:
    """
    A single argument about a route's quality on one dimension.

    id:        Unique identifier, e.g. "fastest:time:pro"
    route:     Route name this argument is about, e.g. "Fastest Route"
    dimension: One of "time" | "stress" | "turns" | "cbr"
    polarity:  "pro" (supports recommending this route) or "con" (argues against)
    claim:     Human-readable claim text shown in the explanation
    strength:  Normalised [0, 1] — how strong the evidence behind this argument is
    evidence:  List of raw metric strings used to justify this argument
    status:    Set by grounded semantics: "IN" | "OUT" | "UNDECIDED"
    """
    id: str
    route: str
    dimension: str
    polarity: str
    claim: str
    strength: float
    evidence: List[str] = field(default_factory=list)
    status: str = field(default="UNDECIDED", init=False)


@dataclass
class Attack:
    """
    A directed attack from one argument to another.

    attacker_id:  id of the attacking Argument
    target_id:    id of the argument being attacked
    kind:         "cross_route" | "self_undermining" | "cbr_rebuttal" | "defense"
    weight:       [0, 1] — scales the attacker's effective strength for this attack
    succeeds:     Filled in by compute_grounded_extension()
    """
    attacker_id: str
    target_id: str
    kind: str
    weight: float
    succeeds: bool = field(default=False, init=False)


class ArgumentationFramework:
    """
    Dung Abstract Argumentation Framework (AF = <AR, attacks>) with strength-weighted
    grounded semantics.

    Grounded semantics (standard): computes the least fixed point of the characteristic
    function F(S) = {a | S defends a}, giving a unique, skeptically justified extension.

    Strength modification: attack (A → B) succeeds only if
        A.strength * attack.weight  >  B.strength * 0.5
    meaning a target with twice the strength of an attacker resists the attack even if
    the attacker is IN. This prevents trivially weak arguments from defeating strong ones.
    """

    def __init__(self) -> None:
        self.arguments: Dict[str, Argument] = {}
        self.attacks: List[Attack] = []

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------

    def add_argument(self, arg: Argument) -> None:
        self.arguments[arg.id] = arg

    def add_attack(self, attacker_id: str, target_id: str,
                   kind: str = "cross_route", weight: float = 0.7) -> None:
        if attacker_id in self.arguments and target_id in self.arguments:
            self.attacks.append(Attack(attacker_id, target_id, kind, weight))

    # ------------------------------------------------------------------
    # Grounded semantics
    # ------------------------------------------------------------------

    def _incoming(self, arg_id: str) -> List[Attack]:
        return [a for a in self.attacks if a.target_id == arg_id]

    def compute_grounded_extension(self) -> Dict[str, str]:
        """
        Iterative labelling algorithm for grounded semantics.

        Algorithm:
          1. Initialise every argument as UNDECIDED.
          2. Repeat until fixpoint:
             a. Mark IN  — any UNDECIDED argument all of whose attackers are OUT.
             b. Mark OUT — any UNDECIDED argument attacked by an IN argument
                           whose effective strength exceeds the target's resistance.
          3. Return mapping {arg_id: status}.

        Termination is guaranteed because the state can only progress
        UNDECIDED → IN or UNDECIDED → OUT, never backward, and |AR| is finite.
        Worst-case iterations: O(|AR|).
        """
        for a in self.arguments.values():
            a.status = "UNDECIDED"

        changed = True
        iterations = 0
        max_iterations = len(self.arguments) * 2 + 10

        while changed and iterations < max_iterations:
            changed = False
            iterations += 1

            for arg_id, arg in self.arguments.items():
                if arg.status != "UNDECIDED":
                    continue

                incoming = self._incoming(arg_id)

                # No attackers → unconditionally IN
                if not incoming:
                    arg.status = "IN"
                    changed = True
                    continue

                # Check if any IN attacker is strong enough to defeat this argument
                defeated = False
                for atk in incoming:
                    attacker = self.arguments.get(atk.attacker_id)
                    if attacker and attacker.status == "IN":
                        if attacker.strength * atk.weight > arg.strength * 0.5:
                            defeated = True
                            atk.succeeds = True
                            break

                if defeated:
                    arg.status = "OUT"
                    changed = True
                    continue

                # IN if every attacker is OUT (all attacks are neutralised)
                if all(self.arguments[a.attacker_id].status == "OUT"
                       for a in incoming
                       if a.attacker_id in self.arguments):
                    arg.status = "IN"
                    changed = True

        return {aid: a.status for aid, a in self.arguments.items()}

    # ------------------------------------------------------------------
    # Querying the resolved framework
    # ------------------------------------------------------------------

    def recommend(self) -> Optional[str]:
        """
        Returns the route name whose IN pro-arguments have the highest total strength.
        Returns None if no route has any accepted pro-arguments.
        """
        self.compute_grounded_extension()
        scores: Dict[str, float] = {}
        for a in self.arguments.values():
            if a.polarity == "pro" and a.status == "IN":
                scores[a.route] = scores.get(a.route, 0.0) + a.strength
        return max(scores, key=scores.get) if scores else None

    def recommend_with_routes(self, routes: list[dict]) -> Optional[str]:
        """
        Returns the AF recommendation, but avoids selecting a strictly dominated
        route when an undominated AF-supported alternative is available.

        This keeps the grounded-semantics scoring intact while adding a final
        Pareto sanity check over the concrete route metrics shown to the user.
        """
        self.compute_grounded_extension()
        scores: Dict[str, float] = {}
        for a in self.arguments.values():
            if a.polarity == "pro" and a.status == "IN":
                scores[a.route] = scores.get(a.route, 0.0) + a.strength

        if not scores:
            return None

        route_by_name = {r["name"]: r for r in routes}
        ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
        for route_name, _ in ranked:
            route = route_by_name.get(route_name)
            if route is None:
                continue
            if not _is_pareto_dominated(route, routes):
                return route_name

        return ranked[0][0]

    def trace(self) -> dict:
        """
        Returns a fully serialisable trace of the resolved framework for use by the
        explanation generator and the /api/argue endpoint.

        Structure:
        {
            "accepted":  [arg_dict, ...],   # status == IN
            "rejected":  [arg_dict, ...],   # status == OUT
            "undecided": [arg_dict, ...],   # status == UNDECIDED
            "attacks":   [attack_dict, ...]
        }
        """
        self.compute_grounded_extension()
        return {
            "accepted":  [_arg_dict(a) for a in self.arguments.values() if a.status == "IN"],
            "rejected":  [_arg_dict(a) for a in self.arguments.values() if a.status == "OUT"],
            "undecided": [_arg_dict(a) for a in self.arguments.values() if a.status == "UNDECIDED"],
            "attacks": [
                {
                    "attacker_id": atk.attacker_id,
                    "target_id":   atk.target_id,
                    "kind":        atk.kind,
                    "weight":      round(atk.weight, 3),
                    "succeeds":    atk.succeeds,
                }
                for atk in self.attacks
                if atk.attacker_id in self.arguments and atk.target_id in self.arguments
            ],
        }

    # ------------------------------------------------------------------
    # Preferred extensions (maximal admissible sets)
    # ------------------------------------------------------------------

    def _is_conflict_free(self, arg_ids: Set[str]) -> bool:
        """Return True if no argument in arg_ids attacks another argument in arg_ids
        with sufficient strength."""
        for atk in self.attacks:
            if atk.attacker_id in arg_ids and atk.target_id in arg_ids:
                attacker = self.arguments[atk.attacker_id]
                target = self.arguments[atk.target_id]
                if attacker.strength * atk.weight > target.strength * 0.5:
                    return False
        return True

    def _defends(self, s: Set[str], arg_id: str) -> bool:
        """Return True if set s defends arg_id: for every attacker b of arg_id,
        some c in s attacks b with sufficient strength."""
        for atk in self.attacks:
            if atk.target_id != arg_id:
                continue
            b_id = atk.attacker_id
            b = self.arguments.get(b_id)
            if b is None:
                continue
            # Check if any c in s counter-attacks b sufficiently
            defended = False
            for counter_atk in self.attacks:
                if counter_atk.attacker_id in s and counter_atk.target_id == b_id:
                    c = self.arguments[counter_atk.attacker_id]
                    if c.strength * counter_atk.weight > b.strength * 0.5:
                        defended = True
                        break
            if not defended:
                return False
        return True

    def _is_admissible(self, arg_ids: Set[str]) -> bool:
        """Return True if arg_ids is conflict-free and defends all its members."""
        if not self._is_conflict_free(arg_ids):
            return False
        for a_id in arg_ids:
            if not self._defends(arg_ids, a_id):
                return False
        return True

    def compute_preferred_extensions(self) -> list:
        """
        Compute all maximal admissible sets (preferred extensions).

        Uses exhaustive enumeration for AFs with ≤20 arguments.
        Falls back to returning the grounded extension as a single-element list
        for larger AFs.

        Returns a list of sets, each set containing argument ids.
        """
        all_ids = list(self.arguments.keys())
        n = len(all_ids)

        if n > 20:
            # Fall back to grounded extension
            self.compute_grounded_extension()
            grounded = frozenset(
                aid for aid, a in self.arguments.items() if a.status == "IN"
            )
            return [grounded]

        # Enumerate all 2^n subsets and collect admissible ones
        admissible_sets: List[Set[str]] = []
        for mask in range(1 << n):
            subset: Set[str] = set()
            for i in range(n):
                if mask & (1 << i):
                    subset.add(all_ids[i])
            if self._is_admissible(subset):
                admissible_sets.append(subset)

        # Keep only maximal admissible sets (no proper superset is also admissible)
        preferred: List[Set[str]] = []
        for s in admissible_sets:
            if not any(s < other for other in admissible_sets):
                preferred.append(frozenset(s))

        # Deduplicate
        seen = set()
        result = []
        for s in preferred:
            if s not in seen:
                seen.add(s)
                result.append(s)

        return result if result else [frozenset()]

    # ------------------------------------------------------------------
    # Stable extensions
    # ------------------------------------------------------------------

    def compute_stable_extensions(self) -> list:
        """
        Compute all stable extensions.

        S is stable if it is conflict-free AND every argument outside S is
        attacked by some argument in S with sufficient strength.

        Uses exhaustive enumeration for AFs with ≤20 arguments.
        Returns an empty list for larger AFs.

        Returns a list of frozensets of argument ids.
        """
        all_ids = list(self.arguments.keys())
        n = len(all_ids)

        if n > 20:
            return []

        stable: List[frozenset] = []
        for mask in range(1 << n):
            subset: Set[str] = set()
            for i in range(n):
                if mask & (1 << i):
                    subset.add(all_ids[i])

            if not self._is_conflict_free(subset):
                continue

            # Every argument outside S must be attacked from S with sufficient strength
            outside = set(all_ids) - subset
            all_attacked = True
            for out_id in outside:
                attacked = False
                for atk in self.attacks:
                    if atk.attacker_id in subset and atk.target_id == out_id:
                        attacker = self.arguments[atk.attacker_id]
                        target = self.arguments[out_id]
                        if attacker.strength * atk.weight > target.strength * 0.5:
                            attacked = True
                            break
                if not attacked:
                    all_attacked = False
                    break

            if all_attacked:
                stable.append(frozenset(subset))

        return stable

    # ------------------------------------------------------------------
    # Compare semantics
    # ------------------------------------------------------------------

    def _rec_from_set(self, in_set: Set[str]) -> Optional[str]:
        """Pick the route with the highest total pro-argument strength
        from the given set of accepted argument ids."""
        scores: Dict[str, float] = {}
        for aid in in_set:
            a = self.arguments.get(aid)
            if a and a.polarity == "pro":
                scores[a.route] = scores.get(a.route, 0.0) + a.strength
        return max(scores, key=scores.get) if scores else None

    def compare_semantics(self) -> dict:
        """
        Run grounded, preferred, and stable semantics and return a summary dict.

        Returns:
        {
            "grounded": {"extension": [...], "recommendation": str|None},
            "preferred": {"extensions": [[...], ...], "recommendations": [...], "count": int},
            "stable":    {"extensions": [[...], ...], "recommendations": [...], "count": int},
            "all_semantics_agree": bool,
            "recommendations": {
                "grounded": str|None,
                "preferred": str|None,
                "stable": str|None,
            }
        }
        """
        # Grounded
        self.compute_grounded_extension()
        grounded_set = frozenset(
            aid for aid, a in self.arguments.items() if a.status == "IN"
        )
        grounded_rec = self._rec_from_set(grounded_set)

        # Preferred
        preferred_exts = self.compute_preferred_extensions()
        preferred_recs = [self._rec_from_set(ext) for ext in preferred_exts]
        preferred_rec = preferred_recs[0] if preferred_recs else None
        # Consensus preferred recommendation (all agree)
        if preferred_recs and len(set(preferred_recs)) == 1:
            preferred_rec = preferred_recs[0]
        else:
            preferred_rec = None

        # Stable
        stable_exts = self.compute_stable_extensions()
        stable_recs = [self._rec_from_set(ext) for ext in stable_exts]
        stable_rec = stable_recs[0] if stable_recs else None
        if stable_recs and len(set(stable_recs)) == 1:
            stable_rec = stable_recs[0]
        else:
            stable_rec = None if not stable_recs else stable_recs[0]

        all_recs = {grounded_rec, preferred_rec, stable_rec}
        all_semantics_agree = len(all_recs) == 1

        return {
            "grounded": {
                "extension": sorted(grounded_set),
                "recommendation": grounded_rec,
            },
            "preferred": {
                "extensions": [sorted(ext) for ext in preferred_exts],
                "recommendations": preferred_recs,
                "count": len(preferred_exts),
            },
            "stable": {
                "extensions": [sorted(ext) for ext in stable_exts],
                "recommendations": stable_recs,
                "count": len(stable_exts),
            },
            "all_semantics_agree": all_semantics_agree,
            "recommendations": {
                "grounded": grounded_rec,
                "preferred": preferred_rec,
                "stable": stable_rec,
            },
        }

    def to_dict(self) -> dict:
        """Full serialisable representation for the /api/argue response."""
        t = self.trace()
        all_args = t["accepted"] + t["rejected"] + t["undecided"]
        grounded = [a["id"] for a in t["accepted"]]
        return {
            "arguments": all_args,
            "attacks": t["attacks"],
            "grounded_extension": grounded,
            "counts": {
                "accepted": len(t["accepted"]),
                "rejected": len(t["rejected"]),
                "undecided": len(t["undecided"]),
                "attacks_succeeded": sum(1 for atk in t["attacks"] if atk["succeeds"]),
            },
        }


# ------------------------------------------------------------------
# Internal helper
# ------------------------------------------------------------------

def _arg_dict(a: Argument) -> dict:
    return {
        "id":        a.id,
        "route":     a.route,
        "dimension": a.dimension,
        "polarity":  a.polarity,
        "claim":     a.claim,
        "strength":  round(a.strength, 3),
        "evidence":  a.evidence,
        "status":    a.status,
    }


def _is_pareto_dominated(route: dict, others: list[dict]) -> bool:
    """Return True if `route` is strictly dominated on time, stress, and turns."""
    t = route["stats"]["travel_time_min"]
    s = route["profile"].get("avg_road_stress", 0)
    d = route["profile"].get("difficult_turns", 0)

    for other in others:
        if other["name"] == route["name"]:
            continue
        ot = other["stats"]["travel_time_min"]
        os_ = other["profile"].get("avg_road_stress", 0)
        od = other["profile"].get("difficult_turns", 0)
        if ot <= t and os_ <= s and od <= d and (ot < t or os_ < s or od < d):
            return True
    return False
