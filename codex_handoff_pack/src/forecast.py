"""
Forecast skeleton:
- converts blended date_end series to weekly Mondays
- produces 1-week-ahead damped-trend forecast per party
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def forecast_next(series: pd.Series, horizon_weeks: int = 1, window_weeks: int = 16) -> tuple[float, float]:
    s = series.dropna()
    if len(s) < 6:
        last = float(s.iloc[-1]) if len(s) else float("nan")
        return last, float("nan")

    s = s.iloc[-window_weeks:] if len(s) > window_weeks else s
    y = s.values.astype(float)
    x = np.arange(len(y), dtype=float)

    A = np.vstack([x, np.ones_like(x)]).T
    coef, *_ = np.linalg.lstsq(A, y, rcond=None)
    slope, intercept = float(coef[0]), float(coef[1])

    yhat = slope * x + intercept
    resid = y - yhat
    sigma = float(np.sqrt(np.mean(resid**2))) if len(resid) > 2 else float("nan")

    # damp slope to avoid runaway
    slope_d = 0.5 * slope
    next_x = (len(y) - 1) + horizon_weeks
    # anchor at last fitted point
    anchor = yhat[-1]
    pred = float(anchor + slope_d * horizon_weeks)
    return pred, sigma


def to_weekly(blended: pd.DataFrame, date_col: str = "date_end") -> pd.DataFrame:
    df = blended.copy()
    df[date_col] = pd.to_datetime(df[date_col])
    df = df.sort_values(date_col).set_index(date_col)

    party_cols = [c for c in df.columns if c != "n_polls"]
    daily = pd.date_range(start=df.index.min(), end=df.index.max(), freq="D")
    daily_df = df[party_cols].reindex(daily).interpolate(method="time")
    weekly = daily_df.reindex(pd.date_range(daily_df.index.min(), daily_df.index.max(), freq="W-MON"))
    weekly.index.name = "week_monday"
    return weekly


def main():
    outputs_dir = Path("outputs")
    blended_path = outputs_dir / "weighted_time_series.xlsx"

    if blended_path.exists():
        blended = pd.read_excel(blended_path)
    else:
        fallback_path = outputs_dir / "weighted_poll_9_agencies_all_parties_2025_present.xlsx"
        if not fallback_path.exists():
            raise FileNotFoundError(
                "No blended input found. Expected either "
                "'outputs/weighted_time_series.xlsx' or "
                "'outputs/weighted_poll_9_agencies_all_parties_2025_present.xlsx'."
            )
        blended = pd.read_excel(fallback_path, sheet_name="weighted_time_series")

    weekly = to_weekly(blended)

    forecast_rows = []
    for col in weekly.columns:
        pred, sigma = forecast_next(weekly[col])
        forecast_rows.append({"party": col, "next_week_pred": pred, "rmse": sigma})

    out = pd.DataFrame(forecast_rows)
    outputs_dir.mkdir(parents=True, exist_ok=True)
    out.to_excel(outputs_dir / "forecast_next_week.xlsx", index=False)
    print(out.sort_values("rmse").head(10))


if __name__ == "__main__":
    main()
