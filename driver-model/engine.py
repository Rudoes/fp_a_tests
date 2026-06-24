"""Driver-based revenue engine.

The cascade, computed strictly bottom-up (each layer consumes the layer below):
  capacity -> opps created -> funnel by stage -> deals won (new customers)
  new customers -> implementation revenue + new SaaS revenue
  existing base -> existing SaaS revenue
  => total revenue

Every function is pure: assumptions in, numbers out. No I/O, no globals.
"""
from __future__ import annotations
import pandas as pd
import numpy as np


def month_index(meta: dict) -> pd.PeriodIndex:
    return pd.period_range(meta["start_month"], periods=meta["months"], freq="M")


# ---- Layer 0: capacity -> opportunities created per month ----
def opps_created(a: dict, n: int) -> np.ndarray:
    cap = a["sales_capacity"]
    ramp = cap["ramp_curve"]
    hires = cap["hires_per_month"]

    ramped_equiv = np.zeros(n)
    for m in range(n):
        equiv = cap["starting_reps"] * 1.0           # starting reps fully ramped
        for hire_month in range(m + 1):              # each past/this-month hire cohort
            tenure = m - hire_month
            prod = ramp[min(tenure, len(ramp) - 1)]
            equiv += hires[hire_month] * prod
        ramped_equiv[m] = equiv
    return ramped_equiv * cap["new_opps_per_ramped_rep_per_month"]


# ---- Layer 1: funnel flow with per-transition rates and stage lags ----
def run_funnel(a: dict, created: np.ndarray, n: int) -> tuple[pd.DataFrame, np.ndarray]:
    p = a["pipeline"]
    stages = p["stages"]
    conv = p["conversion_rates"]
    lag = p["stage_lag_months"]

    # entering[s][m] = opportunities entering stage s in month m
    entering = {s: np.zeros(n) for s in stages}
    entering[stages[0]] += created
    for s in stages:                                  # inject starting pipeline at t0
        entering[s][0] += p["starting_pipeline"].get(s, 0)

    won = np.zeros(n)
    for i, s in enumerate(stages):
        rate_key = f"{s}_to_{stages[i+1]}" if i + 1 < len(stages) else f"{s}_to_won"
        rate = conv[rate_key]
        L = lag[s]
        for m in range(n):
            arrivals = entering[s][m] * rate
            dest_m = m + L
            if dest_m < n:
                if i + 1 < len(stages):
                    entering[stages[i + 1]][dest_m] += arrivals
                else:
                    won[dest_m] += arrivals
    funnel = pd.DataFrame(entering)
    return funnel, won


# ---- Layer 2/3: revenue from won cohorts and existing base ----
def _days(idx: pd.PeriodIndex) -> np.ndarray:
    return np.array([p.days_in_month for p in idx])


def new_revenue(a: dict, won: np.ndarray, idx: pd.PeriodIndex):
    nb = a["new_business"]
    n = len(idx)
    days = _days(idx)
    daily_saas_per_cust = nb["avg_acv"] / 365.0
    impl_lag = nb["implementation_lag_months"]
    impl_fee = nb["implementation_fee"]

    impl_rev = np.zeros(n)
    saas_rev = np.zeros(n)
    for sign_m in range(n):
        cohort = won[sign_m]
        if cohort <= 0:
            continue
        # implementation fee spread evenly over the build period (signed -> live)
        spread = max(impl_lag, 1)
        for k in range(spread):
            mm = sign_m + k
            if mm < n:
                impl_rev[mm] += cohort * impl_fee / spread
        # SaaS recognised daily from live date for contract_months
        live_m = sign_m + impl_lag
        for k in range(nb["contract_months"]):
            mm = live_m + k
            if 0 <= mm < n:
                saas_rev[mm] += cohort * daily_saas_per_cust * days[mm]
    return impl_rev, saas_rev


def existing_revenue(a: dict, idx: pd.PeriodIndex) -> np.ndarray:
    eb = a["existing_business"]
    n = len(idx)
    days = _days(idx)
    daily = eb["avg_acv"] / 365.0
    active = float(eb["active_customers"])
    rev = np.zeros(n)
    for m in range(n):
        rev[m] = active * daily * days[m]
        active *= (1 - eb["monthly_logo_churn"])      # churn into next month
    return rev


def build(a: dict) -> pd.DataFrame:
    idx = month_index(a["meta"])
    n = len(idx)
    created = opps_created(a, n)
    funnel, won = run_funnel(a, created, n)
    impl, new_saas = new_revenue(a, won, idx)
    existing = existing_revenue(a, idx)

    df = pd.DataFrame({
        "month": idx.strftime("%Y-%m"),
        "opps_created": created.round(1),
        "stage4_entering": funnel["stage4"].round(1),
        "new_customers": won.round(2),
        "implementation_rev": impl.round(0),
        "new_saas_rev": new_saas.round(0),
        "existing_saas_rev": existing.round(0),
    })
    df["total_revenue"] = (df["implementation_rev"] + df["new_saas_rev"]
                           + df["existing_saas_rev"])
    return df


if __name__ == "__main__":
    from inputs_resolver import resolve
    a = resolve()
    out = build(a)
    print(out.to_string(index=False))
    print(f"\nFull-year revenue: {out['total_revenue'].sum():,.0f}")
    print(f"New customers signed: {out['new_customers'].sum():,.1f}")
