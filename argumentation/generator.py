"""
Argument Generator — translates route profiles and CBR cases into a populated
ArgumentationFramework ready for grounded-semantics evaluation.

No imports from knowledge_base.py or cbr.py. kb_params.json is loaded directly
so this module has zero circular-import risk.
"""

from __future__ import annotations
import json
import os
from typing import Dict, List, Tuple

from .framework import Argument, ArgumentationFramework

# ---------------------------------------------------------------------------
# KB params loader (independent of knowledge_base.py)
# ---------------------------------------------------------------------------

_PARAMS_CACHE: dict | None = None

def _load_params() -> dict:
    global _PARAMS_CACHE
    if _PARAMS_CACHE is not None:
        return _PARAMS_CACHE
    path = os.path.join(os.path.dirname(__file__), "..", "data", "kb_params.json")
    try:
        with open(path) as f:
            _PARAMS_CACHE = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # Fallback defaults mirror knowledge_base.py hardcoded values
        _PARAMS_CACHE = {
            "argument_thresholds": {
                "stress_pro_ceiling": 2.0,
                "turns_pro_max_difficult": 0,
                "time_pro_min_gap": 0.15,
                "cbr_pro_min_similarity": 0.55,
                "cbr_pro_min_feedback": 4,
                "cross_route_attack_gap": 0.20,
            },
            "attack_weights": {
                "cross_route_time": 1.0,
                "cross_route_stress": 0.90,
                "cross_route_turns": 0.85,
                "self_stress_to_time": 0.75,
                "self_turns_to_time": 0.65,
                "cbr_con_to_pros": 0.60,
                "cbr_pro_defends_cons": 0.55,
                "cbr_pro_attacks_opponent_time": 0.70,
            },
        }
    return _PARAMS_CACHE

def reload_params() -> None:
    """Call after kb_refinement writes a new kb_params.json."""
    global _PARAMS_CACHE
    _PARAMS_CACHE = None


# ---------------------------------------------------------------------------
# Normalisation helpers (pure functions — easy to unit-test)
# ---------------------------------------------------------------------------

def _time_strength(t: float, all_times: List[float]) -> float:
    """1.0 = fastest in set, 0.0 = slowest. Clamped to [0.05, 1.0]."""
    t_min, t_max = min(all_times), max(all_times)
    if t_max == t_min:
        return 0.5
    return round(max(0.05, (t_max - t) / (t_max - t_min)), 3)


def _stress_strength(s: float) -> float:
    """1.0 = zero stress, 0.0 = max stress (5.0). Clamped to [0.0, 1.0]."""
    return round(max(0.0, min(1.0, 1.0 - s / 5.0)), 3)


def _turns_strength(difficult: int, moderate: int, max_difficult: int) -> float:
    """1.0 = no turns, lower = more turns. Weighted sum normalised."""
    burden = difficult + 0.5 * moderate
    cap = max(max_difficult + 0.5 * (moderate + 1), 1.0)
    return round(max(0.0, min(1.0, 1.0 - burden / cap)), 3)


def _cbr_strength(cases: List[Tuple[float, dict]], preferred_type: str,
                  min_sim: float, min_score: int) -> Tuple[float, dict | None]:
    """
    Returns (strength, best_case) for the best supporting CBR case.
    strength 0.0 and None if no matching case found.
    """
    matching = [
        (sim, c) for sim, c in cases
        if c.get("preferred_route_type") == preferred_type
        and c.get("feedback_score", 0) >= min_score
        and sim >= min_sim
    ]
    if not matching:
        return 0.0, None
    best_sim, best_case = max(matching, key=lambda x: x[0])
    return round(min(0.95, best_sim), 3), best_case


# ---------------------------------------------------------------------------
# Argument factory
# ---------------------------------------------------------------------------

def _slug(route_name: str) -> str:
    return route_name.lower().replace(" ", "_")


