import json as _json
import os as _os

# ---------------------------------------------------------------------------
# Load parameterised KB values from data/kb_params.json if available.
# Falls back to hardcoded defaults so the system starts cleanly even before
# the params file exists. After kb_refinement.py updates the file, call
# reload_kb_params() to pick up the new values.
# ---------------------------------------------------------------------------

_KB_PARAMS_PATH = _os.path.join(_os.path.dirname(__file__), "data", "kb_params.json")

_DEFAULT_ROAD_STRESS = {
    "motorway": 5.0,
    "trunk": 4.5,
    "primary": 3.5,
    "secondary": 2.5,
    "tertiary": 2.0,
    "unclassified": 1.8,
    "residential": 1.2,
    "living_street": 0.8,
    "service": 1.0,
    "road": 2.0,
}

_DEFAULT_TURN_RULES = [
    {"min_angle": 0,   "max_angle": 15,  "label": "straight ahead",       "base_score": 0.0},
    {"min_angle": 15,  "max_angle": 45,  "label": "gentle curve",          "base_score": 0.3},
    {"min_angle": 45,  "max_angle": 90,  "label": "moderate turn",         "base_score": 1.0},
    {"min_angle": 90,  "max_angle": 135, "label": "sharp turn",            "base_score": 2.0},
    {"min_angle": 135, "max_angle": 180, "label": "very sharp / U-turn",   "base_score": 3.0},
]

_DEFAULT_TURN_PENALTIES = {
    "no_signal_penalty": 0.5,
    "left_turn_penalty": 0.3,
    "multilane_threshold": 3,
    "multilane_penalty": 0.3,
    "penalty_applies_above_base_score": 1.0,
    "max_turn_score": 3.0,
}


def _load_kb_params() -> dict:
    try:
        with open(_KB_PARAMS_PATH) as _f:
            _p = _json.load(_f)
        return {
            "road_stress": _p.get("road_stress_scores", _DEFAULT_ROAD_STRESS),
            "turn_rules":  _p.get("turn_difficulty_rules", _DEFAULT_TURN_RULES),
            "turn_penalties": _p.get("turn_penalties", _DEFAULT_TURN_PENALTIES),
        }
    except (FileNotFoundError, _json.JSONDecodeError):
        return {
            "road_stress": _DEFAULT_ROAD_STRESS,
            "turn_rules":  _DEFAULT_TURN_RULES,
            "turn_penalties": _DEFAULT_TURN_PENALTIES,
        }


_KB = _load_kb_params()

ROAD_STRESS_SCORES = _KB["road_stress"]

# Turn difficulty rules — angle thresholds map to driving effort scores.
# Penalties are added for: unprotected turns (no signal), left turns across
# oncoming traffic, and multi-lane turns that require lane discipline.
TURN_DIFFICULTY_RULES = _KB["turn_rules"]

_TURN_PENALTIES = _KB["turn_penalties"]


def reload_kb_params() -> None:
    """
    Reload knowledge base parameters from disk.
    Call after kb_refinement.py applies a refinement so the router and scorer
    pick up updated values on the next request without restarting the server.
    """
    global ROAD_STRESS_SCORES, TURN_DIFFICULTY_RULES, _TURN_PENALTIES, _KB
    _KB = _load_kb_params()
    ROAD_STRESS_SCORES = _KB["road_stress"]
    TURN_DIFFICULTY_RULES = _KB["turn_rules"]
    _TURN_PENALTIES = _KB["turn_penalties"]


def get_road_stress(highway_type, maxspeed=None, lanes=None):
    if isinstance(highway_type, list):
        highway_type = highway_type[0]
    base = ROAD_STRESS_SCORES.get(str(highway_type).lower(), 2.0)

    speed_mod = 0.0
    if maxspeed:
        try:
            spd = str(maxspeed).replace(" mph", "").replace(" km/h", "").strip()
            spd = float(spd.split(";")[0])
            if spd > 100:  # likely km/h
                spd *= 0.621371
            if spd >= 55:
                speed_mod = 0.6
            elif spd >= 40:
                speed_mod = 0.3
            elif spd <= 25:
                speed_mod = -0.2
        except (ValueError, TypeError):
            pass

    lane_mod = 0.0
    if lanes:
        try:
            n = int(str(lanes).split(";")[0]) if isinstance(lanes, str) else int(lanes)
            if n >= 4:
                lane_mod = 0.4
            elif n >= 3:
                lane_mod = 0.2
        except (ValueError, TypeError):
            pass

    return round(min(5.0, max(0.0, base + speed_mod + lane_mod)), 2)


