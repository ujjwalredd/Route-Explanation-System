import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from fastapi.responses import StreamingResponse

from router import get_nearest_nodes, generate_candidate_routes, load_or_fetch_graph
from cbr import load_cases, get_preference_summary, retrieve_similar_cases, store_case
from explainer import explain_route, stream_llm_explanation

app = FastAPI(title="Route AI API")

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
    "Olcott Park": (39.1534, -86.5162),
    "Bryan Park": (39.1600, -86.5180),
    "Uptown Bloomington": (39.1720, -86.5380),
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

class FeedbackRequest(BaseModel):
    origin_name: str
    dest_name: str
    chosen_route: dict
    feedback_score: int

class ExplainRequest(BaseModel):
    chosen_route: dict
    all_routes: list
    use_llm: bool = False

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
    if G is None:
        G = load_or_fetch_graph("Bloomington, Indiana, USA")
        
    orig_ll = LANDMARKS.get(req.origin_name)
    dest_ll = LANDMARKS.get(req.dest_name)
    
    if not orig_ll or not dest_ll:
        raise HTTPException(status_code=400, detail="Invalid landmarks")
        
    orig_node, dest_node = get_nearest_nodes(G, orig_ll, dest_ll)
    routes = generate_candidate_routes(G, orig_node, dest_node)
    
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
    
    return {"routes": clean_routes}

@app.post("/api/explain")
def get_explanation(req: ExplainRequest):
    if req.use_llm:
        return StreamingResponse(stream_llm_explanation(req.chosen_route, req.all_routes), media_type="text/plain")
    else:
        expl = explain_route(req.chosen_route, req.all_routes)
        return {"explanation": expl}

@app.post("/api/feedback")
def submit_feedback(req: FeedbackRequest):
    new_case = store_case(req.origin_name, req.dest_name, req.chosen_route, req.feedback_score)
    return {"status": "success", "case": new_case}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
