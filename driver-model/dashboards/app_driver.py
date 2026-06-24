"""Interactive driver-model dashboard.

Run from the project root:
    streamlit run dashboards/app_driver.py

The dashboard owns NO model logic. It mutates leaf assumptions and re-runs the
same engine, so every change propagates through the full cascade automatically.
"""
import sys
from pathlib import Path
import copy
import streamlit as st
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))
from engine import build
from inputs_resolver import resolve, deep_merge, validate

st.set_page_config(page_title="Driver model", layout="wide")
st.title("Driver-based plan: live sensitivity")

base = resolve()                      # resolved defaults (YAML + Salesforce)
baseline_df = build(base)             # the unchanged reference case

# ---------- sidebar: leaf assumptions grouped by layer ----------
st.sidebar.header("Assumptions")

st.sidebar.subheader("Capacity")
opps_per_rep = st.sidebar.slider(
    "New opps / ramped rep / month", 2, 20,
    base["sales_capacity"]["new_opps_per_ramped_rep_per_month"])
starting_reps = st.sidebar.slider(
    "Starting reps", 1, 20, base["sales_capacity"]["starting_reps"])

st.sidebar.subheader("Funnel conversion")
cr = base["pipeline"]["conversion_rates"]
c12 = st.sidebar.slider("Stage1 to Stage2", 0.0, 1.0, float(cr["stage1_to_stage2"]), 0.01)
c23 = st.sidebar.slider("Stage2 to Stage3", 0.0, 1.0, float(cr["stage2_to_stage3"]), 0.01)
c34 = st.sidebar.slider("Stage3 to Stage4", 0.0, 1.0, float(cr["stage3_to_stage4"]), 0.01)
cwon = st.sidebar.slider("Win rate (Stage4 to won)", 0.0, 1.0, float(cr["stage4_to_won"]), 0.01)

st.sidebar.subheader("New business")
avg_acv = st.sidebar.slider("New avg ACV", 10000, 150000,
                            base["new_business"]["avg_acv"], 5000)
impl_fee = st.sidebar.slider("Implementation fee", 0, 50000,
                             base["new_business"]["implementation_fee"], 1000)
impl_lag = st.sidebar.slider("Implementation lag (months)", 0, 6,
                             base["new_business"]["implementation_lag_months"])

st.sidebar.subheader("Existing business")
active = st.sidebar.slider("Active customers", 0, 200,
                           base["existing_business"]["active_customers"])
churn = st.sidebar.slider("Monthly logo churn", 0.0, 0.05,
                          float(base["existing_business"]["monthly_logo_churn"]), 0.001)

# ---------- assemble overrides and re-run the SAME engine ----------
overrides = {
    "sales_capacity": {
        "new_opps_per_ramped_rep_per_month": opps_per_rep,
        "starting_reps": starting_reps,
    },
    "pipeline": {"conversion_rates": {
        "stage1_to_stage2": c12, "stage2_to_stage3": c23,
        "stage3_to_stage4": c34, "stage4_to_won": cwon,
    }},
    "new_business": {
        "avg_acv": avg_acv, "implementation_fee": impl_fee,
        "implementation_lag_months": impl_lag,
    },
    "existing_business": {"active_customers": active, "monthly_logo_churn": churn},
}
a = deep_merge(base, overrides)
try:
    validate(a)
except ValueError as e:
    st.error(f"Invalid assumptions: {e}")
    st.stop()
df = build(a)

# ---------- KPI row: current vs baseline (this IS the sensitivity readout) ----------
def fy(frame, col):
    return frame[col].sum()

rev_now, rev_base = fy(df, "total_revenue"), fy(baseline_df, "total_revenue")
cust_now, cust_base = fy(df, "new_customers"), fy(baseline_df, "new_customers")
dec_now, dec_base = df["total_revenue"].iloc[-1], baseline_df["total_revenue"].iloc[-1]

k1, k2, k3 = st.columns(3)
k1.metric("Full-year revenue", f"{rev_now:,.0f}", f"{rev_now - rev_base:+,.0f} vs base")
k2.metric("New customers", f"{cust_now:,.1f}", f"{cust_now - cust_base:+,.1f} vs base")
k3.metric("Dec revenue", f"{dec_now:,.0f}", f"{dec_now - dec_base:+,.0f} vs base")

# ---------- watch the cascade move, layer by layer ----------
st.subheader("Revenue: your scenario vs baseline")
comp = pd.DataFrame({
    "month": df["month"],
    "your scenario": df["total_revenue"],
    "baseline": baseline_df["total_revenue"],
}).set_index("month")
st.line_chart(comp)

left, right = st.columns(2)
with left:
    st.subheader("Revenue mix")
    mix = df.set_index("month")[
        ["implementation_rev", "new_saas_rev", "existing_saas_rev"]]
    st.bar_chart(mix)            # stacked
with right:
    st.subheader("Upstream drivers")
    st.caption("How capacity and the funnel feed new customers each month")
    drivers = df.set_index("month")[["opps_created", "new_customers"]]
    st.line_chart(drivers)

# ---------- tornado: which assumption moves revenue most ----------
st.subheader("Sensitivity: full-year revenue swing at +/-10% per driver")
st.caption("Each bar perturbs ONE assumption by +/-10% from your current scenario, "
           "holding the rest fixed. Longer bar = more leverage.")

drivers_to_test = {
    "opps / rep": ("sales_capacity", "new_opps_per_ramped_rep_per_month"),
    "win rate": ("pipeline", "conversion_rates", "stage4_to_won"),
    "new ACV": ("new_business", "avg_acv"),
    "active customers": ("existing_business", "active_customers"),
    "stage3 to stage4": ("pipeline", "conversion_rates", "stage3_to_stage4"),
}

def set_path(d, path, value):
    d = copy.deepcopy(d)
    node = d
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    return d

def get_path(d, path):
    node = d
    for key in path:
        node = node[key]
    return node

rows = []
for label, path in drivers_to_test.items():
    cur = get_path(a, path)
    low = build(set_path(a, path, cur * 0.9))["total_revenue"].sum()
    high = build(set_path(a, path, cur * 1.1))["total_revenue"].sum()
    rows.append({"driver": label, "downside (-10%)": low - rev_now,
                 "upside (+10%)": high - rev_now})

tornado = pd.DataFrame(rows).set_index("driver")
tornado["range"] = tornado["upside (+10%)"] - tornado["downside (-10%)"]
tornado = tornado.sort_values("range").drop(columns="range")
st.bar_chart(tornado)

with st.expander("How the assumptions are linked"):
    st.markdown(
        "- Capacity (reps x productivity) sets **opportunities created**.\n"
        "- Opportunities flow through the funnel at each **conversion rate** "
        "to produce **new customers** (deals won).\n"
        "- New customers generate **implementation** and **new SaaS** revenue; "
        "the existing base generates **existing SaaS** revenue.\n"
        "- The dashboard changes only the leaves. The engine recomputes every "
        "layer above, so a change anywhere propagates all the way to revenue."
    )

st.subheader("Detail")
st.dataframe(df, use_container_width=True)
