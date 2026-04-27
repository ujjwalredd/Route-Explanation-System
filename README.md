# Route Explanation System

**CSCI-B 551 — Elements of Artificial Intelligence**
Indiana University, Fall 2026

**Team:** Ujjwal Reddy Kalvolu Sreenivasa Reddy, Rithvik Mysore Suresh, Divya Prasanth Paraman

---

## What this is

Most navigation apps tell you a route and a time. They don't tell you *why*. This system does.

Given a start and end point in Bloomington, Indiana, it generates three candidate routes — optimized for speed, ease of driving, or a balanced trade-off — and produces a structured natural-language explanation for why a particular route was chosen. The explanation is grounded in a formal **argumentation framework**: route properties generate pro/con arguments, arguments attack each other, and a grounded-semantics solver determines which arguments survive.

This is a Knowledge-Based AI project. The system does not use a neural network to make decisions. It uses explicit knowledge representations, real traffic data, case-based reasoning, formal argumentation, and adaptive knowledge refinement to justify each recommendation in terms a driver actually cares about.

---

## Architecture

```
OpenStreetMap (Bloomington road network)
        +
City of Bloomington Traffic Counts (AADT per intersection)
        ↓
Knowledge Base — parameterized rules (kb_params.json)
  road stress scores blended with observed traffic volume,
  turn difficulty rules, turn penalties, argument thresholds
  time-of-day traffic multipliers (morning/evening peak)
        ↓
Multi-Objective Router — weighted shortest path (3 route objectives)
  + edge-penalty diversity guarantee for geometrically distinct routes
        ↓
Argument Generator — pro/con arguments per route × dimension
  (time, road stress, turn complexity, CBR evidence)
  + segment-level worst-case annotation per argument
        ↓
Argumentation Framework — Dung grounded + preferred + stable semantics
  strength-weighted attack resolution, faithfulness checker
        ↓
Explanation Generator — traces winning argument chain → natural language
  + verdict sentence, counterfactual, decisiveness score, dimension winners
  + interactive SVG argument graph in UI
        ↑
User Feedback → CBR Case Library → KB Refinement Analyzer
  4 analyzers: stress, turn penalties, argument thresholds, attack weights
  preference drift detection across time windows
  detects miscalibrated rules and updates kb_params.json
```

---

## Benchmark Results

All metrics below come from running `python benchmark.py --sample 40 --seed 42` across **40 landmark pairs** (out of 380 directed pairs). Run date: **April 20, 2026**.

| Metric | Value |
|---|---|
| Pairs evaluated | 40 |
| 3 distinct routes generated | **40 / 40 (100%)** |
| 2 distinct routes | 0 / 40 (0%) |
| Pairs with <=1 route generated | 0 / 40 (0%) |
| Mean route diversity (Jaccard) | **0.752** |
| Pareto non-dominated recommendation | **40 / 40 (100%)** |
| Mean accepted arguments / query | 4.8 |
| Mean successful attacks / query | 7.2 |
| Mean faithfulness score | **1.000** |
| All 3 semantics agree | **100%** |

> **Faithfulness 1.000** — under the current threshold-based checker, all accepted pro-arguments are consistent with the route statistics and argument thresholds that generated them.

> **Jaccard diversity 0.752** means on average about 75% of road nodes across two candidate routes are non-overlapping — confirming the edge-penalty diversity mechanism still produces meaningfully distinct options.

> **Pareto 100%** — the final recommendation step now applies a Pareto sanity check, so the seeded sample does not return any strictly dominated route.

---

## Ablation Study

Comparison of 4 system configurations across 20 sampled pairs. Each configuration adds one component on top of the baseline.

| Configuration | Faithfulness | Pareto Rate | 3-Route % |
|---|---|---|---|
| Baseline (no CBR, no traffic) | 1.000 | **100%** | 100% |
| + Traffic data only | 1.000 | 95% | 100% |
| + CBR only | 1.000 | **100%** | 100% |
| **Full system** | **1.000** | **100%** | **100%** |

> In the seeded 20-pair ablation sample, baseline already achieves 100% Pareto non-domination. Traffic data alone shows a slight dip (95%) as it reshapes stress scores on one edge case; when combined with CBR the full system returns to 100%. All configurations achieve perfect faithfulness and 3-route diversity.

