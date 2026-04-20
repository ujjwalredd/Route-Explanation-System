"""
Simulate feedback rounds to generate KB convergence curve data.
Usage:
    python simulate_feedback.py              # 60 rounds, saves data/convergence.json
    python simulate_feedback.py --rounds 30  # custom count
"""
import argparse, json, random
from pathlib import Path

KB_PATH = Path("data/kb_params.json")
OUT_PATH = Path("data/convergence.json")

# Simulated "ground truth" preference: users prefer lower-stress routes
ROUTE_PROFILES = [
    {"name": "Fastest Route", "avg_road_stress": 3.2, "difficult_turns": 2, "travel_time_min": 8.0, "distance_km": 3.5, "preference": "fast"},
    {"name": "Easiest Route", "avg_road_stress": 1.4, "difficult_turns": 0, "travel_time_min": 12.0, "distance_km": 4.1, "preference": "low_stress"},
    {"name": "Balanced Route", "avg_road_stress": 2.1, "difficult_turns": 1, "travel_time_min": 9.5, "distance_km": 3.8, "preference": "balanced"},
]

CONVERGENCE_THRESHOLD = 0.005
CONVERGENCE_WINDOW = 5


def detect_convergence(update_snapshots: list[dict]) -> dict:
    """
    Detect convergence across refinement checkpoints rather than raw rounds.

    Using per-round snapshots is misleading because parameters only update every
    5 rounds, creating long flat stretches even while the system is still
    drifting at each refinement step.
    """
    first_parameter_change_round = None
    first_stress_change_round = None

    for idx in range(1, len(update_snapshots)):
        prev = update_snapshots[idx - 1]
        curr = update_snapshots[idx]
        if first_parameter_change_round is None and (
            curr["stress_pro_ceiling"] != prev["stress_pro_ceiling"]
            or curr["left_turn_penalty"] != prev["left_turn_penalty"]
            or curr["self_stress_to_time"] != prev["self_stress_to_time"]
        ):
            first_parameter_change_round = curr["round"]
        if first_stress_change_round is None and curr["stress_pro_ceiling"] != prev["stress_pro_ceiling"]:
            first_stress_change_round = curr["round"]

    for idx in range(CONVERGENCE_WINDOW - 1, len(update_snapshots)):
        window = update_snapshots[idx - CONVERGENCE_WINDOW + 1:idx + 1]
        if first_stress_change_round is None or window[0]["round"] < first_stress_change_round:
            continue
        values = [snap["stress_pro_ceiling"] for snap in window]
        if max(values) - min(values) < CONVERGENCE_THRESHOLD:
            return {
                "reached": True,
                "round": window[-1]["round"],
                "threshold": CONVERGENCE_THRESHOLD,
                "window_checkpoints": CONVERGENCE_WINDOW,
                "first_parameter_change_round": first_parameter_change_round,
                "first_stress_change_round": first_stress_change_round,
            }

    return {
        "reached": False,
        "round": None,
        "threshold": CONVERGENCE_THRESHOLD,
        "window_checkpoints": CONVERGENCE_WINDOW,
        "first_parameter_change_round": first_parameter_change_round,
        "first_stress_change_round": first_stress_change_round,
    }

def simulate_feedback_score(route_profile: dict) -> int:
    """Simulate user feedback: low-stress routes rated higher."""
    stress = route_profile["avg_road_stress"]
    turns = route_profile["difficult_turns"]
    # Higher stress + turns = lower rating; add noise
    base = 5.0 - stress * 0.6 - turns * 0.4
    noisy = base + random.gauss(0, 0.5)
    return max(1, min(5, round(noisy)))

