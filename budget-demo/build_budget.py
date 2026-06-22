"""Build a simple monthly budget from a YAML assumptions file.

Usage:
    python build_budget.py              # builds the 'base' scenario
    python build_budget.py upside       # builds a named scenario
    python build_budget.py all          # builds every scenario
"""
from __future__ import annotations
import sys
from pathlib import Path
import copy
import yaml
import pandas as pd

ROOT = Path(__file__).resolve().parent
ASSUMPTIONS = ROOT / "assumptions" / "budget.yaml"
OUTDIR = ROOT / "outputs"


def deep_merge(base: dict, override: dict) -> dict:
    """Return base updated with override, merging nested dicts (e.g. opex)."""
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load(path: Path = ASSUMPTIONS) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def assumptions_for(cfg: dict, scenario: str) -> dict:
    """Merge the named scenario's overrides onto the base case."""
    if scenario not in cfg["scenarios"]:
        valid = ", ".join(cfg["scenarios"])
        raise ValueError(f"Unknown scenario '{scenario}'. Choose from: {valid}")
    return deep_merge(cfg["base"], cfg["scenarios"][scenario])


def project_budget(a: dict, meta: dict, label: str = "scenario") -> pd.DataFrame:
    """Project a monthly budget from a fully-merged assumptions dict."""
    n = meta["months"]
    periods = pd.period_range(meta["start_month"], periods=n, freq="M")

    rows = []
    cash = a["starting_cash"]
    for i, p in enumerate(periods):
        revenue = a["starting_revenue"] * (1 + a["monthly_growth"]) ** i
        cogs = revenue * (1 - a["gross_margin"])
        gross_profit = revenue - cogs
        opex = sum(a["opex"].values())
        ebitda = gross_profit - opex
        cash += ebitda
        rows.append({
            "scenario": label,
            "month": p.strftime("%Y-%m"),
            "revenue": round(revenue),
            "cogs": round(cogs),
            "gross_profit": round(gross_profit),
            "opex": round(opex),
            "ebitda": round(ebitda),
            "cash": round(cash),
        })
    return pd.DataFrame(rows)


def build_budget(cfg: dict, scenario: str) -> pd.DataFrame:
    """Convenience wrapper: merge a named scenario and project it."""
    a = assumptions_for(cfg, scenario)
    return project_budget(a, cfg["meta"], label=scenario)


def main():
    cfg = load()
    arg = sys.argv[1] if len(sys.argv) > 1 else "base"
    scenarios = list(cfg["scenarios"]) if arg == "all" else [arg]

    OUTDIR.mkdir(exist_ok=True)
    frames = []
    for s in scenarios:
        df = build_budget(cfg, s)
        df.to_csv(OUTDIR / f"budget_{s}.csv", index=False)
        frames.append(df)
        print(f"\n=== {s} ===")
        print(df.to_string(index=False))

    if len(frames) > 1:
        combined = pd.concat(frames, ignore_index=True)
        combined.to_csv(OUTDIR / "budget_all.csv", index=False)
        summary = (combined.groupby("scenario")
                   .agg(full_year_revenue=("revenue", "sum"),
                        full_year_ebitda=("ebitda", "sum"),
                        ending_cash=("cash", "last"))
                   .round())
        print("\n=== full-year summary ===")
        print(summary.to_string())


if __name__ == "__main__":
    main()
