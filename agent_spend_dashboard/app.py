"""
app.py  –  ADK Agent Engine Spend Dashboard
Analyzes compute + LLM token costs for agents running on Vertex AI Agent Engine.

Run locally:
    export GCP_PROJECT_ID=my-project
    streamlit run app.py

Deploy to Cloud Run: see deploy.sh
"""

import os
import logging
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta, timezone
from collections import defaultdict

from src.agent_registry import list_agent_engines
from src.monitoring     import get_metrics_for_agents
from src.token_metrics  import get_token_metrics
from src.pricing        import calculate_costs, MODEL_PRICING, COMPUTE_PRICING
from src.style_system   import CSS_STYLES, SIDEBAR_BRAND_HTML, render_hero_card, render_card_start, render_card_end

logging.basicConfig(level=logging.INFO)

def get_spend_timeseries(agents_list, all_runtime, all_costs):
    ts_data = defaultdict(float)
    for agent in agents_list:
        eid = agent["id"]
        m = all_runtime[eid]
        c = all_costs[eid]
        
        cpu_pts = m.get("cpu_timeseries", [])
        mem_pts = m.get("memory_timeseries", [])
        req_pts = m.get("request_count_timeseries", [])
        
        cpu_dict = {p["timestamp"]: p["value"] for p in cpu_pts}
        mem_dict = {p["timestamp"]: p["value"] for p in mem_pts}
        req_dict = {p["timestamp"]: p["value"] for p in req_pts}
        
        all_ts = set(cpu_dict.keys()) | set(mem_dict.keys()) | set(req_dict.keys())
        total_agent_requests = sum(req_dict.values()) or 1.0
        total_agent_token_cost = c["token_cost"]
        
        for ts in all_ts:
            cpu_sec = cpu_dict.get(ts, 0.0)
            mem_gbs = mem_dict.get(ts, 0.0)
            reqs = req_dict.get(ts, 0.0)
            
            comp_cost = (cpu_sec / 3600.0) * COMPUTE_PRICING["vcpu_per_hour"] + (mem_gbs / 3600.0) * COMPUTE_PRICING["memory_per_hour"]
            tok_cost = (reqs / total_agent_requests) * total_agent_token_cost
            ts_data[ts] += comp_cost + tok_cost
            
    sorted_pts = [{"timestamp": ts, "value": val} for ts, val in ts_data.items()]
    sorted_pts.sort(key=lambda x: x["timestamp"])
    return sorted_pts


# ── Page setup ─────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Agent Engine Spend Dashboard",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(CSS_STYLES, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR – Configuration & Controls
# ══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown(SIDEBAR_BRAND_HTML, unsafe_allow_html=True)

    # GCP Project
    project_id = st.text_input(
        "Project",
        value=os.environ.get("GCP_PROJECT_ID", ""),
        help="Your Google Cloud project ID",
    )

    location = st.selectbox(
        "Region",
        ["us-central1", "us-east1", "us-west1",
         "europe-west1", "europe-west4",
         "asia-northeast1", "asia-southeast1"],
    )

    # ── Time Range ────────────────────────────────────────────────────────
    preset = st.selectbox(
        "Time period",
        ["Last 24 hours", "Last 7 days", "Last 30 days", "Custom range"],
        index=2
    )

    now = datetime.now(timezone.utc)
    if preset == "Last 24 hours":
        start_dt, end_dt = now - timedelta(hours=24), now
    elif preset == "Last 7 days":
        start_dt, end_dt = now - timedelta(days=7), now
    elif preset == "Last 30 days":
        start_dt, end_dt = now - timedelta(days=30), now
    else:
        c1, c2 = st.columns(2)
        sd = c1.date_input("Start", value=(now - timedelta(days=7)).date())
        ed = c2.date_input("End",   value=now.date())
        start_dt = datetime(sd.year, sd.month, sd.day, tzinfo=timezone.utc)
        end_dt   = datetime(ed.year, ed.month, ed.day, 23, 59, 59, tzinfo=timezone.utc)

    st.caption(
        f"🕐 {start_dt.strftime('%b %d %H:%M')} → {end_dt.strftime('%b %d %H:%M')} UTC"
    )


    # ── Agent Engine Selection ────────────────────────────────────────────
    selected_agents: list[dict] = []

    if project_id:
        with st.spinner("Loading agents..."):
            agents = list_agent_engines(project_id, location)

        if agents:
            names = [a["display_name"] for a in agents]
            chosen = st.multiselect(
                "Agent",
                names,
                default=names[:1],
                help="Hold Ctrl/Cmd to multi-select",
            )
            selected_agents = [a for a in agents if a["display_name"] in chosen]
        else:
            st.warning("No Agent Engines found. Check project ID and region.")
    else:
        st.info("Enter a Project ID above.")

    # ── Default model for cost estimation when token logs unavailable ──────
    default_model = st.selectbox(
        "Fallback model",
        list(MODEL_PRICING.keys()),
        index=list(MODEL_PRICING.keys()).index("gemini-2.0-flash"),
        help="Used when token logs are unavailable"
    )

    st.markdown('<div style="height:15px"></div>', unsafe_allow_html=True)
    analyze_btn = st.button(
        "🔍  Analyze Spend",
        type="primary",
        use_container_width=True,
        disabled=not (project_id and selected_agents),
    )


