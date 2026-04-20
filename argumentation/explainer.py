"""
Converts a resolved ArgumentationFramework into structured natural-language explanation.

No external project imports — only framework.py from within this package.
"""

from __future__ import annotations
from typing import List, Optional
from .framework import ArgumentationFramework

_DIM_LABELS = {"time": "Time", "stress": "Stress", "turns": "Turns", "cbr": "Experience"}


# ---------------------------------------------------------------------------
# Structured explainability helpers
# ---------------------------------------------------------------------------

def generate_verdict(af: ArgumentationFramework, chosen_route: dict, all_routes: List[dict]) -> str:
    """
    One-sentence bottom-line explanation of why the chosen route was recommended.
    Derived purely from accepted pro-arguments in the grounded extension.
    """
    trace = af.trace()
    rn = chosen_route["name"]

    winning_pros = sorted(
        [a for a in trace["accepted"] if a["route"] == rn and a["polarity"] == "pro"],
        key=lambda x: -x["strength"],
    )

    if not winning_pros:
        return f"{rn} was recommended based on the overall balance of route properties."

    # Top 1–2 dimensions
    top = winning_pros[:2]
    parts = []
    for a in top:
        dim = _DIM_LABELS.get(a["dimension"], a["dimension"].title())
        # Extract a short phrase from the claim
        claim = a["claim"]
        # Keep only text before first parenthesis or comma for brevity
        short = claim.split("(")[0].split(",")[0].strip().rstrip(".")
        parts.append(f"{dim.lower()}: {short}")

    if len(parts) == 1:
        return f"{rn} was recommended because {parts[0]}."
    return f"{rn} was recommended because {parts[0]}, and {parts[1]}."


def generate_counterfactual(af: ArgumentationFramework, chosen_route: dict, all_routes: List[dict]) -> str:
    """
    Identifies the closest competitor and what dimension change would flip the recommendation.
    Returns a human-readable sentence.
    """
    trace = af.trace()
    rn = chosen_route["name"]

    # For each alternative, count its rejected pro-args (they almost made it)
    alt_scores: dict = {}
    for a in trace["rejected"]:
        if a["route"] != rn and a["polarity"] == "pro":
            alt_scores.setdefault(a["route"], {"strength": 0.0, "dims": []})
            alt_scores[a["route"]]["strength"] += a.get("strength", 0.0)
            alt_scores[a["route"]]["dims"].append(a.get("dimension", ""))

    if not alt_scores:
        return "No alternative routes were competitive enough to consider switching."

    # Pick competitor with highest rejected strength
    runner_up_name = max(alt_scores, key=lambda k: alt_scores[k]["strength"])
    runner_up_info = alt_scores[runner_up_name]

    # Most common dimension that was rejected for runner-up
    dims = runner_up_info["dims"]
    dominant_dim = max(set(dims), key=dims.count) if dims else "time"
    dim_label = _DIM_LABELS.get(dominant_dim, dominant_dim.title())

    # Compare actual stats for the specific dimension
    chosen_stats = chosen_route.get("stats", {})
    chosen_profile = chosen_route.get("profile", {})
    runner_up_route = next((r for r in all_routes if r["name"] == runner_up_name), None)

    suffix = ""
    if runner_up_route:
        r_stats = runner_up_route.get("stats", {})
        r_profile = runner_up_route.get("profile", {})
        if dominant_dim == "time":
            diff = round(r_stats.get("travel_time_min", 0) - chosen_stats.get("travel_time_min", 0), 1)
            if diff < 0:
                suffix = f" ({abs(diff)} min faster)"
        elif dominant_dim == "stress":
            diff = round(r_profile.get("avg_road_stress", 0) - chosen_profile.get("avg_road_stress", 0), 2)
            if diff < 0:
                suffix = f" (lower road stress)"
        elif dominant_dim == "turns":
            diff = r_profile.get("difficult_turns", 0) - chosen_profile.get("difficult_turns", 0)
            if diff < 0:
                suffix = f" ({abs(diff)} fewer difficult turns)"

    return (
        f"If {dim_label.lower()} were weighted more heavily, "
        f"{runner_up_name} would be preferred instead{suffix}."
    )


def compute_decisiveness(af: ArgumentationFramework, chosen_route: dict, all_routes: List[dict]) -> float:
    """
    Returns a [0, 1] score representing how decisive the recommendation is.
    1.0 = chosen route has all accepted pros, no competition.
    0.0 = tied with a competitor.
    """
    trace = af.trace()
    rn = chosen_route["name"]

    def route_strength(name: str) -> float:
        return sum(
            a.get("strength", 0.0)
            for a in trace["accepted"]
            if a["route"] == name and a["polarity"] == "pro"
        )

    chosen_strength = route_strength(rn)
    alt_strengths = [route_strength(r["name"]) for r in all_routes if r["name"] != rn]

    if not alt_strengths:
        return 1.0

    best_alt = max(alt_strengths)
    total = chosen_strength + best_alt
    if total == 0:
        return 0.5

    # Margin: how much larger chosen is relative to total
    margin = (chosen_strength - best_alt) / total
    return round(max(0.0, min(1.0, 0.5 + margin)), 3)


