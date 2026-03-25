import os
import pickle

import osmnx as ox
import networkx as nx

from knowledge_base import score_edge, classify_turn, compute_turn_angle, summarize_route_profile

CACHE_DIR = "data"
CACHE_PATH = os.path.join(CACHE_DIR, "graph_bloomington.pkl")

ROUTE_CONFIGS = [
    {
        "name": "Fastest Route",
        "icon": "⚡",
        "color": "#e74c3c",
        "description": "Minimizes travel time",
        "weights": {"time": 1.0, "stress": 0.05, "turns": 0.05, "distance": 0.0},
    },
    {
        "name": "Easiest Route",
        "icon": "🌿",
        "color": "#27ae60",
        "description": "Fewest difficult turns, quietest roads",
        "weights": {"time": 0.2, "stress": 1.0, "turns": 1.8, "distance": 0.0},
    },
    {
        "name": "Balanced Route",
        "icon": "⚖️",
        "color": "#2980b9",
        "description": "Best overall trade-off",
        "weights": {"time": 0.6, "stress": 0.6, "turns": 0.8, "distance": 0.0},
    },
]


def load_or_fetch_graph(place="Bloomington, Indiana, USA"):
    os.makedirs(CACHE_DIR, exist_ok=True)
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, "rb") as f:
            return pickle.load(f)

    print(f"Downloading OSM graph for {place} — this takes ~30 sec the first time...")
    G = ox.graph_from_place(place, network_type="drive")
    G = ox.add_edge_speeds(G)
    G = ox.add_edge_travel_times(G)
    G = ox.add_edge_bearings(G)
    with open(CACHE_PATH, "wb") as f:
        pickle.dump(G, f)
    print("Graph downloaded and cached.")
    return G


def get_nearest_nodes(G, origin_latlon, dest_latlon):
    o = ox.nearest_nodes(G, origin_latlon[1], origin_latlon[0])
    d = ox.nearest_nodes(G, dest_latlon[1], dest_latlon[0])
    return o, d


def _edge_cost(G, u, v, data, weights):
    travel_time = data.get("travel_time", data.get("length", 100) / 8.0)
    length = data.get("length", 50)
    scores = score_edge(data)
    road_stress = scores["road_stress"]

    in_bearing = data.get("bearing", 0) or 0
    out_edges = list(G.out_edges(v, data=True))
    turn_cost = 0.0
    if out_edges:
        difficulties = []
        for _, _, ed in out_edges:
            out_bearing = ed.get("bearing", in_bearing) or in_bearing
            angle = compute_turn_angle(in_bearing, out_bearing)
            # bearing delta > 180 means left turn in standard compass orientation
            is_left = (out_bearing - in_bearing) % 360 > 180
            _, diff_score = classify_turn(angle, has_signal=False, lanes=scores["lanes"], is_left_turn=is_left)
            difficulties.append(diff_score)
        turn_cost = sum(difficulties) / len(difficulties) * 25

    cost = (
        weights["time"] * travel_time
        + weights["stress"] * road_stress * 12
        + weights["turns"] * turn_cost
        + weights["distance"] * length * 0.005
    )
    return max(cost, 1e-6)


def _find_path(G, orig, dest, weights):
    def wfn(u, v, data):
        return _edge_cost(G, u, v, data, weights)
    try:
        return nx.shortest_path(G, orig, dest, weight=wfn)
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return None


def _path_key(path):
    # Sample every 5th node so near-identical paths aren't treated as duplicates
    return tuple(path[::5] + [path[-1]])


def _extract_edges(G, path):
    edges = []
    for i in range(len(path) - 1):
        u, v = path[i], path[i + 1]
        raw = dict(list(G[u][v].values())[0])
        enriched = {**raw, **score_edge(raw)}

        if i > 0:
            prev_u = path[i - 1]
            prev_raw = list(G[prev_u][u].values())[0]
            in_bearing = prev_raw.get("bearing", 0) or 0
            out_bearing = raw.get("bearing", 0) or 0
            angle = compute_turn_angle(in_bearing, out_bearing)
            is_left = (out_bearing - in_bearing) % 360 > 180
            t_label, t_score = classify_turn(angle, has_signal=False, lanes=enriched["lanes"], is_left_turn=is_left)
            enriched["turn_angle"] = angle
            enriched["turn_label"] = t_label
            enriched["turn_difficulty"] = t_score
            enriched["turn_coord"] = [G.nodes[u]["y"], G.nodes[u]["x"]] # Frontend pinpoint reference
        else:
            enriched["turn_angle"] = 0.0
            enriched["turn_label"] = "start"
            enriched["turn_difficulty"] = 0.0
            enriched["turn_coord"] = [G.nodes[u]["y"], G.nodes[u]["x"]] # Added coordinate

        edges.append(enriched)
    return edges


def _get_coords(G, path):
    return [(G.nodes[n]["y"], G.nodes[n]["x"]) for n in path]


def _route_stats(edges):
    total_time = sum(e.get("travel_time", 0) for e in edges)
    total_dist = sum(e.get("length", 0) for e in edges)
    return {
        "travel_time_min": round(total_time / 60, 1),
        "distance_km": round(total_dist / 1000, 2),
    }


def generate_candidate_routes(G, orig_node, dest_node):
    routes = []
    seen = set()

    for cfg in ROUTE_CONFIGS:
        path = _find_path(G, orig_node, dest_node, cfg["weights"])
        if path is None:
            continue

        key = _path_key(path)
        if key in seen:
            # Perturb weights to force a different path for variety
            w2 = {k: v * (1.15 if k != "time" else 0.85) for k, v in cfg["weights"].items()}
            path2 = _find_path(G, orig_node, dest_node, w2)
            if path2 and _path_key(path2) not in seen:
                path = path2
                key = _path_key(path)

        seen.add(key)
        edges = _extract_edges(G, path)
        coords = _get_coords(G, path)
        stats = _route_stats(edges)
        profile = summarize_route_profile(edges)

        routes.append({
            **{k: v for k, v in cfg.items() if k != "weights"},
            "path": path,
            "coords": coords,
            "edges": edges,
            "stats": stats,
            "profile": profile,
        })

    return routes
