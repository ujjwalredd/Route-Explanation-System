import json
import os
from datetime import datetime

CASES_PATH = os.path.join("data", "cases.json")


def load_cases():
    os.makedirs("data", exist_ok=True)
    if not os.path.exists(CASES_PATH):
        _seed_cases()
    with open(CASES_PATH, "r") as f:
        return json.load(f)


def save_cases(cases):
    os.makedirs("data", exist_ok=True)
    with open(CASES_PATH, "w") as f:
        json.dump(cases, f, indent=2)


def _seed_cases():
    cases = [
        {
            "id": 1,
            "origin_name": "IU Sample Gates",
            "dest_name": "Monroe County Courthouse",
            "preferred_route_type": "Easiest Route",
            "reason": "user preferred fewer turns during morning rush hour",
            "profile": {
                "difficult_turns": 0, "moderate_turns": 2, "avg_road_stress": 1.3,
                "distance_km": 2.1, "travel_time_min": 7.5,
                "dominant_road_type": "residential", "stress_label": "quiet side street",
            },
            "user_preference": "low_stress", "feedback_score": 5,
            "timestamp": "2025-09-10T08:15:00",
        },
        {
            "id": 2,
            "origin_name": "IU Memorial Union",
            "dest_name": "IU Health Bloomington Hospital",
            "preferred_route_type": "Fastest Route",
            "reason": "user was in a hurry and accepted busier roads",
            "profile": {
                "difficult_turns": 2, "moderate_turns": 3, "avg_road_stress": 3.2,
                "distance_km": 3.4, "travel_time_min": 8.0,
                "dominant_road_type": "primary", "stress_label": "busy arterial",
            },
            "user_preference": "fast", "feedback_score": 4,
            "timestamp": "2025-09-18T09:00:00",
        },
        {
            "id": 3,
            "origin_name": "Kirkwood Ave",
            "dest_name": "IU Memorial Stadium",
            "preferred_route_type": "Easiest Route",
            "reason": "user consistently avoids difficult left turns near downtown",
            "profile": {
                "difficult_turns": 0, "moderate_turns": 1, "avg_road_stress": 1.5,
                "distance_km": 1.8, "travel_time_min": 6.0,
                "dominant_road_type": "residential", "stress_label": "quiet side street",
            },
            "user_preference": "low_stress", "feedback_score": 5,
            "timestamp": "2025-10-02T17:30:00",
        },
        {
            "id": 4,
            "origin_name": "Bloomington City Hall",
            "dest_name": "IU Kelley School of Business",
            "preferred_route_type": "Balanced Route",
            "reason": "user valued time savings without completely avoiding main roads",
            "profile": {
                "difficult_turns": 1, "moderate_turns": 2, "avg_road_stress": 2.1,
                "distance_km": 1.6, "travel_time_min": 5.5,
                "dominant_road_type": "secondary", "stress_label": "moderate main road",
            },
            "user_preference": "balanced", "feedback_score": 4,
            "timestamp": "2025-10-12T14:00:00",
        },
        {
            "id": 5,
            "origin_name": "Eastside neighborhood",
            "dest_name": "Bloomington Square",
            "preferred_route_type": "Easiest Route",
            "reason": "user preferred residential streets to avoid the College Ave on-ramp merge",
            "profile": {
                "difficult_turns": 0, "moderate_turns": 3, "avg_road_stress": 1.4,
                "distance_km": 4.0, "travel_time_min": 11.5,
                "dominant_road_type": "residential", "stress_label": "quiet side street",
            },
            "user_preference": "low_stress", "feedback_score": 5,
            "timestamp": "2025-10-20T07:45:00",
        },
        {
            "id": 6,
            "origin_name": "IU East Parking Garage",
            "dest_name": "Kroger on 3rd Street",
            "preferred_route_type": "Fastest Route",
            "reason": "quick errand, user prioritized speed over comfort",
            "profile": {
                "difficult_turns": 1, "moderate_turns": 2, "avg_road_stress": 2.6,
                "distance_km": 2.0, "travel_time_min": 5.5,
                "dominant_road_type": "tertiary", "stress_label": "moderate main road",
            },
            "user_preference": "fast", "feedback_score": 4,
            "timestamp": "2025-10-25T11:00:00",
        },
        {
            "id": 7,
            "origin_name": "IU Wells Library",
            "dest_name": "Olcott Park",
            "preferred_route_type": "Easiest Route",
            "reason": "evening drive, user preferred the predictability of residential streets",
            "profile": {
                "difficult_turns": 0, "moderate_turns": 2, "avg_road_stress": 1.2,
                "distance_km": 3.1, "travel_time_min": 9.0,
                "dominant_road_type": "residential", "stress_label": "quiet side street",
            },
            "user_preference": "low_stress", "feedback_score": 5,
            "timestamp": "2025-11-05T20:00:00",
        },
        {
            "id": 8,
            "origin_name": "Uptown Bloomington",
            "dest_name": "IU Sample Gates",
            "preferred_route_type": "Balanced Route",
            "reason": "user new to the area, preferred clearly-marked main roads",
            "profile": {
                "difficult_turns": 1, "moderate_turns": 3, "avg_road_stress": 2.3,
                "distance_km": 2.8, "travel_time_min": 9.5,
                "dominant_road_type": "secondary", "stress_label": "moderate main road",
            },
            "user_preference": "balanced", "feedback_score": 3,
            "timestamp": "2025-11-12T10:30:00",
        },
        {
            "id": 9,
            "origin_name": "Bryan Park",
            "dest_name": "IU Memorial Union",
            "preferred_route_type": "Fastest Route",
            "reason": "running late to a meeting, fastest path was the clear choice",
            "profile": {
                "difficult_turns": 2, "moderate_turns": 1, "avg_road_stress": 3.0,
                "distance_km": 2.5, "travel_time_min": 7.0,
                "dominant_road_type": "primary", "stress_label": "busy arterial",
            },
            "user_preference": "fast", "feedback_score": 4,
            "timestamp": "2025-11-20T08:50:00",
        },
        {
            "id": 10,
            "origin_name": "Winslow Farm",
            "dest_name": "Monroe County Courthouse",
            "preferred_route_type": "Balanced Route",
            "reason": "user wanted a route that saves time but avoids the tricky downtown left turns",
            "profile": {
                "difficult_turns": 1, "moderate_turns": 2, "avg_road_stress": 2.0,
                "distance_km": 5.5, "travel_time_min": 13.0,
                "dominant_road_type": "secondary", "stress_label": "moderate main road",
            },
            "user_preference": "balanced", "feedback_score": 5,
            "timestamp": "2025-12-01T16:00:00",
        },
    ]
    save_cases(cases)


