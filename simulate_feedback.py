"""
Simulate feedback rounds to generate KB convergence curve data.
Usage:
    python simulate_feedback.py              # 60 rounds, saves data/convergence.json
    python simulate_feedback.py --rounds 30  # custom count
"""
import argparse, json, random, copy
from pathlib import Path

KB_PATH = Path("data/kb_params.json")
OUT_PATH = Path("data/convergence.json")

# Simulated "ground truth" preference: users prefer lower-stress routes
ROUTE_PROFILES = [
    {"name": "Fastest Route", "avg_road_stress": 3.2, "difficult_turns": 2, "travel_time_min": 8.0, "distance_km": 3.5, "preference": "fast"},
    {"name": "Easiest Route", "avg_road_stress": 1.4, "difficult_turns": 0, "travel_time_min": 12.0, "distance_km": 4.1, "preference": "low_stress"},
    {"name": "Balanced Route", "avg_road_stress": 2.1, "difficult_turns": 1, "travel_time_min": 9.5, "distance_km": 3.8, "preference": "balanced"},
]

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

        snapshots.append({
            "round": i + 1,
            "stress_pro_ceiling": params["argument_thresholds"]["stress_pro_ceiling"],
            "left_turn_penalty": params["turn_penalties"]["left_turn_penalty"],
            "self_stress_to_time": params["attack_weights"]["self_stress_to_time"],
        })

    OUT_PATH.parent.mkdir(exist_ok=True)
    result = {"rounds": rounds, "snapshots": snapshots}
    with open(OUT_PATH, "w") as f:
        json.dump(result, f, indent=2)

    # Print summary
    print(f"\nConvergence simulation complete: {rounds} rounds")
    print(f"stress_pro_ceiling: {snapshots[0]['stress_pro_ceiling']:.3f} → {snapshots[-1]['stress_pro_ceiling']:.3f}")
    print(f"left_turn_penalty:  {snapshots[0]['left_turn_penalty']:.3f} → {snapshots[-1]['left_turn_penalty']:.3f}")
    print(f"Saved to {OUT_PATH}")

    # Find convergence round (when delta < 0.01 for 5 consecutive rounds)
    for j in range(5, len(snapshots)):
        window = snapshots[j-5:j]
        stress_range = max(s["stress_pro_ceiling"] for s in window) - min(s["stress_pro_ceiling"] for s in window)
        if stress_range < 0.005:
            print(f"Convergence detected at round {j+1}")
            break

    return result

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=60)
    args = parser.parse_args()
    random.seed(42)
    run_simulation(args.rounds)

if __name__ == "__main__":
    main()