# ══════════════════════════════════════════════════════════════════════════════
# MAIN CONTENT
# ══════════════════════════════════════════════════════════════════════════════
# ── Setup initial status messages if not loaded ───────────────────────────────
if not project_id:
    st.info("👈  Enter your **GCP Project ID** in the sidebar to get started.")
    st.stop()

if not selected_agents:
    st.info("👈  Select one or more **Agent Engines** in the sidebar, then click **Analyze Spend**.")
    st.stop()

# ── Run analysis on button press (cache in session_state) ─────────────────────
if analyze_btn:
    engine_ids = [a["id"] for a in selected_agents]

    with st.spinner("Fetching runtime metrics from Cloud Monitoring…"):
        all_runtime = get_metrics_for_agents(
            project_id, location, engine_ids, start_dt, end_dt
        )

    with st.spinner("Scanning Cloud Logging for token usage…"):
        all_tokens = {
            eid: get_token_metrics(project_id, location, eid, start_dt, end_dt)
            for eid in engine_ids
        }

    all_costs = {
        eid: calculate_costs(all_runtime[eid], all_tokens[eid], default_model)
        for eid in engine_ids
    }

    st.session_state["results"] = {
        "agents":     selected_agents,
        "runtime":    all_runtime,
        "tokens":     all_tokens,
        "costs":      all_costs,
        "time_range": (start_dt, end_dt),
        "project_id": project_id,
        "preset":     preset,
    }

# Bail if no cached results yet
if "results" not in st.session_state:
    st.info("👈  Click **Analyze Spend** to load data.")
    st.stop()

res         = st.session_state["results"]
agents_list = res["agents"]
all_runtime = res["runtime"]
all_tokens  = res["tokens"]
all_costs   = res["costs"]
current_preset = res.get("preset", "selected period")

# ══════════════════════════════════════════════════════════════════════════════
# MAIN CONTENT HEADER & HERO CARD
# ══════════════════════════════════════════════════════════════════════════════
agents_label = " · ".join([a["display_name"] for a in agents_list]) if agents_list else "all agents"
scope_label = f"Showing {project_id} · {location} · {agents_label} — {current_preset}"

c_head_left, c_head_right = st.columns([3, 1])
with c_head_left:
    st.markdown(f"""
    <div style="font-size:22px; font-weight:700; letter-spacing:-0.015em; color:oklch(0.2 0.01 250);">Spend overview</div>
    <div style="font-size:13px; color:oklch(0.55 0.01 250); margin-top:2px;">{scope_label}</div>
    """, unsafe_allow_html=True)
with c_head_right:
    st.markdown('<div style="font-size:12px; color:oklch(0.6 0.01 250); font-family: \'Roboto Mono\', ui-monospace, monospace; text-align: right; line-height: 2.2;">Updated just now</div>', unsafe_allow_html=True)

st.markdown('<div style="height:10px"></div>', unsafe_allow_html=True)

total_cost      = sum(c["total"]         for c in all_costs.values())
total_compute   = sum(c["compute_cost"]  for c in all_costs.values())
total_tokens_c  = sum(c["token_cost"]    for c in all_costs.values())
total_requests  = sum(m["request_count"] for m in all_runtime.values())

