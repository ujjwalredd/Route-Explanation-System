"""
Bloomington Traffic Count Integration
======================================
Downloads AADT (Annual Average Daily Traffic) from the City of Bloomington
Open Data portal and builds a per-OSM-node traffic index cached to disk.

Source: https://data.bloomington.in.gov/Transportation/Traffic-Counts/dcr5-fg4c/about_data
API:    https://data.bloomington.in.gov/resource/dcr5-fg4c.json

AADT = Annual Average Daily Traffic — the average number of vehicles passing a
point on a road in a 24-hour period, averaged across all days of the year.
This directly grounds road stress scores in real observed traffic rather than
heuristic road type classifications.

Usage:
    python traffic_data.py            # download + build index
    python traffic_data.py --check    # print coverage stats without rebuilding

After running, knowledge_base.py automatically blends the index into stress scores.
"""

from __future__ import annotations
import json
import math
import os
import ssl
import sys
import argparse
import urllib.request
from typing import Optional

# macOS Python installs often lack the system CA bundle — bypass for this public API.
_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE

TRAFFIC_API = "https://data.bloomington.in.gov/resource/dcr5-fg4c.json"
CACHE_PATH  = os.path.join("data", "traffic_raw.json")
INDEX_PATH  = os.path.join("data", "traffic_index.json")
GRAPH_PATH  = os.path.join("data", "graph_bloomington.pkl")

# Only keep stations within Monroe County bounding box (generous margin)
LAT_MIN, LAT_MAX = 38.8, 39.5
LNG_MIN, LNG_MAX = -86.9, -86.2


# ---------------------------------------------------------------------------
# Step 1: Download
# ---------------------------------------------------------------------------

def download_traffic_data(force: bool = False) -> list[dict]:
    """
    Fetch all AADT records from the Bloomington Open Data portal.
    Results are cached to data/traffic_raw.json.
    """
    if not force and os.path.exists(CACHE_PATH):
        print(f"  Using cached traffic data from {CACHE_PATH}")
        with open(CACHE_PATH) as f:
            return json.load(f)

    print("  Downloading traffic count data from Bloomington Open Data...")
    # Single request — 2,625 records is well under the 50,000 SODA limit
    url = f"{TRAFFIC_API}?$limit=50000&$order=year%20DESC"
    with urllib.request.urlopen(url, timeout=30, context=_SSL_CTX) as resp:
        records = json.loads(resp.read().decode())

    print(f"  Downloaded {len(records)} records.")
    os.makedirs("data", exist_ok=True)
    with open(CACHE_PATH, "w") as f:
        json.dump(records, f)
    return records


# ---------------------------------------------------------------------------
# Step 2: Deduplicate — keep most recent AADT per station
# ---------------------------------------------------------------------------

def deduplicate(records: list[dict]) -> list[dict]:
    """
    For each unique loc_id, keep the record with the most recent year.
    Filters out records missing lat/long/aadt or outside the county bbox.
    """
    best: dict[str, dict] = {}
    skipped = 0

    for r in records:
        try:
            lat  = float(r["lat"])
            lng  = float(r["long"])
            aadt = int(r["aadt"])
        except (KeyError, ValueError, TypeError):
            skipped += 1
            continue

        if not (LAT_MIN <= lat <= LAT_MAX and LNG_MIN <= lng <= LNG_MAX):
            skipped += 1
            continue
        if aadt <= 0:
            continue

        loc_id = r.get("loc_id", f"{lat:.5f},{lng:.5f}")
        year   = int(r.get("year", 0))

        if loc_id not in best or year > int(best[loc_id].get("year", 0)):
            best[loc_id] = {
                "loc_id":    loc_id,
                "lat":       lat,
                "lng":       lng,
                "aadt":      aadt,
                "year":      year,
                "crossroad": r.get("crossroad", ""),
            }

    stations = list(best.values())
    print(f"  Deduplicated to {len(stations)} unique stations ({skipped} records skipped).")
    return stations


# ---------------------------------------------------------------------------
# Step 3: Normalize AADT → traffic index [0, 1]
# ---------------------------------------------------------------------------

def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    sorted_v = sorted(values)
    idx = max(0, min(len(sorted_v) - 1, int(len(sorted_v) * p / 100)))
    return sorted_v[idx]


def normalize_aadt(stations: list[dict]) -> list[dict]:
    """
    Normalize AADT to a [0, 1] traffic index using log-scale normalization
    against the 95th-percentile AADT value (caps outliers).

    Log-scale is appropriate because traffic volume spans several orders of
    magnitude — a road with 20,000 vehicles/day is not 10× worse than one
    with 2,000, but it does carry meaningfully more stress.
    """
    aadts = [s["aadt"] for s in stations]
    cap   = _percentile(aadts, 95)
    if cap == 0:
        cap = max(aadts) or 1

    for s in stations:
        capped = min(s["aadt"], cap)
        s["traffic_index"] = round(math.log1p(capped) / math.log1p(cap), 4)

    print(f"  AADT range: {min(aadts):,}–{max(aadts):,} vehicles/day. "
          f"95th pct cap: {cap:,}. Normalized to [0, 1].")
    return stations


