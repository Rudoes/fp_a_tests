"""Resolve model inputs from multiple sources into ONE canonical dict.

The engine never knows where a number came from. Each adapter returns a partial
dict in the canonical schema; the resolver merges them by ownership/precedence,
validates, and (optionally) snapshots the result for reproducibility.

Precedence (low -> high):
  system snapshots  <  human YAML assumptions  <  explicit overrides
Ideally sources own DIFFERENT keys, so they rarely collide.
"""
from __future__ import annotations
from pathlib import Path
import copy
import yaml

ROOT = Path(__file__).resolve().parent
YAML_PATH = ROOT / "assumptions" / "model.yaml"


def deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


# ---- adapters: one per source, each returns a partial canonical dict ----
def from_yaml(path: Path = YAML_PATH) -> dict:
    """FP&A-owned, human-authored go-forward assumptions."""
    with open(path) as f:
        return yaml.safe_load(f)


def from_salesforce() -> dict:
    """STUB. In production this calls the Salesforce MCP/API and returns the
    canonical keys SF owns: current pipeline by stage, and conversion rates
    DERIVED from trailing won/created history rather than guessed."""
    return {
        "pipeline": {
            "starting_pipeline": {           # observed current open pipeline
                "stage1": 24, "stage2": 15, "stage3": 9, "stage4": 6,
            },
            "conversion_rates": {            # trailing 12-mo actuals, not assumptions
                "stage1_to_stage2": 0.58,
                "stage2_to_stage3": 0.52,
                "stage3_to_stage4": 0.50,
                "stage4_to_won": 0.28,
            },
        }
    }


# ---- validation: fail loudly on a broken merge ----
def validate(a: dict) -> None:
    p = a["pipeline"]
    for k, v in p["conversion_rates"].items():
        if not 0 <= v <= 1:
            raise ValueError(f"conversion rate {k}={v} out of [0,1]")
    missing = set(p["stages"]) - set(p["stage_lag_months"])
    if missing:
        raise ValueError(f"stages missing a lag: {missing}")
    if a["meta"]["months"] < 1:
        raise ValueError("meta.months must be >= 1")


def resolve(use_salesforce: bool = True, overrides: dict | None = None) -> dict:
    a = from_yaml()
    if use_salesforce:
        a = deep_merge(a, from_salesforce())   # SF wins on the keys it owns
    if overrides:
        a = deep_merge(a, overrides)           # human override wins over everything
    validate(a)
    return a


def snapshot(a: dict, path: str | Path) -> None:
    """Freeze the exact resolved inputs a run used (reproducibility + audit)."""
    with open(path, "w") as f:
        yaml.safe_dump(a, f, sort_keys=False)


if __name__ == "__main__":
    a = resolve()
    print("Resolved conversion rates (SF-sourced):")
    for k, v in a["pipeline"]["conversion_rates"].items():
        print(f"  {k}: {v}")
    print("Resolved starting pipeline (SF-sourced):", a["pipeline"]["starting_pipeline"])
    print("avg_acv (YAML-sourced):", a["new_business"]["avg_acv"])
