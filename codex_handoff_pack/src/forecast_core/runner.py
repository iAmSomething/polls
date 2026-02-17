from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .config import ForecastConfig, Z80
from .features import detect_regime_shift, load_approval_weekly, to_weekly
from .io import load_blended_input, write_forecast_outputs
from .models import forecast_next, forecast_next_ssm, forecast_next_ssm_with_exog
def build_forecast_row(
    party: str,
    series: pd.Series,
    cfg: ForecastConfig,
    q_scale: float,
    approval_weekly: pd.Series,
) -> dict:
    if cfg.model == "legacy":
        pred, sigma = forecast_next(series, horizon_weeks=cfg.horizon_weeks, window_weeks=cfg.window_weeks)
        row = {"party": party, "next_week_pred": pred, "rmse": sigma, "pred_sd": np.nan}
    else:
        if cfg.exog_approval == "on":
            pred, pred_sd, sigma = forecast_next_ssm_with_exog(
                series=series,
                approval_weekly=approval_weekly,
                horizon_weeks=cfg.horizon_weeks,
                window_weeks=cfg.window_weeks,
                q_scale=q_scale,
            )
        else:
            pred, pred_sd, sigma = forecast_next_ssm(
                series, horizon_weeks=cfg.horizon_weeks, window_weeks=cfg.window_weeks, q_scale=q_scale
            )
        row = {"party": party, "next_week_pred": pred, "rmse": sigma, "pred_sd": pred_sd}
    if pd.notna(row["pred_sd"]):
        row["pred_lo_80"] = float(row["next_week_pred"] - Z80 * row["pred_sd"])
        row["pred_hi_80"] = float(row["next_week_pred"] + Z80 * row["pred_sd"])
    else:
        row["pred_lo_80"] = np.nan
        row["pred_hi_80"] = np.nan
    row["model"] = cfg.model
    row["exog_approval"] = cfg.exog_approval
    return row


def run_forecast(cfg: ForecastConfig) -> tuple[pd.DataFrame, dict]:
    outputs_dir = Path("outputs")
    blended = load_blended_input(outputs_dir)
    weekly = to_weekly(blended)
    regime = (
        detect_regime_shift(weekly)
        if cfg.regime_guard == "on"
        else {"triggered": False, "reasons": ["disabled"], "score": 0.0}
    )
    q_scale = cfg.regime_q_scale if regime.get("triggered", False) else 1.0
    approval_weekly = (
        load_approval_weekly(Path(cfg.approval_weekly_csv))
        if cfg.exog_approval == "on"
        else pd.Series(dtype=float)
    )
    forecast_rows = [
        build_forecast_row(col, weekly[col], cfg, q_scale, approval_weekly)
        for col in weekly.columns
    ]
    out = pd.DataFrame(forecast_rows)
    regime_payload = {
        "triggered": bool(regime.get("triggered", False)),
        "reasons": regime.get("reasons", []),
        "score": float(regime.get("score", 0.0)),
        "q_scale_applied": float(q_scale),
        "model": cfg.model,
        "exog_approval": cfg.exog_approval,
        "approval_rows": int(len(approval_weekly)),
    }
    regime_out = write_forecast_outputs(outputs_dir, out, regime_payload)
    print("Wrote:", regime_out)
    print(out.sort_values("rmse").head(10))
    return out, regime_payload