def stress_to_label(score):
    if score >= 4.5:
        return "high-speed highway"
    elif score >= 3.5:
        return "busy arterial"
    elif score >= 2.5:
        return "moderate main road"
    elif score >= 1.5:
        return "quiet side street"
    else:
        return "very calm local road"


def compute_turn_angle(bearing_in, bearing_out):
    diff = abs(bearing_out - bearing_in) % 360
    if diff > 180:
        diff = 360 - diff
    return round(diff, 1)


def classify_turn(angle_deg, has_signal=False, lanes=1, is_left_turn=False):
    base_score = 0.0
    label = "straight ahead"
    for rule in TURN_DIFFICULTY_RULES:
        if rule["min_angle"] <= angle_deg < rule["max_angle"]:
            label = rule["label"]
            base_score = rule["base_score"]
            break
    else:
        label = "very sharp / U-turn"
        base_score = 3.0

    penalties = _TURN_PENALTIES
    threshold = penalties.get("penalty_applies_above_base_score", 1.0)
    if base_score >= threshold:
        if not has_signal:
            base_score += penalties.get("no_signal_penalty", 0.5)
        if is_left_turn:
            base_score += penalties.get("left_turn_penalty", 0.3)
        ml_thresh = penalties.get("multilane_threshold", 3)
        if isinstance(lanes, (int, float)) and lanes >= ml_thresh:
            base_score += penalties.get("multilane_penalty", 0.3)

    max_score = penalties.get("max_turn_score", 3.0)
    return label, round(min(max_score, base_score), 2)


def score_edge(edge_data):
    highway = edge_data.get("highway", "unclassified")
    maxspeed = edge_data.get("maxspeed")
    lanes = edge_data.get("lanes", 1)

    if isinstance(lanes, list):
        try:
            lanes = max(int(l) for l in lanes if str(l).isdigit())
        except ValueError:
            lanes = 1
    elif lanes:
        try:
            lanes = int(str(lanes).split(";")[0])
        except (ValueError, TypeError):
            lanes = 1

    road_stress = get_road_stress(highway, maxspeed, lanes)
    return {
        "road_stress": road_stress,
        "stress_label": stress_to_label(road_stress),
        "highway_type": highway if not isinstance(highway, list) else highway[0],
        "lanes": lanes or 1,
    }


def summarize_route_profile(edge_list):
    if not edge_list:
        return {}

    total_len = sum(e.get("length", 0) for e in edge_list) or 1

    avg_stress = sum(
        e.get("road_stress", 2.0) * e.get("length", 0) for e in edge_list
    ) / total_len

    difficult_turns = sum(1 for e in edge_list if e.get("turn_difficulty", 0) >= 2.0)
    moderate_turns = sum(1 for e in edge_list if 1.0 <= e.get("turn_difficulty", 0) < 2.0)

    highway_m = sum(
        e.get("length", 0)
        for e in edge_list
        if e.get("highway_type", "") in ("motorway", "trunk", "primary")
    )
    residential_m = sum(
        e.get("length", 0)
        for e in edge_list
        if e.get("highway_type", "") in ("residential", "living_street", "service")
    )

    road_types = [e.get("highway_type", "unclassified") for e in edge_list]
    dominant = max(set(road_types), key=road_types.count) if road_types else "unclassified"

    return {
        "total_length_km": round(total_len / 1000, 2),
        "avg_road_stress": round(avg_stress, 2),
        "difficult_turns": difficult_turns,
        "moderate_turns": moderate_turns,
        "highway_pct": round(highway_m / total_len * 100, 1),
        "residential_pct": round(residential_m / total_len * 100, 1),
        "dominant_road_type": dominant,
        "stress_label": stress_to_label(avg_stress),
        "turn_summary": _build_turn_summary(difficult_turns, moderate_turns),
    }


def _build_turn_summary(difficult, moderate):
    if difficult == 0 and moderate == 0:
        return "mostly straight, no significant turns"
    elif difficult == 0:
        return f"{moderate} moderate turn{'s' if moderate != 1 else ''}, no sharp turns"
    else:
        return (
            f"{difficult} sharp/difficult turn{'s' if difficult != 1 else ''}"
            + (f" and {moderate} moderate" if moderate else "")
        )