def _make_arguments(
    route: dict,
    all_routes: List[dict],
    cbr_cases: List[Tuple[float, dict]],
    params: dict,
) -> List[Argument]:
    """Generate up to 8 arguments (2 per dimension) for one route."""
    thresholds = params["argument_thresholds"]
    rn = route["name"]
    slug = _slug(rn)
    prof = route["profile"]
    stats = route["stats"]

    t = stats["travel_time_min"]
    s = prof.get("avg_road_stress", 2.0)
    diff_turns = prof.get("difficult_turns", 0)
    mod_turns = prof.get("moderate_turns", 0)
    dom_road = prof.get("dominant_road_type", "mixed")
    stress_label = prof.get("stress_label", "")
    turn_summary = prof.get("turn_summary", "")

    all_times = [r["stats"]["travel_time_min"] for r in all_routes]
    max_diff = max(r["profile"].get("difficult_turns", 0) for r in all_routes)

    t_str = _time_strength(t, all_times)
    s_str = _stress_strength(s)
    tr_str = _turns_strength(diff_turns, mod_turns, max_diff)

    args: List[Argument] = []

    # ---- TIME ----
    time_gap = thresholds["time_pro_min_gap"]
    fastest_time = min(all_times)
    slowest_time = max(all_times)
    if t_str >= time_gap:
        args.append(Argument(
            id=f"{slug}:time:pro",
            route=rn, dimension="time", polarity="pro",
            claim=(
                f"{rn} is time-efficient at {t} min"
                + (f" — {round((t - fastest_time) * 60)} sec behind the fastest option."
                   if t > fastest_time else " — the fastest available option.")
            ),
            strength=t_str,
            evidence=[f"travel_time={t}min",
                      f"range=[{fastest_time}, {slowest_time}]min"],
        ))
    else:
        args.append(Argument(
            id=f"{slug}:time:con",
            route=rn, dimension="time", polarity="con",
            claim=(
                f"{rn} takes {t} min — {round(t - fastest_time, 1)} min slower "
                f"than the fastest option ({fastest_time} min)."
            ),
            strength=round(max(0.1, 1.0 - t_str), 3),
            evidence=[f"travel_time={t}min, fastest={fastest_time}min"],
        ))

    # ---- STRESS ----
    ceiling = thresholds["stress_pro_ceiling"]
    if s <= ceiling:
        args.append(Argument(
            id=f"{slug}:stress:pro",
            route=rn, dimension="stress", polarity="pro",
            claim=(
                f"{rn} uses {stress_label} roads (avg stress {s:.1f}/5, "
                f"dominated by {dom_road}) — within the safe ceiling of {ceiling}/5."
            ),
            strength=max(0.15, s_str),
            evidence=[f"avg_stress={s}", f"dominant={dom_road}",
                      f"ceiling={ceiling}"],
        ))
    else:
        args.append(Argument(
            id=f"{slug}:stress:con",
            route=rn, dimension="stress", polarity="con",
            claim=(
                f"{rn} uses {stress_label} roads (avg stress {s:.1f}/5, "
                f"dominated by {dom_road}) — exceeds the safe ceiling of {ceiling}/5."
            ),
            strength=round(max(0.15, 1.0 - s_str), 3),
            evidence=[f"avg_stress={s}", f"ceiling={ceiling}"],
        ))

    # ---- TURNS ----
    max_turns_pro = thresholds["turns_pro_max_difficult"]
    if diff_turns <= max_turns_pro:
        args.append(Argument(
            id=f"{slug}:turns:pro",
            route=rn, dimension="turns", polarity="pro",
            claim=(
                f"{rn} requires no difficult turns — {turn_summary or 'clean navigation'}."
            ),
            strength=max(0.3, tr_str),
            evidence=[f"difficult_turns={diff_turns}",
                      f"moderate_turns={mod_turns}"],
        ))
    else:
        args.append(Argument(
            id=f"{slug}:turns:con",
            route=rn, dimension="turns", polarity="con",
            claim=(
                f"{rn} requires {diff_turns} difficult turn{'s' if diff_turns != 1 else ''}"
                + (f" and {mod_turns} moderate" if mod_turns else "")
                + f" — {turn_summary}."
            ),
            strength=round(max(0.15, 1.0 - tr_str), 3),
            evidence=[f"difficult_turns={diff_turns}",
                      f"moderate_turns={mod_turns}"],
        ))

    # ---- CBR ----
    min_sim = thresholds["cbr_pro_min_similarity"]
    min_score = thresholds["cbr_pro_min_feedback"]
    cbr_str, best_case = _cbr_strength(cbr_cases, rn, min_sim, min_score)

    if cbr_str > 0 and best_case:
        args.append(Argument(
            id=f"{slug}:cbr:pro",
            route=rn, dimension="cbr", polarity="pro",
            claim=(
                f"Past experience supports {rn}: a similar trip from "
                f"{best_case['origin_name']} to {best_case['dest_name']} "
                f"was rated {best_case['feedback_score']}/5 "
                f"(CBR similarity {cbr_str:.2f})."
            ),
            strength=cbr_str,
            evidence=[f"case_id={best_case['id']}",
                      f"score={best_case['feedback_score']}",
                      f"similarity={cbr_str}"],
        ))

    # CBR con — cases that went poorly for this route type
    poor = [
        (sim, c) for sim, c in cbr_cases
        if c.get("preferred_route_type") == rn
        and c.get("feedback_score", 3) <= 2
        and sim >= min_sim
    ]
    if poor:
        worst_sim, worst = max(poor, key=lambda x: x[0])
        args.append(Argument(
            id=f"{slug}:cbr:con",
            route=rn, dimension="cbr", polarity="con",
            claim=(
                f"Past experience warns against {rn}: a similar trip was rated "
                f"{worst['feedback_score']}/5 (similarity {round(worst_sim, 2):.2f})."
            ),
            strength=0.6,
            evidence=[f"case_id={worst['id']}",
                      f"score={worst['feedback_score']}"],
        ))

    return args


