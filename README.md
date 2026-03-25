# Route Explanation System

**CSCI-B 551 — Elements of Artificial Intelligence**
Indiana University, Fall 2026

**Team:** Ujjwal Reddy Kalvolu, Rithvik Mysore Suresh, Divya Prasanth Paraman

---

## What this is

Most navigation apps tell you a route and a time. They don't tell you *why*. This system does.

Given a start and end point in Bloomington, Indiana, it generates three candidate routes — optimized for speed, ease of driving, or a balanced trade-off — and produces a natural language explanation for why a particular route was chosen. The explanation covers things like road character, turn complexity, and how similar routes have been handled in the past. The whole point is to make routing decisions transparent and human-centric, not just numerically optimal.

This is a Knowledge-Based AI project. The system doesn't use a neural network to make decisions. It uses explicit knowledge representations, case-based reasoning, and means-ends analysis to justify each recommendation in terms a driver actually cares about.

---

## The four components

### 1. Knowledge Base (`knowledge_base.py`)

This is where the domain knowledge lives. It answers the professor's question directly: what makes a turn "difficult"?

Every road edge from OpenStreetMap gets scored on two axes:

**Road stress** is computed from the road type (residential vs. arterial vs. highway), speed limit, and number of lanes. A residential street at 25 mph scores around 1.2/5. A four-lane primary arterial at 45 mph scores around 3.5/5. The reasoning: more lanes, higher speeds, and busier road classes require more driver attention and create more cognitive load.

**Turn difficulty** is computed from the deflection angle between consecutive road segments. A turn under 15 degrees is essentially straight. A 90-120 degree turn becomes a "sharp turn" with a base difficulty score of 2.0. On top of that, unprotected turns (no traffic signal) are penalized because they require yielding to oncoming traffic. Left turns get an additional penalty under US driving rules for the same reason. Multi-lane turns add a precision penalty.

These aren't magic numbers — they're grounded in what actually makes driving harder. The knowledge base translates all of this into labels like "quiet side street," "busy arterial," and "mostly straight, no significant turns" that mean something to a person.

### 2. Multi-Objective Router (`router.py`)

The router uses OSMnx to pull a real road network graph for Bloomington from OpenStreetMap, then runs a modified shortest-path algorithm (via NetworkX) with a weighted cost function combining:

- **Travel time** — estimated from edge length and speed
- **Road stress** — from the knowledge base
- **Turn difficulty** — from the knowledge base
- **Distance** — used lightly as a tiebreaker

By varying these weights, the same graph produces three meaningfully different paths:

| Route | Time weight | Stress weight | Turn weight |
|---|---|---|---|
| Fastest | 1.0 | 0.05 | 0.05 |
| Easiest | 0.2 | 1.0 | 1.8 |
| Balanced | 0.6 | 0.6 | 0.8 |

The graph is cached to disk after the first download so subsequent runs are instant.

### 3. Case-Based Reasoning (`cbr.py`)

The case library stores past routing decisions. Each case records the origin, destination, chosen route type, the reason it was chosen, a qualitative profile of that route, a user preference tag (fast / low_stress / balanced), and a 1-5 feedback score.

The library is seeded with 10 realistic Bloomington scenarios. When a new route is generated, the system retrieves the top matching cases using a similarity measure across four features: number of difficult turns, average road stress, distance, and travel time. Cases that match the user's apparent preference and have higher feedback scores rank higher.

Over time, as you use the system and rate routes, the case library grows and becomes more personalized. A user who consistently rates low-stress routes highly will see that reflected in future explanations — and eventually in which routes get surfaced first.

### 4. Explanation Generator (`explainer.py`)

The explainer takes the chosen route, the full list of candidate routes, and the retrieved CBR cases, then builds an explanation. Two modes:

**Template mode** (default): structured text that covers route character, turn complexity, why alternatives were rejected (with specific reasons like "2 more difficult turns" or "0.8 higher road stress"), the most relevant CBR cases, and a preference profile summary if enough feedback history exists.

**Ollama mode** (toggle in sidebar): passes the same structured data to `llama3.2` running locally via Ollama. The model produces a 3-4 sentence conversational explanation. No API key, no internet required. `llama3.2:latest` (3B parameters, 2GB) is the recommended model — it's fast and specifically good at instruction-following and natural language generation. `phi3.5:3.8b` is a solid alternative if you want slightly more careful reasoning.

---

## Running it

### Clone the repo

```bash
git clone https://github.com/ujjwalredd/Route-Explanation-System.git
cd Route-Explanation-System
```

### Prerequisites

Create and activate a virtual environment first:

```bash
python3 -m venv venv
source venv/bin/activate
```

Then install dependencies:

```bash
pip install -r requirements.txt
```

Ollama must be running if you want LLM explanations:
```bash
ollama serve
```
The model `llama3.2:latest` should already be pulled. If not: `ollama pull llama3.2`.

### Start the backend

```bash
python api.py
```

The first time it starts, it downloads and caches the Bloomington road network from OpenStreetMap (~30 sec). Every run after that is instant. The API runs at `http://localhost:8000`.

### Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173` in your browser.

### Using it

1. Pick an origin and destination from the dropdown (12 Bloomington landmarks included)
2. Click **Find Routes**
3. Three routes appear on the map and in the comparison table
4. Select a route with the radio buttons to see its explanation
5. Rate the route with the feedback buttons — this adds a new case to the CBR library
6. Toggle **Ollama (llama3.2)** in the sidebar for a conversational explanation instead of the structured template

---

## Project structure

```
Route Explanation System/
├── app.py               Streamlit UI, map rendering, feedback loop
├── knowledge_base.py    Road stress + turn difficulty rules
├── router.py            Multi-objective OSMnx routing
├── cbr.py               Case library, similarity retrieval, preference learning
├── explainer.py         Template + Ollama explanation generation
├── requirements.txt
└── data/
    ├── cases.json        Case library (auto-created on first run)
    └── graph_bloomington.pkl   Cached OSM graph (auto-created on first run)
```

---

## Design decisions worth noting

**Why Bloomington, Indiana?** Concrete, testable, and locally relevant. The professor suggested starting with specific scenarios and this gives the check-in something real to show.

**Why templates as the default, not LLM?** Templates are deterministic and inspectable, which matters for a KBAI course project. The LLM layer is additive — it can generate richer text but the structured reasoning is already visible in the template output. This also means the system works completely offline.

**Why not a learned model for routing?** That would be a different project. The point here is explainability through explicit knowledge, not accuracy through learning. The qualitative mapping rules are the knowledge acquisition component the professor asked about.

**Human-subject evaluation:** The feedback loop (👍 / 👌 / 👎) isn't just for personalization. The plan is to ask class volunteers to rate explanations from both template and Ollama modes and compare them. This gives a real evaluation metric beyond "does it run."

---

## KBAI methods implemented

| Method | Where |
|---|---|
| Knowledge representation | `knowledge_base.py` — explicit rules mapping quant → qualitative |
| Means-ends analysis | `router.py` — decomposes journey into segments, identifies obstacles |
| Case-Based Reasoning | `cbr.py` — retrieves + adapts past route cases |
| Explanation generation | `explainer.py` — constraint satisfaction + comparative explanation |
| Preference learning | `cbr.py` `get_preference_summary()` — learns from feedback over time |
