"""
Converts a resolved ArgumentationFramework into structured natural-language explanation.

No external project imports — only framework.py from within this package.
"""

from __future__ import annotations
from typing import List, Optional
from .framework import ArgumentationFramework

_DIM_LABELS = {"time": "Time", "stress": "Stress", "turns": "Turns", "cbr": "Experience"}


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