# ---------------------------------------------------------------------------
# Attack builder
# ---------------------------------------------------------------------------

def _build_attacks(af: ArgumentationFramework, route_names: List[str],
                   weights: dict) -> None:
    slugs = [_slug(rn) for rn in route_names]
    params = _load_params()
    gap = params["argument_thresholds"]["cross_route_attack_gap"]

    for slug in slugs:
        # Self-undermining: stress/turns cons attack time pro of same route
        if f"{slug}:stress:con" in af.arguments and f"{slug}:time:pro" in af.arguments:
            af.add_attack(f"{slug}:stress:con", f"{slug}:time:pro",
                          kind="self_undermining",
                          weight=weights["self_stress_to_time"])

        if f"{slug}:turns:con" in af.arguments and f"{slug}:time:pro" in af.arguments:
            af.add_attack(f"{slug}:turns:con", f"{slug}:time:pro",
                          kind="self_undermining",
                          weight=weights["self_turns_to_time"])

        # CBR con attacks all pros of same route
        if f"{slug}:cbr:con" in af.arguments:
            for dim in ["time:pro", "stress:pro", "turns:pro"]:
                if f"{slug}:{dim}" in af.arguments:
                    af.add_attack(f"{slug}:cbr:con", f"{slug}:{dim}",
                                  kind="cbr_rebuttal",
                                  weight=weights["cbr_con_to_pros"])

        # CBR pro defends own cons (positive evidence redeems concerns)
        if f"{slug}:cbr:pro" in af.arguments:
            for dim in ["stress:con", "turns:con", "time:con"]:
                if f"{slug}:{dim}" in af.arguments:
                    af.add_attack(f"{slug}:cbr:pro", f"{slug}:{dim}",
                                  kind="defense",
                                  weight=weights["cbr_pro_defends_cons"])

    # Cross-route: on each dimension, the stronger route attacks the weaker
    for dim, wkey in [("time", "cross_route_time"),
                      ("stress", "cross_route_stress"),
                      ("turns", "cross_route_turns")]:
        pro_args = [
            (s, af.arguments[f"{s}:{dim}:pro"])
            for s in slugs
            if f"{s}:{dim}:pro" in af.arguments
        ]
        pro_args.sort(key=lambda x: -x[1].strength)

        for i, (stronger_slug, stronger_arg) in enumerate(pro_args):
            for weaker_slug, weaker_arg in pro_args[i + 1:]:
                if stronger_arg.strength - weaker_arg.strength >= gap:
                    af.add_attack(f"{stronger_slug}:{dim}:pro",
                                  f"{weaker_slug}:{dim}:pro",
                                  kind="cross_route",
                                  weight=weights[wkey])

    # CBR pro attacks opponent's time pro (user history overrides raw speed)
    for slug in slugs:
        cbr_pro_id = f"{slug}:cbr:pro"
        if cbr_pro_id not in af.arguments:
            continue
        cbr_str = af.arguments[cbr_pro_id].strength
        for other_slug in slugs:
            if other_slug == slug:
                continue
            opp_time_id = f"{other_slug}:time:pro"
            if opp_time_id not in af.arguments:
                continue
            opp_str = af.arguments[opp_time_id].strength
            if cbr_str > 0.55 and opp_str < cbr_str * 1.25:
                af.add_attack(cbr_pro_id, opp_time_id,
                              kind="cbr_rebuttal",
                              weight=weights["cbr_pro_attacks_opponent_time"])


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def build_argumentation_framework(
    routes: List[dict],
    cbr_cases_per_route: Dict[str, List[Tuple[float, dict]]],
) -> ArgumentationFramework:
    """
    Build and return an ArgumentationFramework for the given routes.

    Args:
        routes:               List of route dicts from router.generate_candidate_routes()
        cbr_cases_per_route:  {route_name: [(similarity, case_dict), ...]}
                              One entry per route, retrieved externally to keep
                              this module free of CBR imports.

    Returns:
        A populated ArgumentationFramework (grounded semantics NOT yet computed —
        call af.compute_grounded_extension() or af.recommend() before querying).
    """
    params = _load_params()
    af = ArgumentationFramework()

    for route in routes:
        rn = route["name"]
        cases = cbr_cases_per_route.get(rn, [])
        for arg in _make_arguments(route, routes, cases, params):
            af.add_argument(arg)

    _build_attacks(af, [r["name"] for r in routes], params["attack_weights"])
    return af
