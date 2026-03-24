import os
import streamlit as st
import folium
import pandas as pd
from streamlit_folium import st_folium

st.set_page_config(
    page_title="Route Explanation System",
    page_icon="🗺️",
    layout="wide",
    initial_sidebar_state="expanded",
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

ROUTE_COLORS = {
    "Fastest Route": "#e74c3c",
    "Easiest Route": "#27ae60",
    "Balanced Route": "#2980b9",
}

ROUTE_WEIGHTS = {
    "Fastest Route": 4,
    "Easiest Route": 5,
    "Balanced Route": 4,
}


@st.cache_resource(show_spinner="Loading Bloomington road network — first run takes ~30 sec...")
def get_graph():
    from router import load_or_fetch_graph
    return load_or_fetch_graph("Bloomington, Indiana, USA")


def build_map(routes, origin_name, dest_name):
    origin_ll = LANDMARKS[origin_name]
    dest_ll = LANDMARKS[dest_name]
    center = (
        (origin_ll[0] + dest_ll[0]) / 2,
        (origin_ll[1] + dest_ll[1]) / 2,
    )
    m = folium.Map(location=center, zoom_start=14, tiles="CartoDB positron")

    for route in routes:
        color = ROUTE_COLORS.get(route["name"], "#888")
        folium.PolyLine(
            route["coords"],
            color=color,
            weight=ROUTE_WEIGHTS.get(route["name"], 4),
            opacity=0.85,
            tooltip=f"{route['icon']} {route['name']} — {route['stats']['travel_time_min']} min, {route['stats']['distance_km']} km",
        ).add_to(m)

    folium.Marker(
        origin_ll,
        tooltip=f"Start: {origin_name}",
        icon=folium.Icon(color="green", icon="play", prefix="fa"),
    ).add_to(m)
    folium.Marker(
        dest_ll,
        tooltip=f"End: {dest_name}",
        icon=folium.Icon(color="red", icon="flag", prefix="fa"),
    ).add_to(m)

    legend = """
    <div style="position:fixed;bottom:28px;left:28px;z-index:9999;
                background:white;padding:10px 14px;border-radius:8px;
                box-shadow:0 2px 8px rgba(0,0,0,0.18);font-size:13px;line-height:1.8;">
        <b>Routes</b><br>
        <span style="color:#e74c3c;font-size:16px">&#9644;</span> ⚡ Fastest<br>
        <span style="color:#27ae60;font-size:16px">&#9644;</span> 🌿 Easiest<br>
        <span style="color:#2980b9;font-size:16px">&#9644;</span> ⚖️ Balanced
    </div>"""
    m.get_root().html.add_child(folium.Element(legend))
    return m


def default_map():
    m = folium.Map(location=[39.1660, -86.5264], zoom_start=14, tiles="CartoDB positron")
    for name, (lat, lon) in LANDMARKS.items():
        folium.CircleMarker(
            [lat, lon],
            radius=6,
            color="#2980b9",
            fill=True,
            fill_opacity=0.7,
            tooltip=name,
        ).add_to(m)
    return m


# ── Session state init ────────────────────────────────────────────────────────

for key in ["routes", "origin_name", "dest_name"]:
    if key not in st.session_state:
        st.session_state[key] = None

# ── Header ────────────────────────────────────────────────────────────────────

st.title("🗺️ Route Explanation System")
st.caption("Knowledge-Based AI · Multi-Objective Routing · Case-Based Reasoning · Natural Language Explanation")

# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("Trip Setup")
    landmark_list = list(LANDMARKS.keys())
    origin_name = st.selectbox("Origin", landmark_list, index=0)
    dest_name = st.selectbox("Destination", landmark_list, index=1)

    if origin_name == dest_name:
        st.warning("Origin and destination must be different.")

    st.divider()
    st.subheader("Explanation Mode")
    use_llm = st.toggle(
        "Use Ollama (llama3.2) for richer explanation",
        value=False,
        help="Runs locally via Ollama — no API key needed. Make sure Ollama is running.",
    )

    st.divider()
    st.subheader("Case Library")
    from cbr import load_cases, get_preference_summary

    all_cases = load_cases()
    st.metric("Stored Cases", len(all_cases))
    pref = get_preference_summary()
    if pref:
        pref_icons = {"fast": "⚡ Speed-first", "low_stress": "🌿 Low-stress", "balanced": "⚖️ Balanced"}
        st.info(f"Learned preference: **{pref_icons.get(pref['dominant'], pref['dominant'])}**")
    else:
        st.caption("No preference profile yet — provide feedback to build one.")

    st.divider()
    run_btn = st.button(
        "Find Routes",
        type="primary",
        use_container_width=True,
        disabled=(origin_name == dest_name),
    )

# ── Route computation ─────────────────────────────────────────────────────────

if run_btn and origin_name != dest_name:
    with st.spinner("Computing routes..."):
        G = get_graph()
        from router import get_nearest_nodes, generate_candidate_routes

        orig_ll = LANDMARKS[origin_name]
        dest_ll = LANDMARKS[dest_name]
        orig_node, dest_node = get_nearest_nodes(G, orig_ll, dest_ll)
        routes = generate_candidate_routes(G, orig_node, dest_node)

        st.session_state.routes = routes
        st.session_state.origin_name = origin_name
        st.session_state.dest_name = dest_name

# ── Main layout ───────────────────────────────────────────────────────────────

col_map, col_panel = st.columns([3, 2], gap="medium")

if st.session_state.routes:
    routes = st.session_state.routes
    o_name = st.session_state.origin_name
    d_name = st.session_state.dest_name

    with col_map:
        st.subheader(f"{o_name}  →  {d_name}")
        m = build_map(routes, o_name, d_name)
        st_folium(m, width=700, height=480, returned_objects=[])

    with col_panel:
        st.subheader("Route Comparison")
        from explainer import compare_routes_table

        df = pd.DataFrame(compare_routes_table(routes))
        st.dataframe(df, use_container_width=True, hide_index=True)

        st.divider()

        route_labels = [f"{r['icon']}  {r['name']}" for r in routes]
        selected_label = st.radio("Select a route to explain:", route_labels)
        chosen = routes[route_labels.index(selected_label)]

        st.divider()
        st.subheader("AI Explanation")

        from explainer import explain_route, stream_llm_explanation

        if use_llm:
            st.write_stream(stream_llm_explanation(chosen, routes))
        else:
            st.markdown(explain_route(chosen, routes))

        with st.expander("View similar past cases (CBR details)"):
            from cbr import retrieve_similar_cases

            profile = chosen["profile"]
            stats = chosen["stats"]
            pref_map = {"Fastest Route": "fast", "Easiest Route": "low_stress", "Balanced Route": "balanced"}
            similar = retrieve_similar_cases(
                {**profile, "travel_time_min": stats["travel_time_min"], "distance_km": stats["distance_km"]},
                target_preference=pref_map.get(chosen["name"], "balanced"),
                top_k=3,
            )
            if similar:
                for score, case in similar:
                    st.markdown(
                        f"**{case['origin_name']} → {case['dest_name']}** "
                        f"*(similarity: {score:.2f})*"
                    )
                    st.caption(
                        f"Chose: {case['preferred_route_type']}  ·  "
                        f"{case['reason']}  ·  Rated {case['feedback_score']}/5"
                    )
                    st.divider()
            else:
                st.caption("No similar cases found yet.")

        st.divider()
        st.subheader("Your Feedback")
        st.caption("Rate this route to improve future recommendations.")

        c1, c2, c3 = st.columns(3)
        feedback_given = False
        with c1:
            if st.button("👍  Great (5)", use_container_width=True):
                from cbr import store_case
                store_case(o_name, d_name, chosen, 5)
                feedback_given = True
                st.success("Saved — case added to library.")
        with c2:
            if st.button("👌  OK (3)", use_container_width=True):
                from cbr import store_case
                store_case(o_name, d_name, chosen, 3)
                feedback_given = True
                st.info("Saved.")
        with c3:
            if st.button("👎  Poor (1)", use_container_width=True):
                from cbr import store_case
                store_case(o_name, d_name, chosen, 1)
                feedback_given = True
                st.warning("Noted — helps refine future routes.")

else:
    with col_map:
        st.info("Select an origin and destination, then click **Find Routes**.")
        st_folium(default_map(), width=700, height=480, returned_objects=[])

    with col_panel:
        st.markdown("""
### How this system works

**1. Multi-Objective Routing**
Generates three candidate routes, each optimized for a different goal:
- ⚡ **Fastest** — minimize travel time
- 🌿 **Easiest** — minimize turn difficulty and road stress
- ⚖️ **Balanced** — find the best overall trade-off

**2. Knowledge Base**
Maps raw road data to human-centric labels using domain rules:
- Turn angle + signal presence → "difficult turn" / "gentle curve"
- Road type + speed limit + lane count → "busy arterial" / "quiet side street"

**3. Case-Based Reasoning**
Retrieves similar past routes from the case library. Over time, as you provide feedback, the system learns your preferences and factors them into both route selection and explanation.

**4. Explanation Generation**
Produces structured natural language covering:
- Why this route was chosen
- Why alternatives were not selected
- Which past cases support this recommendation
- Your learned preference profile

Toggle **Ollama (llama3.2)** in the sidebar for richer, conversational explanations — runs fully locally, no API key needed.
        """)