---

## KB Convergence Results

Simulated 60 feedback rounds using `python simulate_feedback.py --rounds 60`. Parameters adjust via the refinement loop (learning rate 0.05). The script now records both per-round snapshots and checkpoint-based convergence metadata in `data/convergence.json`.

| Parameter | Start | End (round 60) | First change round |
|---|---|---|---|
| `stress_pro_ceiling` | 2.000 | 1.909 | **21** |
| `left_turn_penalty` | 0.300 | 0.666 | **11** |

> Using the current convergence criterion — **< 0.005 variation in `stress_pro_ceiling` across 5 refinement checkpoints after the first stress update** — the simulation does **not** converge within 60 rounds. The first parameter change appears at round 11, `stress_pro_ceiling` first moves at round 21, and `left_turn_penalty` rises from 0.30 → 0.67 as the simulated user keeps favoring easier turns.

---

## The seven components

### 1. Knowledge Base (`knowledge_base.py` + `data/kb_params.json`)

All scoring rules are stored in `data/kb_params.json` and loaded at startup, making them inspectable, editable, and — critically — updatable by the adaptive refinement module without restarting the server.

**Road stress** is scored from three sources blended together:
- *Road type:* a residential street scores 1.2/5; a primary arterial scores 3.5/5
- *Speed and lanes:* high-speed or multi-lane roads add modifiers (up to +0.6 for 55+ mph)
- *Observed traffic volume:* AADT from the City of Bloomington traffic count dataset is log-normalized to [0, 1] and blended in at 30% weight (`traffic_blend_weight` in `kb_params.json`)
- *Time-of-day:* morning peak (7–9am) multiplies traffic stress by 1.4×; evening peak (4–7pm) by 1.5×

The 70/30 heuristic-to-traffic blend and all peak multipliers are KB parameters tunable by the adaptive refinement loop.

**Turn difficulty** is computed from the deflection angle between consecutive road segments. Turns over 90° become "sharp" (base score 2.0). Unprotected turns add a 0.5 penalty; left turns across traffic add 0.3; multi-lane turns add 0.3 more.

**Latency note:** `_KB` is loaded once at module import time into a module-level dict. All edge scoring during Dijkstra is pure in-memory arithmetic — zero file I/O per call.

### 2. Traffic Data Integration (`traffic_data.py`)

Downloads all 2,625 AADT records from the City of Bloomington Open Data portal, deduplicates to 1,236 unique measurement stations (most recent year per location), log-normalizes against the 95th-percentile count to cap outliers, then matches each station to the nearest OSM road node using `ox.nearest_nodes`. Results are cached to `data/traffic_index.json` (791 matched nodes).

### 3. Multi-Objective Router (`router.py`)

Uses OSMnx to pull the Bloomington road graph from OpenStreetMap and NetworkX for weighted shortest-path search. Three routes are generated by varying the cost function:

| Route | Time weight | Stress weight | Turn weight |
|---|---|---|---|
| Fastest | 1.0 | 0.05 | 0.05 |
| Easiest | 0.2 | 1.0 | 1.8 |
| Balanced | 0.6 | 0.6 | 0.8 |

When weight perturbation fails to produce a geometrically distinct third route, an **edge-penalty diversity pass** re-runs Dijkstra with a 4× cost multiplier on edges already used in accepted routes. After fixing short-path duplicate suppression, the seeded benchmark sample now achieves a **100% 3-distinct-route rate**.

Accepts an optional `hour` parameter for time-of-day-aware routing (passed from `departure_hour` in the route request).

### 4. Case-Based Reasoning (`cbr.py`)

Stores past routing decisions as cases: origin, destination, chosen route type, route profile, user preference tag, and feedback score. Similarity is computed across four features: difficult turns, average road stress, distance, and travel time.

The library is seeded with 20 realistic Bloomington scenarios. **Preference drift detection** (`get_preference_drift`) compares the distribution of high-rated cases in the most recent 10-case window against all older cases using L1 distance. A drift score above 0.20 signals shifted preferences — reported via `/api/preference-drift`.

### 5. Argumentation Framework (`argumentation/`)

**The novel contribution.** No prior work applies formal argumentation to route explanation. This module implements a Dung-style Abstract Argumentation Framework (AF) with strength-weighted grounded semantics.

