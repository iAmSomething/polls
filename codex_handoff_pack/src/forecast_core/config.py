from __future__ import annotations

import argparse
from dataclasses import dataclass

Z80 = 1.2815515655446004


@dataclass(frozen=True)
class ForecastConfig:
    model: str
    window_weeks: int
    horizon_weeks: int
    regime_guard: str
    regime_q_scale: float
    exog_approval: str
    approval_weekly_csv: str


def parse_args() -> ForecastConfig:
    ap = argparse.ArgumentParser(description="Forecast next-week party support from blended series.")
    ap.add_argument("--model", choices=["legacy", "ssm"], default="ssm")
    ap.add_argument("--window-weeks", type=int, default=24)
    ap.add_argument("--horizon-weeks", type=int, default=1)
    ap.add_argument("--regime-guard", choices=["on", "off"], default="on")
    ap.add_argument("--regime-q-scale", type=float, default=2.0, help="Q scale when regime shift is triggered")
    ap.add_argument("--exog-approval", choices=["off", "on"], default="off")
    ap.add_argument("--approval-weekly-csv", default="outputs/president_approval_weekly.csv")
    ns = ap.parse_args()
    return ForecastConfig(
        model=ns.model,
        window_weeks=ns.window_weeks,
        horizon_weeks=ns.horizon_weeks,
        regime_guard=ns.regime_guard,
        regime_q_scale=ns.regime_q_scale,
        exog_approval=ns.exog_approval,
        approval_weekly_csv=ns.approval_weekly_csv,
    )