def run_simulation(rounds: int):
    with open(KB_PATH) as f:
        params = json.load(f)

    snapshots = []
    update_snapshots = []
    cases = []

    for i in range(rounds):
        # Pick a random route profile and simulate feedback
        route = random.choice(ROUTE_PROFILES)
        score = simulate_feedback_score(route)
        cases.append({"profile": route, "score": score, "round": i})

        # After every 5 cases, simulate what refinement would do
        if len(cases) >= 5 and i % 5 == 0:
            # Detect stress calibration signal
            high_rated = [c for c in cases[-20:] if c["score"] >= 4]
            if high_rated:
                avg_stress = sum(c["profile"]["avg_road_stress"] for c in high_rated) / len(high_rated)
                current_ceiling = params["argument_thresholds"]["stress_pro_ceiling"]
                if abs(avg_stress - current_ceiling) > 0.15:
                    delta = (avg_stress - current_ceiling) * params["refinement"]["learning_rate"]
                    delta = max(-params["refinement"]["max_stress_adjustment"], min(params["refinement"]["max_stress_adjustment"], delta))
                    params["argument_thresholds"]["stress_pro_ceiling"] = round(current_ceiling + delta, 3)

            # Detect turn penalty signal
            hard_turn_cases = [c for c in cases[-20:] if c["profile"]["difficult_turns"] >= 2]
            easy_turn_cases = [c for c in cases[-20:] if c["profile"]["difficult_turns"] == 0]
            if hard_turn_cases and easy_turn_cases:
                hard_avg = sum(c["score"] for c in hard_turn_cases) / len(hard_turn_cases)
                easy_avg = sum(c["score"] for c in easy_turn_cases) / len(easy_turn_cases)
                gap = easy_avg - hard_avg
                if gap > 1.0:
                    current = params["turn_penalties"]["left_turn_penalty"]
                    delta = gap * 0.02
                    params["turn_penalties"]["left_turn_penalty"] = round(min(1.0, current + delta), 3)

            update_snapshots.append({
                "round": i + 1,
                "stress_pro_ceiling": params["argument_thresholds"]["stress_pro_ceiling"],
                "left_turn_penalty": params["turn_penalties"]["left_turn_penalty"],
                "self_stress_to_time": params["attack_weights"]["self_stress_to_time"],
            })

        snapshots.append({
            "round": i + 1,
            "stress_pro_ceiling": params["argument_thresholds"]["stress_pro_ceiling"],
            "left_turn_penalty": params["turn_penalties"]["left_turn_penalty"],
            "self_stress_to_time": params["attack_weights"]["self_stress_to_time"],
        })

    OUT_PATH.parent.mkdir(exist_ok=True)
    convergence = detect_convergence(update_snapshots)
    result = {
        "rounds": rounds,
        "snapshots": snapshots,
        "update_snapshots": update_snapshots,
        "convergence": convergence,
    }
    with open(OUT_PATH, "w") as f:
        json.dump(result, f, indent=2)

    # Print summary
    print(f"\nConvergence simulation complete: {rounds} rounds")
    print(f"stress_pro_ceiling: {snapshots[0]['stress_pro_ceiling']:.3f} → {snapshots[-1]['stress_pro_ceiling']:.3f}")
    print(f"left_turn_penalty:  {snapshots[0]['left_turn_penalty']:.3f} → {snapshots[-1]['left_turn_penalty']:.3f}")
    print(f"Saved to {OUT_PATH}")

    if convergence["first_parameter_change_round"] is not None:
        print(f"First parameter change detected at round {convergence['first_parameter_change_round']}")

    if convergence["reached"]:
        print(
            f"Convergence detected at round {convergence['round']} "
            f"(threshold {CONVERGENCE_THRESHOLD} across {CONVERGENCE_WINDOW} refinement checkpoints)"
        )
    else:
        print(
            f"Convergence not reached within {rounds} rounds "
            f"(threshold {CONVERGENCE_THRESHOLD} across {CONVERGENCE_WINDOW} refinement checkpoints)"
        )

    return result

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=60)
    args = parser.parse_args()
    random.seed(42)
    run_simulation(args.rounds)

if __name__ == "__main__":
    main()