**Arguments** are generated for each route across four dimensions:
- `time` — is this route time-efficient relative to alternatives?
- `stress` — do its roads fall within the safe stress ceiling?
- `turns` — does it avoid difficult navigation maneuvers?
- `cbr` — does past experience support or warn against this route type?

Argument strength values are **normalized relative to the actual route set** on each query. The fastest route always scores 1.0 on time strength; the slowest scores near 0. **Segment-level annotation** identifies the worst individual segment per argument (e.g., "avg stress 2.1/5 (peak: primary road at 3.5/5)").

**Three semantics are computed and compared** (for RQ2):
- *Grounded* — unique, skeptically justified; used for recommendations
- *Preferred* — all maximal admissible sets; exhaustive up to 20 arguments
- *Stable* — conflict-free sets attacking every outside argument

All three semantics agree **100% of the time** in the seeded 40-pair benchmark, validating grounded semantics as the primary recommendation mechanism.

The final route recommendation applies a lightweight **Pareto sanity check** on top of the AF scores so a strictly dominated route is not returned when an undominated AF-supported alternative exists.

**Structured explainability** (new):
- `generate_verdict()` — one-sentence bottom-line: "Balanced Route was recommended because time: lowest travel time, and stress: quietest roads."
- `generate_counterfactual()` — "If travel time were weighted more heavily, Fastest Route would be preferred instead (0.5 min faster)."
- `compute_decisiveness()` — [0, 1] confidence margin between chosen route and runner-up
- `get_dimension_winners()` — which route wins on each dimension (time / stress / turns)

**Argument graph visualization:** the frontend renders a live SVG graph showing every argument node (green=IN, red=OUT, gray=UNDECIDED) and every attack relation (solid=succeeded, dashed=failed), grouped by route in columns.

### 6. Adaptive KB Refinement (`kb_refinement.py`)

Closes the loop between case-based experiential learning and symbolic rule-based knowledge. Four analyzers run on accumulated cases:

- **Stress calibration:** adjust `road_stress_scores` when rated trips diverge from the baseline
- **Turn penalty calibration:** increase `left_turn_penalty` when hard-turn routes are consistently rated lower
- **Argument threshold calibration:** shift `stress_pro_ceiling` toward observed high-rated trip stress
- **Attack weight calibration:** adjust `self_stress_to_time` and `self_turns_to_time` based on user acceptance patterns

In the current 60-round simulation, `left_turn_penalty` starts adapting at round 11 and `stress_pro_ceiling` at round 21; under the stricter checkpoint-based criterion above, convergence is not yet reached within 60 rounds. All adjustments are capped and stepped conservatively (learning rate 0.05).

### 7. Explanation UI (`frontend/`)

Three explanation modes switchable via tabs in the UI:
- **Argumentation** — structured argument trace with verdict, dimension chips, decisiveness bar, SVG graph
- **Template** — deterministic rule-based prose, fastest to render
- **LLM** — conversational prose grounded in the argument trace (requires Ollama)

**Study mode** (`?study=true`): activates a bottom panel after each explanation with three Likert scales (Trust / Clarity / Safety, 1–5). Responses are stored to `data/study_responses.jsonl` with participant ID, mode, and route context — directly answering RQ4.

**Time-of-day selector** in the sidebar lets users pick departure time (morning peak, evening peak, or off-peak), which feeds into the traffic stress computation.

---

## Running it

### Prerequisites

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Ollama (optional, for LLM explanations):
```bash
ollama serve
ollama pull llama3.2
```

### Build the traffic index (one time)

```bash
python traffic_data.py
```

Downloads 2,625 AADT records, matches to OSM nodes, caches `data/traffic_index.json`. If no cached graph exists yet, run `python api.py` once first; `traffic_data.py` will then reuse the cached versioned graph file automatically.

### Start the backend

```bash
python api.py
```

The first run downloads and caches the Bloomington road network (~30 sec). Every subsequent run is instant. API at `http://localhost:8000`.

### Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. For study mode: `http://localhost:5173?study=true`.

### Run the benchmark

```bash
python benchmark.py --sample 40 --seed 42   # reproducible 40-pair sample (~5 min)
python benchmark.py               # full: all 380 landmark pairs (~45 min)
python benchmark.py --report      # print summary from saved results
```