def get_dimension_winners(all_routes: List[dict]) -> dict:
    """
    For each key dimension (time, stress, turns), return which route name wins (lowest value).
    Used to render comparison chips in the frontend.
    """
    winners: dict = {}

    # Time winner (lowest travel_time_min)
    try:
        winners["time"] = min(all_routes, key=lambda r: r.get("stats", {}).get("travel_time_min", float("inf")))["name"]
    except Exception:
        pass

    # Stress winner (lowest avg_road_stress)
    try:
        winners["stress"] = min(all_routes, key=lambda r: r.get("profile", {}).get("avg_road_stress", float("inf")))["name"]
    except Exception:
        pass

    # Turns winner (fewest difficult_turns)
    try:
        winners["turns"] = min(all_routes, key=lambda r: r.get("profile", {}).get("difficult_turns", float("inf")))["name"]
    except Exception:
        pass

    return winners


def generate_argument_explanation(
    af: ArgumentationFramework,
    chosen_route: dict,
    all_routes: List[dict],
    pref_summary: Optional[dict] = None,
) -> str:
    """
    Generate a structured markdown explanation from a computed AF.

    Sections produced:
      1. Header with route name and argumentation verdict
      2. Accepted pro-arguments (why this route was chosen)
      3. Per-alternative breakdown (why each was ruled out, citing defeated arguments)
      4. Argumentation statistics
      5. User preference profile (if pref_summary provided and sufficient data)

    The returned string uses the same markdown conventions as _template_explanation()
    in explainer.py, so the frontend requires zero changes.
    """
    trace = af.trace()
    rn = chosen_route["name"]
    lines: List[str] = []

    # ---- Header ----
    lines.append(f"**{rn}** *(Argumentation-Based Reasoning)*")

    # ---- Winning arguments ----
    winning_pros = [
        a for a in trace["accepted"]
        if a["route"] == rn and a["polarity"] == "pro"
    ]
    winning_pros.sort(key=lambda x: -x["strength"])

    if winning_pros:
        lines.append("\n**Why this route was chosen:**")
        for a in winning_pros:
            dim_label = _DIM_LABELS.get(a["dimension"], a["dimension"].title())
            lines.append(f"- {dim_label}: {a['claim']}")

    # ---- Why not alternatives ----
    alternatives = [r["name"] for r in all_routes if r["name"] != rn]
    succeeded_attacks = {atk["target_id"]: atk["attacker_id"]
                         for atk in trace["attacks"] if atk["succeeds"]}

    if alternatives:
        lines.append("\n**Why the alternatives were ruled out:**")
        for alt_name in alternatives:
            rejected_pros = [
                a for a in trace["rejected"]
                if a["route"] == alt_name and a["polarity"] == "pro"
            ]
            surviving_cons = [
                a for a in trace["accepted"]
                if a["route"] == alt_name and a["polarity"] == "con"
            ]

            if not rejected_pros and not surviving_cons:
                lines.append(
                    f"\n- **{alt_name}**: arguments were undecided — "
                    f"insufficient evidence to prefer it over {rn}."
                )
                continue

            lines.append(f"\n*{alt_name}:*")
            for a in rejected_pros:
                defeater_id = succeeded_attacks.get(a["id"])
                if defeater_id:
                    defeater = next(
                        (x for x in trace["accepted"] if x["id"] == defeater_id),
                        None,
                    )
                    reason = (
                        f" *(defeated by: {defeater['claim']})*"
                        if defeater else " *(defeated)*"
                    )
                else:
                    reason = " *(defeated)*"
                lines.append(f"  - ~~{a['claim']}~~{reason}")

            for a in surviving_cons:
                dim_label = _DIM_LABELS.get(a["dimension"], a["dimension"].title())
                lines.append(f"  - {dim_label}: {a['claim']}")

    # ---- Argumentation stats ----
    n_accepted  = len(trace["accepted"])
    n_rejected  = len(trace["rejected"])
    n_undecided = len(trace["undecided"])
    n_succeeded = sum(1 for atk in trace["attacks"] if atk["succeeds"])

    lines.append(
        f"\n**Argumentation summary:** {n_accepted} argument{'s' if n_accepted != 1 else ''} "
        f"accepted, {n_rejected} rejected, {n_undecided} undecided. "
        f"{n_succeeded} attack{'s' if n_succeeded != 1 else ''} succeeded in the grounded extension."
    )

    # ---- Preference profile ----
    if pref_summary and pref_summary.get("high_rated", 0) >= 3:
        p = pref_summary
        dominant_label = p["dominant"].replace("_", "-")
        lines.append(
            f"\n**Your Preference Profile:** Based on {p['high_rated']} highly-rated trips, "
            f"you tend to prefer {dominant_label} routes "
            f"({p['low_stress_pct']}% low-stress, {p['fast_pct']}% fast, "
            f"{p['balanced_pct']}% balanced). This recommendation aligns with that pattern."
        )

    return "\n".join(lines)


