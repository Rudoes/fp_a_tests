"""Streamlit dashboard to compare budget scenarios.

Run from the project root:
    streamlit run dashboards/app.py
"""
import sys
from pathlib import Path
import copy
import streamlit as st
import pandas as pd

# make build_budget.py importable when run from the project root
sys.path.append(str(Path(__file__).resolve().parents[1]))
from build_budget import load, assumptions_for, project_budget

st.set_page_config(page_title="Budget scenarios", layout="wide")
st.title("FY2026 budget: scenario comparison")

cfg = load()
all_scenarios = list(cfg["scenarios"])

# --- sidebar controls ---
st.sidebar.header("Scenarios")
chosen = st.sidebar.multiselect(
    "Compare", all_scenarios, default=all_scenarios)

st.sidebar.header("What-if (applied to every selected scenario)")
growth_delta = st.sidebar.slider(
    "Growth adjustment (pp/month)", -3.0, 3.0, 0.0, 0.5) / 100
margin_delta = st.sidebar.slider(
    "Margin adjustment (pp)", -10.0, 10.0, 0.0, 1.0) / 100

if not chosen:
    st.info("Pick at least one scenario in the sidebar.")
    st.stop()

# --- build each selected scenario, applying the live deltas on top ---
frames = []
for name in chosen:
    a = copy.deepcopy(assumptions_for(cfg, name))
    a["monthly_growth"] = max(0.0, a["monthly_growth"] + growth_delta)
    a["gross_margin"] = min(0.99, max(0.0, a["gross_margin"] + margin_delta))
    frames.append(project_budget(a, cfg["meta"], label=name))

data = pd.concat(frames, ignore_index=True)

# --- KPI row: one metric block per scenario ---
st.subheader("Full-year summary")
cols = st.columns(len(chosen))
for col, name in zip(cols, chosen):
    d = data[data["scenario"] == name]
    col.markdown(f"**{name}**")
    col.metric("Revenue", f"{d['revenue'].sum():,.0f}")
    col.metric("EBITDA", f"{d['ebitda'].sum():,.0f}")
    col.metric("Ending cash", f"{d['cash'].iloc[-1]:,.0f}")

# --- charts: one line per scenario, pivoted so scenarios are columns ---
def chart(metric: str, title: str):
    st.subheader(title)
    wide = data.pivot(index="month", columns="scenario", values=metric)
    st.line_chart(wide)

chart("revenue", "Revenue")
chart("ebitda", "EBITDA")
chart("cash", "Cash balance")

# --- raw table + download ---
st.subheader("Detail")
st.dataframe(data, use_container_width=True)
st.download_button(
    "Download CSV",
    data.to_csv(index=False).encode(),
    file_name="budget_scenarios.csv",
    mime="text/csv",
)
