"""
Automated benchmark for the Route Explanation System.

Runs all landmark pairs through the router and argumentation engine,
collecting metrics for RQ1–RQ3 in the research paper.

Usage:
    python benchmark.py              # full run, saves benchmark_results.json
    python benchmark.py --sample 20 --seed 42  # reproducible sample of 20 pairs
    python benchmark.py --report     # print summary table from existing results
"""

import json
import random
import argparse
import time
from pathlib import Path

from router import load_or_fetch_graph, get_nearest_nodes, generate_candidate_routes
from cbr import retrieve_similar_cases
from argumentation import build_argumentation_framework
from argumentation.explainer import check_faithfulness

LANDMARKS = {
    "IU Sample Gates": (39.1677, -86.5230),
    "Monroe County Courthouse": (39.1653, -86.5346),
    "IU Memorial Union": (39.1687, -86.5240),
    "IU Wells Library": (39.1720, -86.5189),
    "Bloomington City Hall": (39.1648, -86.5298),
    "IU Health Bloomington Hospital": (39.1558, -86.5268),
    "IU Kelley School of Business": (39.1713, -86.5099),
    "IU Memorial Stadium": (39.1793, -86.5252),
    "Kirkwood Ave & Dunn St": (39.1639, -86.5250),
    "Olcott Park": (39.1483, -86.5140),
    "Bryan Park": (39.1600, -86.5180),
    "Uptown Bloomington": (39.1720, -86.5380),
    "IU Assembly Hall": (39.1814, -86.5263),
    "Eskenazi Museum of Art": (39.1700, -86.5220),
    "Switchyard Park": (39.1568, -86.5340),
    "College Mall": (39.1645, -86.4950),
    "IU Luddy School of Informatics": (39.1727, -86.5233),
    "IU Musical Arts Center": (39.1672, -86.5168),
    "Cascades Park": (39.1522, -86.5408),
    "IU Ballantine Hall": (39.1697, -86.5192),
}

PREF_MAP = {"Fastest Route": "fast", "Easiest Route": "low_stress", "Balanced Route": "balanced"}
RESULTS_PATH = Path("data/benchmark_results.json")
DEFAULT_SAMPLE_SEED = 42


def route_diversity(path_a: list, path_b: list) -> float:
    """Jaccard distance between node sets of two paths. 1.0 = completely disjoint."""
    a, b = set(path_a), set(path_b)
    union = a | b
    if not union:
        return 0.0
    return round(1.0 - len(a & b) / len(union), 3)


def is_pareto_dominated(route: dict, others: list) -> bool:
    """Return True if `route` is strictly dominated by any other on (time, stress, turns)."""
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


def run_pair(G, orig_name: str, orig_ll, dest_name: str, dest_ll) -> dict | None:
    orig_node, dest_node = get_nearest_nodes(G, orig_ll, dest_ll)
    routes = generate_candidate_routes(G, orig_node, dest_node)
    if not routes:
        return None

    # Route diversity
    n_routes = len(routes)
    diversities = []
    for i in range(n_routes):
        for j in range(i + 1, n_routes):
            diversities.append(route_diversity(routes[i].get("path", []), routes[j].get("path", [])))
    mean_diversity = round(sum(diversities) / len(diversities), 3) if diversities else 0.0

    # Pareto non-dominance of recommended route
    cbr_per_route = {}
    for r in routes:
        pref = PREF_MAP.get(r["name"], "balanced")
        cbr_per_route[r["name"]] = retrieve_similar_cases(
            {**r["profile"], "travel_time_min": r["stats"]["travel_time_min"],
             "distance_km": r["stats"]["distance_km"]},
            target_preference=pref, top_k=3,
        )

    af = build_argumentation_framework(routes, cbr_per_route)
    af.compute_grounded_extension()
    recommended = af.recommend_with_routes(routes)
    af_dict = af.to_dict()

    # Faithfulness
    faith = check_faithfulness(af, routes)

    # Semantics comparison (RQ2)
    semantics = af.compare_semantics()

    # Pareto check on recommended route
    rec_route = next((r for r in routes if r["name"] == recommended), None)
    pareto_ok = not is_pareto_dominated(rec_route, routes) if rec_route else None

    return {
        "pair": f"{orig_name} → {dest_name}",
        "n_routes": n_routes,
        "mean_diversity": mean_diversity,
        "recommended": recommended,
        "pareto_non_dominated": pareto_ok,
        "accepted": af_dict["counts"]["accepted"],
        "rejected": af_dict["counts"]["rejected"],
        "undecided": af_dict["counts"]["undecided"],
        "attacks_succeeded": af_dict["counts"]["attacks_succeeded"],
        "faithfulness_score": faith["score"],
        "faithfulness_violations": faith["violations"],
        "all_semantics_agree": semantics["all_semantics_agree"],
        "preferred_extension_count": semantics["preferred"]["count"],
        "stable_extension_count": semantics["stable"]["count"],
    }