### Run KB convergence simulation

```bash
python simulate_feedback.py --rounds 60
```

Simulates feedback rounds and outputs `data/convergence.json` with per-round snapshots, refinement checkpoints, and convergence metadata.

### Run ablation study

```bash
python ablation.py --sample 20 --seed 42
```

Compares 4 configurations (baseline / +traffic / +cbr / full_system) across sampled pairs.

---

## Using the app

1. Pick an origin and destination from the dropdown (20 Bloomington landmarks)
2. Optionally select a departure time (morning peak / evening peak / off-peak)
3. Click **Find Routes**
4. Three routes appear on the map — each color-coded, with z-ordered highlighting on selection
5. Select a route — the Explanation panel shows:
   - **Verdict** — one-sentence bottom line
   - **Dimension chips** — which dimensions this route wins (Best Time / Best Stress / Best Turns)
   - **Decisiveness bar** — how confidently the AF chose this route over alternatives
   - **Mode tabs** — switch between Argumentation / Template / LLM explanations
   - **Argument graph** — live SVG showing the full AF with attack relations
   - **Counterfactual** — what would flip the recommendation
   - **Faithfulness badge** — checks accepted arguments against route statistics and argument thresholds
   - **Semantics agreement** — whether grounded/preferred/stable all agree
6. Rate the route — adds a CBR case, eventually triggers KB refinement
7. Study mode (`?study=true`) — shows Trust / Clarity / Safety Likert scales after each explanation

---

## API endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/landmarks` | List all 20 landmarks with coordinates |
| POST | `/api/routes` | Generate 3 candidate routes (accepts `departure_hour`) |
| POST | `/api/explain` | Argumentation, template, or LLM explanation (streaming) |
| POST | `/api/argue` | Full AF trace + faithfulness + semantics + verdict + counterfactual |
| POST | `/api/feedback` | Submit route rating (adds CBR case) |
| GET | `/api/preference-drift` | Preference shift metrics over recent vs. historical cases |
| GET | `/api/argue/history` | Historical AF argument counts from event logs |
| GET | `/api/kb/params` | View current KB parameters |
| POST | `/api/kb/refine` | Run KB refinement analyser (`dry_run` flag) |
| GET | `/api/cases/summary` | CBR library size and preference distribution |
| POST | `/api/study/response` | Record study participant ratings (trust/clarity/safety) |

### `/api/argue` response structure

```json
{
  "argumentation_framework": {
    "arguments": [
      {
        "id": "easiest_route:stress:pro",
        "route": "Easiest Route",
        "dimension": "stress",
        "polarity": "pro",
        "strength": 0.74,
        "claim": "Easiest Route uses quiet side street roads (avg stress 1.3/5, peak: residential at 1.2/5)...",
        "status": "IN"
      }
    ],
    "attacks": [
      {
        "attacker_id": "fastest_route:stress:con",
        "target_id": "fastest_route:time:pro",
        "kind": "self_undermining",
        "weight": 0.75,
        "succeeds": true
      }
    ],
    "grounded_extension": ["easiest_route:stress:pro", "easiest_route:turns:pro"],
    "counts": { "accepted": 5, "rejected": 3, "undecided": 1, "attacks_succeeded": 3 }
  },
  "explanation": "**Easiest Route** *(Argumentation-Based Reasoning)*\n...",
  "verdict": "Easiest Route was recommended because stress: lowest road stress, and turns: no difficult turns.",
  "counterfactual": "If time were weighted more heavily, Fastest Route would be preferred instead (3.5 min faster).",
  "decisiveness": 0.72,
  "dimension_winners": { "time": "Fastest Route", "stress": "Easiest Route", "turns": "Easiest Route" },
  "recommended_by_af": "Easiest Route",
  "af_agrees_with_chosen": true,
  "faithfulness": { "score": 1.0, "total_checked": 5, "violations": 0 },
  "semantics_comparison": {
    "grounded": { "extension": ["easiest_route:stress:pro", "..."], "recommendation": "Easiest Route" },
    "preferred": { "count": 1, "recommendations": ["Easiest Route"] },
    "stable":   { "count": 1, "recommendations": ["Easiest Route"] },
    "all_semantics_agree": true,
    "recommendations": { "grounded": "Easiest Route", "preferred": "Easiest Route", "stable": "Easiest Route" }
  }
}
```

