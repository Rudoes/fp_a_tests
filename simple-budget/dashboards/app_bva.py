"""Budget vs actuals dashboard.

Run from the project root:
    streamlit run dashboards/app_bva.py
"""
import sys
from pathlib import Path
import streamlit as st
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))
from build_budget import load, build_budget
from bva import load_actuals, compare, ytd_summary, DEFAULT_METRICS

st.set_page_config(page_title="Budget vs actuals", layout="wide")
st.title("FY2026 budget vs actuals")

cfg = load()
scenario = st.sidebar.selectbox("Budget scenario", list(cfg["scenarios"]))
metric = st.sidebar.selectbox("Metric to chart", DEFAULT_METRICS, index=0)

budget = build_budget(cfg, scenario)
actuals = load_actuals(ROOT / "actuals" / "actuals.csv")
bva = compare(budget, actuals)

# --- YTD KPI cards (closed months only) ---
ytd = ytd_summary(bva)
st.subheader("Year-to-date (closed months)")
cols = st.columns(len(DEFAULT_METRICS))
for col, m in zip(cols, DEFAULT_METRICS):
    row = ytd.loc[m]
    col.metric(
        m,
        f"{row['actual_ytd']:,.0f}",
        f"{row['variance']:+,.0f} ({row['variance_pct']:+.1f}%) vs budget",
        delta_color="normal" if m not in ("cogs", "opex") else "inverse",
    )

# --- budget vs actual line chart for the chosen metric ---
st.subheader(f"{metric}: budget vs actual")
one = bva[bva["metric"] == metric].set_index("month")
st.line_chart(one[["budget", "actual"]])

# --- variance bar chart (closed months) ---
st.subheader(f"{metric}: monthly variance (actual - budget)")
st.bar_chart(one["variance"].dropna())

# --- full BvA table ---
st.subheader("BvA detail")
show = bva.copy()
show["variance_pct"] = (show["variance_pct"] * 100).round(1)
st.dataframe(
    show.style.format({
        "budget": "{:,.0f}", "actual": "{:,.0f}",
        "variance": "{:+,.0f}", "variance_pct": "{:+.1f}%",
    }, na_rep="-"),
    use_container_width=True,
)
st.download_button("Download BvA CSV", bva.to_csv(index=False).encode(),
                   "bva.csv", "text/csv")
