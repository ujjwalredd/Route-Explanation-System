import os
import json
import time
from pathlib import Path
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from fastapi.responses import StreamingResponse

from router import get_nearest_nodes, generate_candidate_routes, load_or_fetch_graph
from cbr import load_cases, get_preference_summary, retrieve_similar_cases, store_case, get_preference_drift
from explainer import explain_route, stream_llm_explanation, explain_route_template

try:
    from argumentation import build_argumentation_framework, generate_argument_explanation
    from argumentation.explainer import (
        check_faithfulness, generate_verdict, generate_counterfactual,
        compute_decisiveness, get_dimension_winners,
    )
    from kb_refinement import analyze_and_refine
    _ARG_AVAILABLE = True
except ImportError:
    _ARG_AVAILABLE = False

app = FastAPI(title="Route AI API")

LOG_DIR = Path("data") / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
EXPLANATION_MODE = os.getenv("EXPLANATION_MODE", "request").lower()


def _log_event(event: str, payload: dict):
    entry = {"event": event, "ts": time.time(), **payload}
    fname = LOG_DIR / f"{datetime.utcnow().date()}_events.jsonl"
    try:
        with fname.open("a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass

# Allow requests from Vite dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

# Pre-load graph
try:
    G = load_or_fetch_graph("Bloomington, Indiana, USA")
except Exception as e:
    G = None
    print("Warning: Could not load graph initially.", e)

class RouteRequest(BaseModel):
    origin_name: str
    dest_name: str
    departure_hour: int | None = None

class FeedbackRequest(BaseModel):
    origin_name: str
    dest_name: str
    chosen_route: dict
    feedback_score: int

class ExplainRequest(BaseModel):
    chosen_route: dict
    all_routes: list
    use_llm: bool = False
    mode: str | None = None  # "template", "argumentation", "llm", or None to follow env/default

class ArgueRequest(BaseModel):
    chosen_route: dict
    all_routes: list

class KBRefineRequest(BaseModel):
    dry_run: bool = True


class StudyResponse(BaseModel):
    participant_id: str
    condition: str | None = None   # template | argumentation | llm (legacy)
    mode: str | None = None        # same as condition, sent by new UI
    trust: int
    clarity: int
    safety: int
    chosen_route_name: str | None = None
    route_name: str | None = None  # alias from new UI
    origin: str | None = None
    destination: str | None = None
    preferred_route_name: str | None = None
    notes: str | None = None

@app.get("/api/landmarks")
def get_landmarks():
    return [{"name": k, "coords": v} for k, v in LANDMARKS.items()]

@app.get("/api/cases/summary")
def get_cases_summary():
    cases = load_cases()
    pref = get_preference_summary()
    return {"total_cases": len(cases), "preference": pref}

@app.post("/api/routes")
def get_routes(req: RouteRequest):
    global G
    start_ts = time.perf_counter()
    if G is None:
        G = load_or_fetch_graph("Bloomington, Indiana, USA")
        
    orig_ll = LANDMARKS.get(req.origin_name)
    dest_ll = LANDMARKS.get(req.dest_name)
    
    if not orig_ll or not dest_ll:
        raise HTTPException(status_code=400, detail="Invalid landmarks")
    if req.origin_name == req.dest_name:
        raise HTTPException(status_code=400, detail="Origin and destination must be different")
        
    orig_node, dest_node = get_nearest_nodes(G, orig_ll, dest_ll)
    routes = generate_candidate_routes(G, orig_node, dest_node, hour=req.departure_hour)
    
    # Strip non-serializable objects like Shapely LineStrings from networkx edges
    clean_routes = []
    for r in routes:
        clean_r = {k: v for k, v in r.items() if k not in ["path", "edges"]}
        clean_edges = []
        for edge in r.get("edges", []):
            clean_edge = {ek: ev for ek, ev in edge.items() if ek != "geometry"}
            clean_edges.append(clean_edge)
        clean_r["edges"] = clean_edges
        clean_routes.append(clean_r)

    _log_event("routes_generated", {
        "origin": req.origin_name,
        "dest": req.dest_name,
        "route_count": len(clean_routes),
        "latency_ms": round((time.perf_counter() - start_ts) * 1000, 1),
    })
    
    return {"routes": clean_routes}

@app.post("/api/explain")
def get_explanation(req: ExplainRequest):
    start_ts = time.perf_counter()

    def resolve_mode():
        if EXPLANATION_MODE != "request":
            return EXPLANATION_MODE
        if req.mode:
            return req.mode.lower()
        if req.use_llm:
            return "llm"
        return "argumentation"

    mode = resolve_mode()

    if mode == "llm":
        stream = stream_llm_explanation(req.chosen_route, req.all_routes)
        resp = StreamingResponse(stream, media_type="text/plain")
    elif mode == "template":
        def _template_stream():
            yield explain_route_template(req.chosen_route, req.all_routes)
        resp = StreamingResponse(_template_stream(), media_type="text/plain")
    else:  # argumentation (default)
        def _af_stream():
            yield explain_route(req.chosen_route, req.all_routes)
        resp = StreamingResponse(_af_stream(), media_type="text/plain")

    _log_event("explain", {
        "mode": mode,
        "route": req.chosen_route.get("name"),
        "latency_ms": round((time.perf_counter() - start_ts) * 1000, 1),
    })
    return resp

@app.post("/api/feedback")
def submit_feedback(req: FeedbackRequest):
    new_case = store_case(req.origin_name, req.dest_name, req.chosen_route, req.feedback_score)
    return {"status": "success", "case": new_case}


@app.post("/api/study/response")
def submit_study_response(req: StudyResponse):
    record = req.dict()
    # Normalize: mode/condition are the same field; route_name/chosen_route_name are the same
    record["condition"] = record.get("condition") or record.get("mode") or "unknown"
    record["chosen_route_name"] = record.get("chosen_route_name") or record.get("route_name")
    record["ts"] = time.time()
    out_path = Path("data") / "study_responses.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("a") as f:
        f.write(json.dumps(record) + "\n")
    _log_event("study_response", {"participant_id": record["participant_id"], "condition": record["condition"], "chosen_route_name": record["chosen_route_name"]})
    return {"status": "recorded"}

# ---------------------------------------------------------------------------
# Argumentation endpoints (research / debug layer)
# ---------------------------------------------------------------------------

@app.post("/api/argue")
def argue_routes(req: ArgueRequest):
    """
    Build and evaluate an Argumentation Framework for the given routes.

    Returns the full argument trace (accepted/rejected/undecided arguments,
    attack relations, grounded extension) plus a natural-language explanation
    derived from that trace.

    This endpoint exposes the argumentation reasoning layer for research
    inspection, evaluation studies, and the professor demo.
    """
    if not _ARG_AVAILABLE:
        raise HTTPException(status_code=503, detail="Argumentation module not available.")

    # Retrieve CBR cases for every route
    pref_map = {"Fastest Route": "fast", "Easiest Route": "low_stress", "Balanced Route": "balanced"}
    cbr_per_route = {}
    for route in req.all_routes:
        profile = route.get("profile", {})
        stats = route.get("stats", {})
        pref = pref_map.get(route["name"], "balanced")
        cbr_per_route[route["name"]] = retrieve_similar_cases(
            {**profile,
             "travel_time_min": stats.get("travel_time_min", 0),
             "distance_km": stats.get("distance_km", 0)},
            target_preference=pref,
            top_k=3,
        )

    af = build_argumentation_framework(req.all_routes, cbr_per_route)
    af.compute_grounded_extension()
    pref_summary = get_preference_summary()
    explanation = generate_argument_explanation(
        af, req.chosen_route, req.all_routes, pref_summary=pref_summary
    )
    recommended = af.recommend()
    faithfulness = check_faithfulness(af, req.all_routes)
    semantics = af.compare_semantics()
    verdict = generate_verdict(af, req.chosen_route, req.all_routes)
    counterfactual = generate_counterfactual(af, req.chosen_route, req.all_routes)
    decisiveness = compute_decisiveness(af, req.chosen_route, req.all_routes)
    dim_winners = get_dimension_winners(req.all_routes)

    _log_event("argue", {
        "route": req.chosen_route.get("name"),
        "accepted": af.to_dict()["counts"]["accepted"],
        "faithfulness_score": faithfulness["score"],
    })

    return {
        "argumentation_framework": af.to_dict(),
        "explanation": explanation,
        "chosen_route_name": req.chosen_route.get("name"),
        "recommended_by_af": recommended,
        "af_agrees_with_chosen": recommended == req.chosen_route.get("name"),
        "faithfulness": faithfulness,
        "semantics_comparison": semantics,
        "verdict": verdict,
        "counterfactual": counterfactual,
        "decisiveness": decisiveness,
        "dimension_winners": dim_winners,
    }


@app.get("/api/argue/history")
def argue_history():
    """Return historical AF argument counts from event logs (last 30 days)."""
    history = []
    try:
        for log_file in sorted(LOG_DIR.glob("*_events.jsonl"))[-30:]:
            with log_file.open() as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                        if entry.get("event") == "argue":
                            history.append({
                                "ts": entry["ts"],
                                "route": entry.get("route"),
                                "accepted": entry.get("accepted", 0),
                                "faithfulness": entry.get("faithfulness_score", None),
                            })
                    except Exception:
                        pass
    except Exception:
        pass
    return {"history": history, "count": len(history)}


@app.get("/api/preference-drift")
def preference_drift():
    """Return preference drift metrics — how much user preferences have shifted recently."""
    drift = get_preference_drift(window=10)
    if drift is None:
        return {"status": "insufficient_data", "message": "Need at least 20 rated cases to compute drift."}
    return {"status": "ok", **drift}


@app.get("/api/kb/params")
def get_kb_params():
    """Return current knowledge base parameters from kb_params.json."""
    params_path = os.path.join("data", "kb_params.json")
    if not os.path.exists(params_path):
        return {"status": "using_defaults", "params": None}
    with open(params_path) as f:
        return {"status": "loaded", "params": json.load(f)}


@app.post("/api/kb/refine")
def refine_kb(req: KBRefineRequest):
    """
    Analyse accumulated CBR cases and detect KB parameter miscalibration.

    dry_run=true  (default): returns signals without modifying kb_params.json.
    dry_run=false           : applies changes and increments KB version.

    After a non-dry-run refinement, the in-memory KB is also reloaded so
    the router and argument generator use updated values immediately.
    """
    if not _ARG_AVAILABLE:
        raise HTTPException(status_code=503, detail="KB refinement module not available.")

    result = analyze_and_refine(dry_run=req.dry_run)

    # Reload in-memory KB if changes were applied
    if result.applied:
        try:
            from knowledge_base import reload_kb_params
            reload_kb_params()
            from argumentation.generator import reload_params
            reload_params()
        except Exception:
            pass  # non-critical — server restart also works

    return {
        "status": result.summary,
        "dry_run": result.dry_run,
        "applied": result.applied,
        "cases_analyzed": result.cases_analyzed,
        "kb_version_before": result.kb_version_before,
        "kb_version_after": result.kb_version_after,
        "signals": [
            {
                "parameter": s.parameter_path,
                "current": s.current_value,
                "proposed": s.proposed_value,
                "confidence": s.confidence,
                "direction": s.direction,
                "evidence_count": s.evidence_count,
                "rationale": s.rationale,
            }
            for s in result.signals
        ],
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