---

## Project structure

```
Route Explanation System/
├── api.py                  FastAPI server — all endpoints
├── knowledge_base.py       Road stress + turn difficulty scoring (loads from kb_params.json)
├── router.py               Multi-objective OSMnx routing + diversity guarantee + time-of-day
├── cbr.py                  Case library, similarity retrieval, preference drift detection
├── explainer.py            Template + Ollama explanations (uses argumentation engine)
├── kb_refinement.py        Adaptive KB rule refinement from CBR feedback (4 analyzers)
├── traffic_data.py         Bloomington AADT download, normalization, OSM node matching
├── benchmark.py            Automated evaluation (route diversity, AF metrics, faithfulness)
├── simulate_feedback.py    KB convergence curve simulation (60 rounds)
├── ablation.py             4-configuration ablation study runner
├── requirements.txt
│
├── argumentation/          Argumentation framework package
│   ├── __init__.py         Public API exports
│   ├── framework.py        Argument, Attack, AF — grounded + preferred + stable semantics
│   ├── generator.py        Route profiles + CBR cases → populated AF (segment-level claims)
│   └── explainer.py        Argument trace → NL + faithfulness + verdict + counterfactual
│
├── data/
│   ├── kb_params.json      Parameterized KB rules (stress, turns, thresholds, attack weights, time-of-day)
│   ├── cases.json          CBR case library (auto-seeded, grows with feedback)
│   ├── traffic_index.json  OSM node → normalized AADT traffic index (791 nodes)
│   ├── traffic_raw.json    Raw downloaded AADT records (2,625 rows, cached)
│   ├── benchmark_results.json  Latest benchmark run results
│   ├── ablation_results.json   Ablation study results
│   ├── convergence.json    KB convergence snapshots + checkpoint metadata
│   ├── study_responses.jsonl   Study participant ratings (appended per response)
│   └── graph_bloomington__indiana__usa_v1.pkl   Cached OSM road graph
│
└── frontend/               React + TypeScript + MapLibre GL UI
    └── src/
        ├── App.tsx         Routes state, study mode, departure time, mode switching
        └── components/
            ├── Map.tsx         Route rendering, stable layer IDs, z-ordered selection
            ├── Sidebar.tsx     Origin/destination/departure time selection, CBR summary
            ├── Explanation.tsx Full explainability panel (tabs, SVG graph, verdict, counterfactual)
            ├── RouteCard.tsx   Per-route stats card
            └── SkeletonCard.tsx Loading state
```

---

## KBAI methods implemented

| Method | Where | Novel contribution |
|---|---|---|
| Knowledge representation | `knowledge_base.py`, `kb_params.json` | Parameterized, updatable rules blended with real traffic data + time-of-day |
| Means-ends analysis | `router.py` | Weighted multi-objective decomposition + diversity guarantee |
| Case-Based Reasoning | `cbr.py` | 20-case seeded library, preference learning, drift detection |
| Formal argumentation | `argumentation/` | **First application of Dung AF to route explanation** |
| Multi-semantics comparison | `argumentation/framework.py` | Grounded + preferred + stable with strength-weighted attacks |
| Adaptive KB refinement | `kb_refinement.py` | **First use of CBR feedback to update KB rules and attack weights** |
| Explanation generation | `explainer.py` + `argumentation/explainer.py` | Argument-traced NL + verdict + counterfactual + faithfulness |
| Real data integration | `traffic_data.py` | AADT traffic counts blended into heuristic stress scoring |
| Explanation UI | `frontend/` | SVG argument graph, mode tabs, study mode, decisiveness bar |

---

## Research questions

1. **RQ1 — Representation:** What argument scheme best formalizes route trade-offs and maps road features to argument strength?
   > *Answer:* Dung-style AF with normalized strength scores and segment-level claims. In the seeded 40-pair benchmark, the current faithfulness checker scores **1.000**, meaning accepted pro-arguments match the route statistics and thresholds used to generate them.

2. **RQ2 — Semantics:** Which Dung semantics (grounded, preferred, stable) produces the most accurate and interpretable route recommendations?
   > *Answer:* All three semantics agree 100% of the time in the benchmark. Grounded semantics is recommended as primary: it always yields a unique extension and is the most computationally efficient.