def build_ollama_prompt_from_af(
    af: ArgumentationFramework,
    chosen_route: dict,
    all_routes: List[dict],
) -> str:
    """
    Constructs a richer Ollama prompt that includes the argument trace,
    replacing the raw-stats prompt in stream_llm_explanation().
    """
    trace = af.trace()
    rn = chosen_route["name"]
    stats = chosen_route["stats"]
    profile = chosen_route["profile"]

    accepted_claims = "\n".join(
        f"  - [{a['dimension'].upper()}] {a['claim']}"
        for a in trace["accepted"]
        if a["route"] == rn and a["polarity"] == "pro"
    ) or "  (none)"

    defeated_opponent_claims = "\n".join(
        f"  - {a['route']}: {a['claim']}"
        for a in trace["rejected"]
        if a["route"] != rn and a["polarity"] == "pro"
    ) or "  (none)"

    return f"""You are a navigation assistant explaining a route recommendation to a driver.
The recommendation was produced by a formal argumentation framework (Dung grounded semantics).

Selected route: {rn}
- Distance: {stats['distance_km']} km, Time: {stats['travel_time_min']} min
- Road type: {profile.get('dominant_road_type', 'mixed')} ({profile.get('stress_label', '')})
- Difficult turns: {profile.get('difficult_turns', 0)} — {profile.get('turn_summary', '')}

Arguments that SURVIVED (accepted by grounded semantics):
{accepted_claims}

Arguments from alternatives that were DEFEATED:
{defeated_opponent_claims}

Write a 3-4 sentence conversational explanation for why {rn} was recommended. \
Reference the specific accepted arguments naturally. Do not use bullet points or headers — plain prose only."""


# ---------------------------------------------------------------------------
# Faithfulness checking
# ---------------------------------------------------------------------------

import json
import os


def _load_argument_thresholds() -> dict:
    """Load argument thresholds from kb_params.json; fall back to defaults if missing."""
    kb_path = os.path.join(os.path.dirname(__file__), "..", "data", "kb_params.json")
    try:
        with open(kb_path, "r") as fh:
            params = json.load(fh)
        return params.get("argument_thresholds", {})
    except Exception:
        return {}


def _time_strength(travel_time: float, all_times: list[float]) -> float:
    t_min, t_max = min(all_times), max(all_times)
    if t_max == t_min:
        return 0.5
    return max(0.05, (t_max - travel_time) / (t_max - t_min))


def _parse_evidence(evidence: list[str]) -> dict:
    parsed = {}
    for item in evidence:
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        parsed[key] = value
    return parsed


def check_faithfulness(af: ArgumentationFramework, routes: list) -> dict:
    """
    Verify that each accepted pro-argument is faithful to actual route statistics.

    Parameters
    ----------
    af     : computed ArgumentationFramework (af.trace() must be available)
    routes : list of route dicts, each containing at least
             route['name'], route['stats'], and route['profile']

    Returns
    -------
    {
        "score":         float,   # fraction of checked arguments that are faithful
        "total_checked": int,
        "violations":    int,
        "details":       [{"arg_id": str, "dimension": str, "faithful": bool}, ...]
    }
    """
    trace = af.trace()
    route_by_name = {r["name"]: r for r in routes}

    thresholds = _load_argument_thresholds()
    stress_ceiling = float(thresholds.get("stress_pro_ceiling", 2.0))
    turns_pro_max = int(thresholds.get("turns_pro_max_difficult", 0))
    time_pro_min_gap = float(thresholds.get("time_pro_min_gap", 0.15))
    cbr_min_similarity = float(thresholds.get("cbr_pro_min_similarity", 0.55))
    cbr_min_feedback = int(thresholds.get("cbr_pro_min_feedback", 4))
    all_times = [r["stats"]["travel_time_min"] for r in routes if "stats" in r]

    details: list = []

    for arg in trace.get("accepted", []):
        if arg.get("polarity") != "pro" or arg.get("status", "IN") != "IN":
            continue

        route = route_by_name.get(arg.get("route", ""))
        if route is None:
            continue

        dim = arg.get("dimension", "")
        stats = route.get("stats", {})
        profile = route.get("profile", {})

        if dim == "time":
            faithful = _time_strength(stats.get("travel_time_min", float("inf")), all_times) >= time_pro_min_gap
        elif dim == "stress":
            faithful = profile.get("avg_road_stress", float("inf")) <= stress_ceiling
        elif dim == "turns":
            faithful = profile.get("difficult_turns", float("inf")) <= turns_pro_max
        elif dim == "cbr":
            evidence = _parse_evidence(arg.get("evidence", []))
            similarity = float(evidence.get("similarity", 0.0))
            score = int(float(evidence.get("score", 0)))
            faithful = similarity >= cbr_min_similarity and score >= cbr_min_feedback
        else:
            # Unknown dimension — skip faithfulness check
            continue

        details.append({"arg_id": arg["id"], "dimension": dim, "faithful": faithful})

    total_checked = len(details)
    violations = sum(1 for d in details if not d["faithful"])
    score = (total_checked - violations) / total_checked if total_checked > 0 else 1.0

    return {
        "score": score,
        "total_checked": total_checked,
        "violations": violations,
        "details": details,
    }
