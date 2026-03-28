"""
Ablation study: compare 4 system configurations on a sample of landmark pairs.
Usage:
    python ablation.py --sample 20
"""
import argparse, json, random, time
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
}

PREF_MAP = {"Fastest Route": "fast", "Easiest Route": "low_stress", "Balanced Route": "balanced"}
OUT_PATH = Path("data/ablation_results.json")


def is_pareto_dominated(route, others):
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


def run_config(G, pairs, use_cbr=True, use_traffic=True, label="full"):
    """Run a set of pairs under a given configuration."""
    import knowledge_base as kb

    # Temporarily adjust traffic blend weight
    original_blend = kb._KB.get("traffic_blend_weight", 0.3)
    if not use_traffic:
        kb._KB["traffic_blend_weight"] = 0.0

    results = []
    for orig_name, orig_ll, dest_name, dest_ll in pairs:
        try:
            orig_node, dest_node = get_nearest_nodes(G, orig_ll, dest_ll)
            routes = generate_candidate_routes(G, orig_node, dest_node)
            if not routes:
                continue

            cbr_per_route = {}
            for r in routes:
                pref = PREF_MAP.get(r["name"], "balanced")
                if use_cbr:
                    cbr_per_route[r["name"]] = retrieve_similar_cases(
                        {**r["profile"], "travel_time_min": r["stats"]["travel_time_min"],
                         "distance_km": r["stats"]["distance_km"]},
                        target_preference=pref, top_k=3,
                    )
                else:
                    cbr_per_route[r["name"]] = []

            af = build_argumentation_framework(routes, cbr_per_route)
            af.compute_grounded_extension()
            recommended = af.recommend()
            faith = check_faithfulness(af, routes)

            rec_route = next((r for r in routes if r["name"] == recommended), None)
            pareto_ok = not is_pareto_dominated(rec_route, routes) if rec_route else None

            results.append({
                "pair": f"{orig_name} → {dest_name}",
                "n_routes": len(routes),
                "faithfulness": faith["score"],
                "pareto_non_dominated": pareto_ok,
                "recommended": recommended,
            })
        except Exception as e:
            pass

    # Restore
    kb._KB["traffic_blend_weight"] = original_blend

    n = len(results)
    if n == 0:
        return {"config": label, "n": 0}

    return {
        "config": label,
        "n": n,
        "mean_faithfulness": round(sum(r["faithfulness"] for r in results) / n, 3),
        "pareto_rate": round(sum(1 for r in results if r.get("pareto_non_dominated")) / n, 3),
        "n_routes_3": sum(1 for r in results if r["n_routes"] == 3),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, default=20)
    args = parser.parse_args()

    print("Loading graph...")
    G = load_or_fetch_graph("Bloomington, Indiana, USA")

    pairs = [
        (o, oll, d, dll)
        for o, oll in LANDMARKS.items()
        for d, dll in LANDMARKS.items()
        if o != d
    ]
    random.seed(42)
    pairs = random.sample(pairs, min(args.sample, len(pairs)))
    print(f"Running {len(pairs)} pairs across 4 configurations...")

    configs = [
        {"use_cbr": False, "use_traffic": False, "label": "baseline"},
        {"use_cbr": False, "use_traffic": True,  "label": "+traffic"},
        {"use_cbr": True,  "use_traffic": False, "label": "+cbr"},
        {"use_cbr": True,  "use_traffic": True,  "label": "full_system"},
    ]

    ablation_results = []
    for cfg in configs:
        label = cfg["label"]
        print(f"  Running config: {label}...")
        result = run_config(G, pairs, use_cbr=cfg["use_cbr"], use_traffic=cfg["use_traffic"], label=label)
        ablation_results.append(result)
        print(f"    faithfulness={result.get('mean_faithfulness')}, pareto={result.get('pareto_rate')}")

    OUT_PATH.parent.mkdir(exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(ablation_results, f, indent=2)

    print("\n=== ABLATION RESULTS ===")
    print(f"{'Config':<15} {'N':<5} {'Faithfulness':<14} {'Pareto Rate':<12} {'3-Route %'}")
    for r in ablation_results:
        n3_pct = round(r.get('n_routes_3', 0) / max(r['n'], 1) * 100)
        print(f"{r['config']:<15} {r['n']:<5} {r.get('mean_faithfulness', 'N/A'):<14} {r.get('pareto_rate', 'N/A'):<12} {n3_pct}%")

    print(f"\nSaved to {OUT_PATH}")

if __name__ == "__main__":
    main()
