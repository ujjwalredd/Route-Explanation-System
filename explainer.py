import os
from cbr import retrieve_similar_cases, get_preference_summary

try:
    from argumentation import (
        build_argumentation_framework,
        generate_argument_explanation,
        build_ollama_prompt_from_af,
    )
    _ARGUMENTATION_AVAILABLE = True
except ImportError:
    _ARGUMENTATION_AVAILABLE = False

OLLAMA_MODEL = "llama3.2:latest"

PREF_MAP = {
    "Fastest Route": "fast",
    "Easiest Route": "low_stress",
    "Balanced Route": "balanced",
}

PREF_LABELS = {
    "fast": "speed-first routes",
    "low_stress": "quieter, lower-stress routes",
    "balanced": "balanced trade-off routes",
}


def _get_similar_cases(chosen_route):
    profile = chosen_route["profile"]
    stats = chosen_route["stats"]
    target_pref = PREF_MAP.get(chosen_route["name"], "balanced")
    return retrieve_similar_cases(
        {**profile, "travel_time_min": stats["travel_time_min"], "distance_km": stats["distance_km"]},
        target_preference=target_pref,
        top_k=2,
    )


def _get_cbr_cases_for_all_routes(all_routes):
    """Retrieve similar cases for every route (needed by the argumentation generator)."""
    result = {}
    for route in all_routes:
        profile = route["profile"]
        stats = route["stats"]
        pref = PREF_MAP.get(route["name"], "balanced")
        result[route["name"]] = retrieve_similar_cases(
            {**profile,
             "travel_time_min": stats["travel_time_min"],
             "distance_km": stats["distance_km"]},
            target_preference=pref,
            top_k=3,
        )
    return result


def explain_route(chosen_route, all_routes):
    """
    Primary explanation entry point.
    Uses argumentation-based reasoning when available, falls back to template.
    """
    if _ARGUMENTATION_AVAILABLE:
        try:
            return _argumentation_explanation(chosen_route, all_routes)
        except Exception:
            pass  # silent fallback — never break the UI
        return _template_explanation(chosen_route, all_routes, _get_similar_cases(chosen_route))


    def explain_route_template(chosen_route, all_routes):
        """Deterministic template-only explanation (no LLM, no argumentation)."""
        return _template_explanation(chosen_route, all_routes, _get_similar_cases(chosen_route))


def _argumentation_explanation(chosen_route, all_routes):
    """Build AF, run grounded semantics, generate NL explanation."""
    cbr_per_route = _get_cbr_cases_for_all_routes(all_routes)
    af = build_argumentation_framework(all_routes, cbr_per_route)
    af.compute_grounded_extension()
    pref = get_preference_summary()
    return generate_argument_explanation(af, chosen_route, all_routes, pref_summary=pref)


def _fallback_prompt(chosen_route, all_routes, alt_lines, cbr_lines):
    stats = chosen_route["stats"]
    profile = chosen_route["profile"]
    return (
        f"You are a navigation assistant explaining a route recommendation to a driver.\n\n"
        f"Selected route: {chosen_route['name']}\n"
        f"- Distance: {stats['distance_km']} km, Time: {stats['travel_time_min']} min\n"
        f"- Road type: {profile.get('dominant_road_type', 'mixed')} ({profile.get('stress_label', '')})\n"
        f"- Difficult turns: {profile.get('difficult_turns', 0)}, "
        f"Turn summary: {profile.get('turn_summary', '')}\n\n"
        f"Alternatives considered:\n{alt_lines}\n\n"
        f"Relevant past cases (Case-Based Reasoning):\n{cbr_lines}\n\n"
        f"Write a 3-4 sentence explanation for why this route was chosen. Be direct, "
        f"human, and practical. Do not include emojis. Use short paragraphs; no markdown headers."
    )


def stream_llm_explanation(chosen_route, all_routes):
    similar_cases = _get_similar_cases(chosen_route)
    try:
        import ollama

        profile = chosen_route["profile"]
        stats = chosen_route["stats"]

        alt_lines = "\n".join(
            f"  - {r['name']}: {r['stats']['travel_time_min']} min, "
            f"{r['profile'].get('difficult_turns', 0)} difficult turns, "
            f"{r['profile'].get('stress_label', '')}"
            for r in all_routes if r["name"] != chosen_route["name"]
        )

        cbr_lines = "\n".join(
            f"  - {c['origin_name']} to {c['dest_name']}: {c['reason']} (rated {c['feedback_score']}/5)"
            for _, c in similar_cases
        ) or "  No directly matching past cases."

        if _ARGUMENTATION_AVAILABLE:
            try:
                cbr_per_route = _get_cbr_cases_for_all_routes(all_routes)
                af = build_argumentation_framework(all_routes, cbr_per_route)
                af.compute_grounded_extension()
                prompt = build_ollama_prompt_from_af(af, chosen_route, all_routes)
            except Exception:
                prompt = _fallback_prompt(chosen_route, all_routes, alt_lines, cbr_lines)
        else:
            prompt = _fallback_prompt(chosen_route, all_routes, alt_lines, cbr_lines)

        stream = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt}],
            stream=True,
        )
        for chunk in stream:
            token = chunk["message"]["content"]
            if token:
                yield token

    except Exception as e:
        yield f"**Ollama Error:** Unable to generate AI explanation.\n\n`{e}`\n\nPlease ensure Ollama is running and the model is pulled (`ollama pull {OLLAMA_MODEL}`)."