st.markdown(render_hero_card(total_cost, total_compute, total_tokens_c, total_requests, current_preset), unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# VISUALIZATION GRID (2 COLUMNS)
# ══════════════════════════════════════════════════════════════════════════════
col_chart1, col_chart2 = st.columns(2)

with col_chart1:
    st.markdown(render_card_start("Spend over time", current_preset), unsafe_allow_html=True)
    
    pts = get_spend_timeseries(agents_list, all_runtime, all_costs)
    if pts:
        df_ts = pd.DataFrame(pts)
        fig_line = px.area(
            df_ts,
            x="timestamp",
            y="value",
        )
        fig_line.update_traces(
            line_color="#3b82f6",
            line_width=2.5,
            fillcolor="rgba(59, 130, 246, 0.12)"
        )
        fig_line.update_layout(
            margin=dict(l=10, r=10, t=10, b=10),
            height=240,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(
                showgrid=True,
                gridcolor="#e2e8f0",
                tickfont=dict(size=10, color="#94a3b8"),
                title=None
            ),
            yaxis=dict(
                showgrid=True,
                gridcolor="#e2e8f0",
                tickfont=dict(size=10, color="#94a3b8"),
                title=None
            )
        )
        st.plotly_chart(fig_line, use_container_width=True, config={"displayModeBar": False})
    else:
        st.caption("No spend data points available in this window.")
        
    st.markdown(render_card_end(), unsafe_allow_html=True)

with col_chart2:
    st.markdown(render_card_start("Breakdown by component"), unsafe_allow_html=True)
    
    cost_labels = ["CPU Compute", "Memory", "Input Tokens", "Output Tokens", "Thinking Tokens"]
    cost_vals = [
        sum(all_costs[a["id"]]["cpu_cost"] for a in agents_list),
        sum(all_costs[a["id"]]["memory_cost"] for a in agents_list),
        sum(all_costs[a["id"]]["input_token_cost"] for a in agents_list),
        sum(all_costs[a["id"]]["output_token_cost"] for a in agents_list),
        sum(all_costs[a["id"]]["thinking_token_cost"] for a in agents_list),
    ]
    
    # Only keep nonzero slices
    nonzero_idx = [i for i, v in enumerate(cost_vals) if v > 0]
    if nonzero_idx:
        fig_donut = px.pie(
            names=[cost_labels[i] for i in nonzero_idx],
            values=[cost_vals[i] for i in nonzero_idx],
            hole=0.6,
            color_discrete_sequence=["#3b82f6", "#06b6d4", "#10b981", "#8b5cf6", "#f97316"]
        )
        fig_donut.update_traces(textposition="inside", textinfo="percent")
        fig_donut.update_layout(
            margin=dict(l=10, r=10, t=10, b=10),
            height=240,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            legend=dict(
                orientation="v",
                valign="middle",
                x=0.9,
                y=0.5,
                font=dict(size=11, color="#64748b")
            )
        )
        st.plotly_chart(fig_donut, use_container_width=True, config={"displayModeBar": False})
    else:
        st.caption("No cost distribution available.")
        
    st.markdown(render_card_end(), unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# COMPARISON GRID
# ══════════════════════════════════════════════════════════════════════════════
col_comp1, col_comp2 = st.columns(2)

with col_comp1:
    st.markdown(render_card_start("Cost by agent"), unsafe_allow_html=True)
    agent_costs = []
    for a in agents_list:
        eid = a["id"]
        agent_costs.append({
            "Agent": a["display_name"],
            "Cost": all_costs[eid]["total"]
        })
    if agent_costs:
        df_agent_costs = pd.DataFrame(agent_costs).sort_values(by="Cost", ascending=True)
        fig_agent_bar = px.bar(
            df_agent_costs,
            x="Cost",
            y="Agent",
            orientation="h",
            color_discrete_sequence=["#6366f1"]
        )
        fig_agent_bar.update_layout(
            margin=dict(l=10, r=10, t=10, b=10),
            height=200,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(
                showgrid=True,
                gridcolor="#e2e8f0",
                tickfont=dict(size=10, color="#94a3b8"),
                title=None
            ),
            yaxis=dict(
                showgrid=False,
                tickfont=dict(size=11, color="#475569"),
                title=None
            )
        )
        st.plotly_chart(fig_agent_bar, use_container_width=True, config={"displayModeBar": False})
    else:
        st.caption("No agent costs to compare.")
    st.markdown(render_card_end(), unsafe_allow_html=True)

with col_comp2:
    st.markdown(render_card_start("Cost by model"), unsafe_allow_html=True)
    model_costs = defaultdict(float)
    for a in agents_list:
        eid = a["id"]
        for model_id, mc in all_costs[eid].get("by_model_costs", {}).items():
            model_costs[model_id] += mc["model_total"]
            
    if model_costs:
        df_model_costs = pd.DataFrame([
            {"Model": m, "Cost": c} for m, c in model_costs.items()
        ]).sort_values(by="Cost", ascending=True)
        fig_model_bar = px.bar(
            df_model_costs,
            x="Cost",
            y="Model",
            orientation="h",
            color_discrete_sequence=["#06b6d4"]
        )
        fig_model_bar.update_layout(
            margin=dict(l=10, r=10, t=10, b=10),
            height=200,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(
                showgrid=True,
                gridcolor="#e2e8f0",
                tickfont=dict(size=10, color="#94a3b8"),
                title=None
            ),
            yaxis=dict(
                showgrid=False,
                tickfont=dict(size=11, color="#475569"),
                title=None
            )
        )
        st.plotly_chart(fig_model_bar, use_container_width=True, config={"displayModeBar": False})
    else:
        st.caption("No model costs available (token logs missing).")
    st.markdown(render_card_end(), unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# DETAILED AGENT BREAKDOWN (EXPANDERS)
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<div style="height:20px"></div>', unsafe_allow_html=True)

# Tabs to switch between Runtime and Token Details
tab_runtime, tab_tokens = st.tabs(["📊 Runtime Details", "💰 Token & Cost Breakdown"])

with tab_runtime:
    for agent in agents_list:
        eid  = agent["id"]
        m    = all_runtime[eid]
        name = agent["display_name"]

        with st.expander(f"🤖 {name} (ID: {eid})", expanded=True):
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Total Requests",   f"{m['request_count']:,.0f}")
            k2.metric("P95 Latency",      f"{m['p95_latency_ms']:,.1f} ms")
            k3.metric("CPU Allocated",    f"{m['cpu_seconds']/3600:.4f} vCPU-hrs")
            k4.metric("Memory Allocated", f"{m['memory_gb_seconds']/3600:.4f} GiB-hrs")

            tab_req, tab_cpu, tab_mem, tab_lat = st.tabs(
                ["📨 Requests", "🖥️ CPU", "💾 Memory", "⏱️ Latency"]
            )

            def _line_chart(pts, title, y_label, tab):
                if pts:
                    df = pd.DataFrame(pts)
                    fig = px.line(df, x="timestamp", y="value",
                                  title=title, labels={"value": y_label, "timestamp": "Time"})
                    fig.update_layout(margin=dict(t=40, b=20), height=250)
                    tab.plotly_chart(fig, use_container_width=True)
                else:
                    tab.caption("No data points in this time window.")

            _line_chart(m["request_count_timeseries"], "Requests per hour", "requests/hr", tab_req)
            _line_chart(m["cpu_timeseries"], "CPU allocation (vCPU-s/hr)", "vCPU-s", tab_cpu)
            _line_chart(m["memory_timeseries"], "Memory allocation (GiB-s/hr)", "GiB-s", tab_mem)
            _line_chart(m["latency_timeseries"], "P95 Latency (ms)", "ms", tab_lat)

with tab_tokens:
    # Token data availability banner
    any_token_data = any(t["data_available"] for t in all_tokens.values())
    if not any_token_data:
        st.markdown(f"""
        <div class="warning-box" style="background: #fff8e1; border: 1px solid #f9a825; border-radius: 6px; padding: 0.8rem 1rem; margin: 0.5rem 0;">
          ⚠️ <strong>Token data not found in Cloud Logging.</strong><br>
          To enable token tracking, deploy your agent with tracing enabled:<br>
          <code>agent_engines.AdkApp(agent=root_agent, enable_tracing=True)</code><br>
          Or enable <strong>Vertex AI Data Access audit logs</strong> in IAM &amp; Admin → Audit Logs.<br>
          Cost estimates use <em>fallback model: {default_model}</em> as a fallback.
        </div>
        """, unsafe_allow_html=True)

    for agent in agents_list:
        eid   = agent["id"]
        t     = all_tokens[eid]
        c     = all_costs[eid]
        name  = agent["display_name"]

        with st.expander(f"🤖 {name} — Token & Cost Detail", expanded=True):
            if t["data_available"]:
                t1, t2, t3, t4 = st.columns(4)
                t1.metric("Input Tokens",    f"{t['input_tokens']:,.0f}")
                t2.metric("Output Tokens",   f"{t['output_tokens']:,.0f}")
                t3.metric("Thinking Tokens", f"{t['thinking_tokens']:,.0f}")
                total_tok = t['input_tokens'] + t['output_tokens'] + t['thinking_tokens']
                t4.metric("Total Tokens",    f"{total_tok:,.0f}")
            else:
                st.caption("ℹ️ Token counts not available.")

            prices = MODEL_PRICING.get(default_model, MODEL_PRICING["gemini-2.0-flash"])
            rows = [
                {"Component": "🖥️ CPU Compute", "Usage": f"{c['cpu_hours']:.4f} vCPU-hrs", "Unit Price": f"${COMPUTE_PRICING['vcpu_per_hour']:.5f}", "Cost ($)": f"${c['cpu_cost']:.6f}"},
                {"Component": "💾 Memory", "Usage": f"{c['memory_hours']:.4f} GiB-hrs", "Unit Price": f"${COMPUTE_PRICING['memory_per_hour']:.5f}", "Cost ($)": f"${c['memory_cost']:.6f}"},
                {"Component": "📥 Input Tokens", "Usage": f"{t['input_tokens']:,.0f}", "Unit Price": f"${prices['input']:.4f}/1M", "Cost ($)": f"${c['input_token_cost']:.6f}"},
                {"Component": "📤 Output Tokens", "Usage": f"{t['output_tokens']:,.0f}", "Unit Price": f"${prices['output']:.4f}/1M", "Cost ($)": f"${c['output_token_cost']:.6f}"},
                {"Component": "🧠 Thinking Tokens", "Usage": f"{t['thinking_tokens']:,.0f}", "Unit Price": f"${prices['thinking']:.4f}/1M", "Cost ($)": f"${c['thinking_token_cost']:.6f}"},
            ]
            
            # Draw html table
            rows_html = "".join([
                f"<tr><td>{r['Component']}</td><td>{r['Usage']}</td><td>{r['Unit Price']}</td><td><b>{r['Cost ($)']}</b></td></tr>"
                for r in rows
            ])
            table_html = f"""
            <table class="data-table">
              <thead>
                <tr>
                  <th>Component</th>
                  <th>Usage</th>
                  <th>Unit Price</th>
                  <th>Cost</th>
                </tr>
              </thead>
              <tbody>
                {rows_html}
              </tbody>
            </table>
            """
            st.markdown(table_html, unsafe_allow_html=True)

            if t["data_available"] and t["by_model"]:
                st.markdown('<div style="height:10px"></div>', unsafe_allow_html=True)
                st.markdown("**📊 Breakdown by Model**")
                model_rows = []
                for model_id, mc in c.get("by_model_costs", {}).items():
                    model_rows.append(
                        f"<tr><td>{model_id}</td><td>{mc['input_tokens']:,.0f}</td><td>{mc['output_tokens']:,.0f}</td><td>{mc['thinking_tokens']:,.0f}</td><td><b>${mc['model_total']:.6f}</b></td></tr>"
                    )
                model_table_html = f"""
                <table class="data-table">
                  <thead>
                    <tr>
                      <th>Model ID</th>
                      <th>Input Tokens</th>
                      <th>Output Tokens</th>
                      <th>Thinking Tokens</th>
                      <th>Total Cost</th>
                    </tr>
                  </thead>
                  <tbody>
                    {"".join(model_rows)}
                  </tbody>
                </table>
                """
                st.markdown(model_table_html, unsafe_allow_html=True)

st.markdown('<div style="height:20px"></div>', unsafe_allow_html=True)
st.caption(
    "💡 Prices are indicative. Verify at "
    "[cloud.google.com/vertex-ai/pricing](https://cloud.google.com/vertex-ai/pricing) · "
    "Metrics sourced from Cloud Monitoring & Cloud Logging"
)
