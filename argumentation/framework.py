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
from typing import Dict, List, Optional


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