def _profile_similarity(p1, p2):
    # Normalized distance across four features, averaged to a 0-1 score
    features = [
        ("difficult_turns", 6.0),
        ("avg_road_stress", 5.0),
        ("distance_km", 12.0),
        ("travel_time_min", 30.0),
    ]
    total = 0.0
    for key, max_val in features:
        total += max(0.0, 1.0 - abs(float(p1.get(key, 0)) - float(p2.get(key, 0))) / max_val)
    return round(total / len(features), 3)


def retrieve_similar_cases(target_profile, target_preference=None, top_k=3):
    cases = load_cases()
    scored = []
    for case in cases:
        sim = _profile_similarity(target_profile, case.get("profile", {}))
        pref_bonus = 0.15 if target_preference and case.get("user_preference") == target_preference else 0.0
        rating_bonus = (case.get("feedback_score", 3) - 3) * 0.04
        scored.append((sim + pref_bonus + rating_bonus, case))
    scored.sort(key=lambda x: -x[0])
    return scored[:top_k]


def store_case(origin_name, dest_name, chosen_route, feedback_score):
    cases = load_cases()
    new_id = max((c["id"] for c in cases), default=0) + 1
    pref_map = {"Fastest Route": "fast", "Easiest Route": "low_stress", "Balanced Route": "balanced"}

    new_case = {
        "id": new_id,
        "origin_name": origin_name,
        "dest_name": dest_name,
        "preferred_route_type": chosen_route["name"],
        "reason": f"user chose {chosen_route['name']} and rated it {feedback_score}/5",
        "profile": {
            **chosen_route.get("profile", {}),
            "travel_time_min": chosen_route["stats"]["travel_time_min"],
            "distance_km": chosen_route["stats"]["distance_km"],
        },
        "user_preference": pref_map.get(chosen_route["name"], "balanced"),
        "feedback_score": feedback_score,
        "timestamp": datetime.now().isoformat(),
    }
    cases.append(new_case)
    save_cases(cases)
    return new_case


def get_preference_summary():
    cases = load_cases()
    high_rated = [c for c in cases if c.get("feedback_score", 0) >= 4]
    if not high_rated:
        return None

    prefs = [c.get("user_preference", "balanced") for c in high_rated]
    dominant = max(set(prefs), key=prefs.count)
    total = len(prefs)
    return {
        "dominant": dominant,
        "total_cases": len(cases),
        "high_rated": total,
        "low_stress_pct": round(prefs.count("low_stress") / total * 100),
        "fast_pct": round(prefs.count("fast") / total * 100),
        "balanced_pct": round(prefs.count("balanced") / total * 100),
    }