def print_report(results: list):
    if not results:
        print("No results to report.")
        return

    n = len(results)
    n3 = sum(1 for r in results if r["n_routes"] == 3)
    n2 = sum(1 for r in results if r["n_routes"] == 2)
    n1 = sum(1 for r in results if r["n_routes"] <= 1)

    mean_div = sum(r["mean_diversity"] for r in results) / n
    pareto_ok = sum(1 for r in results if r.get("pareto_non_dominated") is True)
    pareto_total = sum(1 for r in results if r.get("pareto_non_dominated") is not None)
    mean_accepted = sum(r["accepted"] for r in results) / n
    mean_attacks = sum(r["attacks_succeeded"] for r in results) / n
    mean_faith = sum(r["faithfulness_score"] for r in results) / n
    semantics_agree = sum(1 for r in results if r.get("all_semantics_agree")) / n

    print("\n" + "=" * 62)
    print("  ROUTE EXPLANATION SYSTEM — BENCHMARK REPORT")
    print("=" * 62)
    print(f"  Pairs evaluated:              {n}")
    print(f"  3 distinct routes:            {n3} ({round(n3/n*100)}%)")
    print(f"  2 distinct routes:            {n2} ({round(n2/n*100)}%)")
    print(f"  ≤1 route generated:          {n1} ({round(n1/n*100)}%)")
    print(f"  Mean route diversity (Jaccard):{mean_div:.3f}")
    print(f"  Pareto non-dominated rec.:    {pareto_ok}/{pareto_total} ({round(pareto_ok/max(pareto_total,1)*100)}%)")
    print(f"  Mean accepted args/query:     {mean_accepted:.1f}")
    print(f"  Mean successful attacks/query:{mean_attacks:.1f}")
    print(f"  Mean faithfulness score:      {mean_faith:.3f}")
    print(f"  All semantics agree:          {round(semantics_agree*100)}%")
    print("=" * 62 + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, default=0, help="Number of random pairs (0 = all 380)")
    parser.add_argument("--seed", type=int, default=DEFAULT_SAMPLE_SEED, help="Random seed used when sampling pairs")
    parser.add_argument("--report", action="store_true", help="Print report from existing results file")
    args = parser.parse_args()

    if args.report:
        if not RESULTS_PATH.exists():
            print("No benchmark_results.json found. Run benchmark first.")
            return
        with open(RESULTS_PATH) as f:
            print_report(json.load(f))
        return

    print("Loading graph...")
    G = load_or_fetch_graph("Bloomington, Indiana, USA")

    pairs = [
        (orig, orig_ll, dest, dest_ll)
        for orig, orig_ll in LANDMARKS.items()
        for dest, dest_ll in LANDMARKS.items()
        if orig != dest
    ]

    if args.sample > 0:
        rng = random.Random(args.seed)
        pairs = rng.sample(pairs, min(args.sample, len(pairs)))
        print(f"Using sample seed: {args.seed}")

    print(f"Running {len(pairs)} pairs...")
    results = []
    for i, (orig, orig_ll, dest, dest_ll) in enumerate(pairs):
        t0 = time.time()
        try:
            result = run_pair(G, orig, orig_ll, dest, dest_ll)
            if result:
                results.append(result)
                elapsed = round(time.time() - t0, 2)
                print(f"  [{i+1}/{len(pairs)}] {result['pair']}: "
                      f"{result['n_routes']} routes, div={result['mean_diversity']}, "
                      f"faith={result['faithfulness_score']:.2f} ({elapsed}s)")
        except Exception as e:
            print(f"  [{i+1}/{len(pairs)}] ERROR {orig} → {dest}: {e}")

    RESULTS_PATH.parent.mkdir(exist_ok=True)
    with open(RESULTS_PATH, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved {len(results)} results to {RESULTS_PATH}")
    print_report(results)


if __name__ == "__main__":
    main()
