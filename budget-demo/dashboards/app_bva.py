"""Streamlit dashboard for Budget vs Actuals (BvA) analysis.

Expects an actuals CSV at outputs/actuals.csv with columns:
    month, revenue, cogs, gross_profit, opex, ebitda, cash

Run from the project root:
    streamlit run dashboards/app_bva.py
"""
import sys
from pathlib import Path
import streamlit as st
import pandas as pd

sys.path.append(str(Path(__file__).resolve().parents[1]))
from build_budget import load, build_budget

ACTUALS_PATH = Path(__file__).resolve().parents[1] / "outputs" / "actuals.csv"

st.set_page_config(page_title="Budget vs Actuals", layout="wide")
st.title("FY2026 budget vs actuals")

cfg = load()
all_scenarios = list(cfg["scenarios"])

# --- sidebar ---
st.sidebar.header("Budget scenario")
scenario = st.sidebar.selectbox("Compare actuals against", all_scenarios)

st.sidebar.header("Actuals")
uploaded = st.sidebar.file_uploader("Upload actuals CSV", type="csv")

# --- load actuals ---
if uploaded is not None:
    actuals = pd.read_csv(uploaded)
elif ACTUALS_PATH.exists():
    actuals = pd.read_csv(ACTUALS_PATH)
else:
    st.info(
        "No actuals loaded. Upload a CSV in the sidebar or place one at "
        f"`outputs/actuals.csv`.\n\n"
        "Expected columns: `month, revenue, cogs, gross_profit, opex, ebitda, cash`"
    )
    st.stop()

# --- build budget for the chosen scenario ---
budget = build_budget(cfg, scenario)

# --- align on common months ---
common_months = sorted(set(budget["month"]) & set(actuals["month"]))
if not common_months:
    st.error("No overlapping months between budget and actuals.")
    st.stop()

bud = budget[budget["month"].isin(common_months)].set_index("month")
act = actuals[actuals["month"].isin(common_months)].set_index("month")

metrics = ["revenue", "gross_profit", "ebitda", "cash"]

# --- variance table ---
variance = pd.DataFrame(index=common_months)
for m in metrics:
    variance[f"{m}_budget"] = bud[m]
    variance[f"{m}_actual"] = act[m]
    variance[f"{m}_var"] = act[m] - bud[m]
    variance[f"{m}_var_pct"] = ((act[m] - bud[m]) / bud[m].abs() * 100).round(1)

# --- KPI row: ytd summary ---
st.subheader("YTD summary")
kpi_cols = st.columns(len(metrics))
for col, m in zip(kpi_cols, metrics):
    bud_total = bud[m].sum() if m != "cash" else bud[m].iloc[-1]
    act_total = act[m].sum() if m != "cash" else act[m].iloc[-1]
    delta = act_total - bud_total
    label = m.replace("_", " ").title()
    col.metric(
        label,
        f"{act_total:,.0f}",
        delta=f"{delta:+,.0f}",
        delta_color="normal" if m != "opex" else "inverse",
    )

# --- charts ---
def bva_chart(metric: str, title: str):
    st.subheader(title)
    chart_data = pd.DataFrame({
        "budget": bud[metric],
        "actual": act[metric],
    }, index=common_months)
    st.line_chart(chart_data)

for m in metrics:
    bva_chart(m, m.replace("_", " ").title())

# --- variance detail table ---
st.subheader("Variance detail")
display_cols = []
for m in metrics:
    display_cols += [f"{m}_budget", f"{m}_actual", f"{m}_var", f"{m}_var_pct"]
st.dataframe(variance[display_cols].reset_index(), use_container_width=True)

st.download_button(
    "Download variance CSV",
    variance.reset_index().to_csv(index=False).encode(),
    file_name="bva_variance.csv",
    mime="text/csv",
)
