"""Budget vs actuals (BvA) analysis layer.

Pure functions: take a budget DataFrame and an actuals file, return a tidy
comparison table with variance and favorable/unfavorable flags.
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd

# Metrics where lower-than-budget is GOOD (costs). Everything else: higher is good.
COST_METRICS = {"cogs", "opex"}
DEFAULT_METRICS = ["revenue", "cogs", "gross_profit", "opex", "ebitda"]


def load_actuals(path: str | Path) -> pd.DataFrame:
    """Load raw actuals (month, revenue, cogs, opex) and derive the rest,
    using the same identities as the budget so the two are comparable."""
    a = pd.read_csv(path)
    a["gross_profit"] = a["revenue"] - a["cogs"]
    a["ebitda"] = a["gross_profit"] - a["opex"]
    return a


def compare(budget_df: pd.DataFrame, actuals_df: pd.DataFrame,
            metrics: list[str] = DEFAULT_METRICS) -> pd.DataFrame:
    """Return a long-format BvA table: one row per month per metric."""
    b = budget_df[["month"] + metrics].melt(
        id_vars="month", var_name="metric", value_name="budget")
    a = actuals_df[["month"] + metrics].melt(
        id_vars="month", var_name="metric", value_name="actual")

    m = b.merge(a, on=["month", "metric"], how="left")  # left = keep all budget months
    m["variance"] = m["actual"] - m["budget"]
    m["variance_pct"] = m["variance"] / m["budget"]

    def favorable(row):
        if pd.isna(row["actual"]):
            return None  # month not closed yet
        if row["metric"] in COST_METRICS:
            return row["variance"] <= 0   # spending less than budget is good
        return row["variance"] >= 0       # earning more than budget is good

    m["favorable"] = m.apply(favorable, axis=1)
    return m


def ytd_summary(bva: pd.DataFrame) -> pd.DataFrame:
    """Year-to-date totals over closed months only (where an actual exists)."""
    closed = bva.dropna(subset=["actual"])
    g = (closed.groupby("metric")
         .agg(budget_ytd=("budget", "sum"), actual_ytd=("actual", "sum")))
    g["variance"] = g["actual_ytd"] - g["budget_ytd"]
    g["variance_pct"] = g["variance"] / g["budget_ytd"]
    g = g.reindex(DEFAULT_METRICS)
    for c in ["budget_ytd", "actual_ytd", "variance"]:
        g[c] = g[c].round()
    g["variance_pct"] = (g["variance_pct"] * 100).round(1)  # as percent
    return g


if __name__ == "__main__":
    from build_budget import load, build_budget
    cfg = load()
    budget = build_budget(cfg, "base")
    actuals = load_actuals(Path(__file__).resolve().parent / "actuals" / "actuals.csv")
    bva = compare(budget, actuals)
    print(bva.dropna(subset=["actual"]).to_string(index=False))
    print("\n=== YTD ===")
    print(ytd_summary(bva).to_string())