def _template_explanation(chosen_route, all_routes, similar_cases):
    profile = chosen_route["profile"]
    stats = chosen_route["stats"]
    name = chosen_route["name"]
    difficult = profile.get("difficult_turns", 0)
    dominant = profile.get("dominant_road_type", "mixed")
    turn_summary = profile.get("turn_summary", "")

    lines = []

    lines.append(
        f"**{name}** was recommended for this trip "
        f"({stats['distance_km']} km, ~{stats['travel_time_min']} min)."
    )

    lines.append(
        f"\n**Road Character:** This route runs primarily along {dominant} roads, "
        f"which are generally {profile.get('stress_label', 'mixed roads')}. "
        f"The average road stress score is {profile.get('avg_road_stress', 0):.1f}/5, "
        f"meaning {'the roads are comfortable and low-pressure for the driver' if profile.get('avg_road_stress', 3) < 2.5 else 'the roads involve some busier sections but are manageable'}."
    )

    if difficult == 0:
        lines.append(
            f"\n**Turn Complexity:** {turn_summary.capitalize() if turn_summary else 'No difficult turns'}. "
            f"There are no sharp or unprotected turns required — the driver can navigate this route "
            f"with confidence, without needing to cut across traffic or make tight maneuvers."
        )
    else:
        lines.append(
            f"\n**Turn Complexity:** The route involves {turn_summary}. "
            f"These are inherent to this corridor and cannot be avoided, "
            f"but the rest of the route compensates with simpler navigation."
        )

    alternatives = [r for r in all_routes if r["name"] != name]
    if alternatives:
        lines.append("\n**Why not the alternatives?**")
        for alt in alternatives:
            ap = alt["profile"]
            reasons = []

            time_diff = round(alt["stats"]["travel_time_min"] - stats["travel_time_min"], 1)
            if time_diff > 0.5:
                reasons.append(f"{time_diff} min slower")
            elif time_diff < -0.5:
                reasons.append(f"{abs(time_diff)} min faster, but with trade-offs below")

            turn_diff = ap.get("difficult_turns", 0) - difficult
            if turn_diff > 0:
                reasons.append(f"{turn_diff} more difficult turn{'s' if turn_diff != 1 else ''}")
            elif turn_diff < 0:
                reasons.append(f"{abs(turn_diff)} fewer difficult turn{'s' if abs(turn_diff) != 1 else ''}")

            stress_diff = ap.get("avg_road_stress", 2) - profile.get("avg_road_stress", 2)
            if stress_diff > 0.5:
                reasons.append("higher road stress")
            elif stress_diff < -0.5:
                reasons.append("lower road stress")

            if reasons:
                lines.append(f"- **{alt['name']}**: {', '.join(reasons)}.")
            else:
                lines.append(f"- **{alt['name']}**: similar characteristics — selected route is preferred based on objectives.")

    if similar_cases:
        lines.append("\n**From Past Experience (Case-Based Reasoning):**")
        for score, case in similar_cases:
            lines.append(
                f"- A similar trip from _{case['origin_name']}_ to _{case['dest_name']}_ "
                f"previously used the {case['preferred_route_type']} because "
                f"\"{case['reason']}\" — rated {case['feedback_score']}/5 "
                f"(similarity: {score:.2f})."
            )

    pref = get_preference_summary()
    if pref and pref["high_rated"] >= 3:
        lines.append(
            f"\n**Your Preference Profile:** Across {pref['high_rated']} highly-rated past trips, "
            f"you tend to prefer {PREF_LABELS.get(pref['dominant'], 'varied routes')} "
            f"({pref['low_stress_pct']}% low-stress, {pref['fast_pct']}% fast, "
            f"{pref['balanced_pct']}% balanced)."
        )

    return "\n".join(lines)


def compare_routes_table(routes):
    return [
        {
            "Route": f"{r['icon']}  {r['name']}",
            "Time (min)": r["stats"]["travel_time_min"],
            "Distance (km)": r["stats"]["distance_km"],
            "Difficult Turns": r["profile"].get("difficult_turns", 0),
            "Avg Stress (0-5)": r["profile"].get("avg_road_stress", 0),
            "Road Character": r["profile"].get("stress_label", "—"),
        }
        for r in routes
    ]