# ---------------------------------------------------------------------------
# Step 4: Match stations → nearest OSM nodes
# ---------------------------------------------------------------------------

def build_node_index(stations: list[dict]) -> dict[int, dict]:
    """
    For each station, find the nearest OSM node in the cached road graph.
    Returns {osm_node_id: {traffic_index, aadt, crossroad, loc_id}}.

    When multiple stations map to the same node, the one with the highest
    AADT is kept (conservative: take the worse-case traffic for that node).
    """
    import pickle
    if not os.path.exists(GRAPH_PATH):
        print("  Graph not found — run the API server first to download it.")
        return {}

    print("  Loading OSM graph...")
    with open(GRAPH_PATH, "rb") as f:
        G = pickle.load(f)

    try:
        import osmnx as ox
    except ImportError:
        print("  osmnx not available — cannot match stations to OSM nodes.")
        return {}

    lngs = [s["lng"] for s in stations]
    lats = [s["lat"] for s in stations]
    print(f"  Matching {len(stations)} stations to OSM nodes...")
    node_ids = ox.nearest_nodes(G, lngs, lats)

    node_index: dict[int, dict] = {}
    for node_id, station in zip(node_ids, stations):
        existing = node_index.get(node_id)
        if existing is None or station["aadt"] > existing["aadt"]:
            node_index[int(node_id)] = {
                "traffic_index": station["traffic_index"],
                "aadt":          station["aadt"],
                "crossroad":     station["crossroad"],
                "loc_id":        station["loc_id"],
                "year":          station["year"],
            }

    print(f"  Mapped to {len(node_index)} unique OSM nodes.")
    return node_index


# ---------------------------------------------------------------------------
# Step 5: Save index
# ---------------------------------------------------------------------------

def save_index(node_index: dict[int, dict]) -> None:
    os.makedirs("data", exist_ok=True)
    # JSON keys must be strings
    serializable = {str(k): v for k, v in node_index.items()}
    with open(INDEX_PATH, "w") as f:
        json.dump(serializable, f, indent=2)
    print(f"  Traffic index saved to {INDEX_PATH} ({len(serializable)} nodes).")


# ---------------------------------------------------------------------------
# Runtime lookup (used by knowledge_base.py)
# ---------------------------------------------------------------------------

_INDEX_CACHE: Optional[dict[int, float]] = None


def load_traffic_index() -> dict[int, float]:
    """
    Returns {osm_node_id (int): traffic_index (float)} from the cached file.
    Returns an empty dict if the index has not been built yet.
    Called at module import time by knowledge_base.py.
    """
    global _INDEX_CACHE
    if _INDEX_CACHE is not None:
        return _INDEX_CACHE

    if not os.path.exists(INDEX_PATH):
        _INDEX_CACHE = {}
        return _INDEX_CACHE

    with open(INDEX_PATH) as f:
        raw = json.load(f)
    _INDEX_CACHE = {int(k): v["traffic_index"] for k, v in raw.items()}
    return _INDEX_CACHE


def get_node_traffic_index(node_id: int) -> Optional[float]:
    """Return traffic index for a specific OSM node, or None if not in index."""
    idx = load_traffic_index()
    return idx.get(node_id)


def coverage_stats() -> dict:
    """Summary statistics for the traffic index coverage."""
    idx = load_traffic_index()
    if not idx:
        return {"indexed_nodes": 0, "status": "index not built"}
    values = list(idx.values())
    return {
        "indexed_nodes": len(idx),
        "mean_traffic_index": round(sum(values) / len(values), 3),
        "max_traffic_index":  round(max(values), 3),
        "min_traffic_index":  round(min(values), 3),
        "high_traffic_nodes": sum(1 for v in values if v >= 0.6),
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Build Bloomington traffic index")
    parser.add_argument("--force",  action="store_true", help="Re-download raw data even if cached")
    parser.add_argument("--check",  action="store_true", help="Print coverage stats only")
    args = parser.parse_args()

    if args.check:
        stats = coverage_stats()
        print(json.dumps(stats, indent=2))
        return

    print("\n[1/5] Downloading traffic count data...")
    records = download_traffic_data(force=args.force)

    print("\n[2/5] Deduplicating to most recent AADT per station...")
    stations = deduplicate(records)

    print("\n[3/5] Normalizing AADT to traffic index [0, 1]...")
    stations = normalize_aadt(stations)

    print("\n[4/5] Matching stations to OSM nodes...")
    node_index = build_node_index(stations)

    if not node_index:
        print("\nNo node index built. Run the API server first to download the graph, then re-run.")
        sys.exit(1)

    print("\n[5/5] Saving index...")
    save_index(node_index)

    print("\nDone. Coverage stats:")
    print(json.dumps(coverage_stats(), indent=2))
    print("\nRestart the API server (python api.py) to use the updated traffic index.")


if __name__ == "__main__":
    main()