3. **RQ3 — Learning:** How many feedback cases does the KB refinement loop need before converging to stable parameters?
   > *Answer:* In the current 60-round simulation, the first parameter change appears at **round 11**, `stress_pro_ceiling` first changes at **round 21**, and the tracked parameters end at `stress_pro_ceiling = 1.909` and `left_turn_penalty = 0.666`. Under the stricter checkpoint-based convergence test, the system does **not** fully converge within 60 rounds.

4. **RQ4 — Explanation Quality:** Do argumentation-traced explanations increase user trust and comprehension compared to template and LLM explanations?
   > *Target:* Human-subject study using `?study=true` mode. Collect Trust / Clarity / Safety Likert ratings per mode. Compare mean scores across argumentation / template / LLM.

5. **RQ5 — Argument Composition:** Can segment-level arguments be composed into route-level structures without combinatorial explosion?
   > *Answer:* Yes. In the seeded 40-pair benchmark, the system averages **4.8 accepted arguments** and **7.2 successful attacks** per query. The generator still produces at most 12 arguments per query (4 dimensions × 3 routes × 2 polarities), well within the exhaustive preferred/stable semantics threshold (20 arguments).

6. **RQ6 — Preference Drift:** Does KB refinement track shifting user preferences, or does it lag behind?
   > *Target:* Requires longitudinal study data. Preference drift detection (`get_preference_drift`) is operational; expose its output over a study period.

7. **RQ7 — Traffic Grounding:** Does blending real AADT data into stress scores improve route quality vs. heuristic-only scoring?
   > *Answer:* In the seeded 20-pair ablation, **traffic-only** reaches **95%** Pareto non-domination, while **baseline**, **+CBR**, and the **full system** each reach **100%**. Traffic changes the frontier on one edge case, and adding CBR recovers the full score.

---

## Design decisions

**Why templates as default, not LLM?** Templates are deterministic and inspectable. The LLM layer is additive — it generates richer prose but the structured argumentation trace is already the primary artifact.

**Why Dung grounded semantics as the primary?** Grounded semantics always yields a unique extension (no ambiguity) and is the most skeptically conservative. This maps well to the safety-oriented domain of route recommendation. Preferred and stable semantics are computed alongside for the RQ2 comparison.

**Why Bloomington, Indiana?** Concrete, testable, and locally relevant. The 20 landmarks cover campus, downtown, residential areas, parks, and commercial zones. The City of Bloomington publishes real AADT traffic counts as open data.

**Why separate `kb_params.json` from code?** Separating parameters from logic enables the KB refinement loop to update values without code changes, enables reproducibility (version-tracked), and makes the knowledge acquisition process transparent.

**Why log-normalize AADT?** Traffic volume spans several orders of magnitude — College Ave at 14,000 vehicles/day vs. a residential street at 200. Log normalization prevents outliers from compressing all other values toward zero.

**Why cache `_KB` at module import?** `score_edge` is called for every graph edge during Dijkstra (thousands of calls per route). Any file I/O per call would make routing prohibitively slow. The module-level cache ensures zero I/O during path search.

---

## Datasets and credits

### OpenStreetMap

Road network data for Bloomington, Indiana downloaded via [OSMnx](https://osmnx.readthedocs.io/) from [OpenStreetMap](https://www.openstreetmap.org/).

> OpenStreetMap contributors, *OpenStreetMap*, available under the Open Database License (ODbL). https://www.openstreetmap.org/copyright

### City of Bloomington — Traffic Counts

Annual Average Daily Traffic (AADT) counts at intersections and road segments throughout Monroe County, published by the City of Bloomington Department of Public Works.

> City of Bloomington, Indiana. *Traffic Counts*. Bloomington Open Data Portal, 2025.
> https://data.bloomington.in.gov/Transportation/Traffic-Counts/dcr5-fg4c/about_data
>
> Data accessed via Socrata Open Data API (SODA 2.0):
> https://data.bloomington.in.gov/resource/dcr5-fg4c.json
>
> License: Public Domain (City of Bloomington Open Data)

**Coverage:** 2,625 AADT records across 1,236 unique measurement stations. After deduplication, log-normalization (95th-percentile cap), and OSM node matching, 791 road nodes in the Bloomington graph are traffic-informed.
