"""
Forecast skeleton:
- converts blended date_end series to weekly Mondays
- produces 1-week-ahead forecast per party (legacy trend or local-level state-space)
"""
from __future__ import annotations

import argparse
import json
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


def _kalman_local_level_nll(y: np.ndarray, q: float, r: float) -> float:
    mu = float(y[0])
    p = max(float(np.var(y)), 1.0)
    nll = 0.0
    for t in range(1, len(y)):
        # predict
        mu_pred = mu
        p_pred = p + q
        s = p_pred + r
        if s <= 0 or not np.isfinite(s):
            return float("inf")
        e = float(y[t] - mu_pred)
        nll += 0.5 * (np.log(s) + (e * e) / s)
        # update
        k = p_pred / s
        mu = mu_pred + k * e
        p = (1.0 - k) * p_pred
    return float(nll)


def _fit_local_level_params(y: np.ndarray) -> tuple[float, float]:
    var_y = float(np.var(y))
    scale = max(var_y, 1e-3)
    r_grid = [0.05, 0.1, 0.2, 0.4, 0.8, 1.2]
    q_grid = [0.001, 0.003, 0.01, 0.03, 0.07, 0.15, 0.3]
    best = (float("inf"), 0.02 * scale, 0.2 * scale)
    for rf in r_grid:
        for qf in q_grid:
            r = rf * scale
            q = qf * scale
            nll = _kalman_local_level_nll(y, q=q, r=r)
            if nll < best[0]:
                best = (nll, q, r)
    return float(best[1]), float(best[2])


def forecast_next_ssm(
    series: pd.Series,
    horizon_weeks: int = 1,
    window_weeks: int = 24,
    q_scale: float = 1.0,
) -> tuple[float, float, float]:
    s = series.dropna()
    if len(s) < 8:
        pred, rmse = forecast_next(s, horizon_weeks=horizon_weeks, window_weeks=window_weeks)
        return pred, float("nan"), rmse

    s = s.iloc[-window_weeks:] if len(s) > window_weeks else s
    y = s.to_numpy(dtype=float)
    q, r = _fit_local_level_params(y)
    q = max(q * float(q_scale), 1e-9)

    mu = float(y[0])
    p = max(float(np.var(y)), 1.0)
    pred_errors = []
    for t in range(1, len(y)):
        mu_pred = mu
        p_pred = p + q
        s_var = p_pred + r
        e = float(y[t] - mu_pred)
        pred_errors.append(e)
        k = p_pred / s_var
        mu = mu_pred + k * e
        p = (1.0 - k) * p_pred

    # h-step ahead latent and observed variance
    p_future = p + horizon_weeks * q
    pred_mean = float(mu)
    pred_sd = float(np.sqrt(max(p_future + r, 1e-9)))
    rmse = float(np.sqrt(np.mean(np.square(pred_errors)))) if pred_errors else float("nan")
    return pred_mean, pred_sd, rmse


def detect_regime_shift(weekly: pd.DataFrame) -> dict:
    focus = [c for c in ["더불어민주당", "국민의힘", "지지정당\n없음"] if c in weekly.columns]
    if not focus:
        return {"triggered": False, "reasons": ["focus_parties_missing"], "score": 0.0}

    recent_w = 4
    base_w = 12
    stats = []
    reasons = []
    for p in focus:
        s = weekly[p].dropna()
        if len(s) < recent_w + base_w + 1:
            continue
        d = s.diff().dropna()
        recent = d.iloc[-recent_w:]
        base = d.iloc[-(recent_w + base_w):-recent_w]
        base_std = float(base.std(ddof=0))
        recent_abs = float(recent.abs().mean())
        z = recent_abs / max(base_std, 1e-6)
        stats.append(z)
        if z >= 2.0:
            reasons.append(f"{p}:volatility_z={z:.2f}")
    score = float(max(stats)) if stats else 0.0
    triggered = bool(reasons)
    if not stats:
        return {"triggered": False, "reasons": ["insufficient_history"], "score": 0.0}
    return {"triggered": triggered, "reasons": reasons if reasons else ["normal"], "score": score}


def load_approval_weekly(path: Path) -> pd.Series:
    if not path.exists():
        return pd.Series(dtype=float)
    try:
        df = pd.read_csv(path)
    except Exception:
        return pd.Series(dtype=float)
    if "week_monday" not in df.columns or "approve" not in df.columns:
        return pd.Series(dtype=float)
    df["week_monday"] = pd.to_datetime(df["week_monday"], errors="coerce")
    df["approve"] = pd.to_numeric(df["approve"], errors="coerce")
    df = df.dropna(subset=["week_monday", "approve"]).sort_values("week_monday")
    if df.empty:
        return pd.Series(dtype=float)
    s = pd.Series(df["approve"].values, index=pd.DatetimeIndex(df["week_monday"]), name="approve")
    s = s.sort_index()

    # Outlier clean (for model input only): suppress abrupt jumps in weekly diff.
    d = s.diff()
    med = float(d.dropna().median()) if d.notna().any() else 0.0
    mad = float((d.dropna() - med).abs().median()) if d.notna().any() else 0.0
    thr = max(8.0, 3.5 * max(mad, 1e-6))
    spike_mask = (d - med).abs() > thr
    s_clean = s.copy()
    s_clean[spike_mask] = np.nan
    s_clean = s_clean.interpolate(method="time", limit_area="inside")
    return s_clean


def forecast_next_ssm_with_exog(
    series: pd.Series,
    approval_weekly: pd.Series,
    horizon_weeks: int = 1,
    window_weeks: int = 24,
    q_scale: float = 1.0,
) -> tuple[float, float, float]:
    base_pred, pred_sd, rmse = forecast_next_ssm(
        series=series,
        horizon_weeks=horizon_weeks,
        window_weeks=window_weeks,
        q_scale=q_scale,
    )
    s = series.dropna()
    if len(s) < 12 or approval_weekly.empty:
        return base_pred, pred_sd, rmse

    df = pd.DataFrame({"y": s.astype(float)})
    df = df.join(approval_weekly.rename("x"), how="left")
    df = df.dropna(subset=["y", "x"]).sort_index()
    if len(df) < 12:
        return base_pred, pred_sd, rmse
    if len(df) > window_weeks:
        df = df.iloc[-window_weeks:]

    # ARX(1): y_{t+1} = a + b*y_t + c*x_t
    y_t = df["y"].iloc[:-1].to_numpy(dtype=float)
    x_t = df["x"].iloc[:-1].to_numpy(dtype=float)
    y_tp1 = df["y"].iloc[1:].to_numpy(dtype=float)
    if len(y_tp1) < 8:
        return base_pred, pred_sd, rmse

    X = np.column_stack([np.ones_like(y_t), y_t, x_t])
    # Ridge-stabilized closed-form for small samples.
    ridge = 1e-3 * np.eye(X.shape[1])
    beta = np.linalg.solve(X.T @ X + ridge, X.T @ y_tp1)
    y_last = float(df["y"].iloc[-1])
    x_last = float(df["x"].iloc[-1])
    pred_arx = float(beta[0] + beta[1] * y_last + beta[2] * x_last)

    # Blend to preserve baseline stability.
    pred = 0.65 * float(base_pred) + 0.35 * pred_arx
    return float(pred), pred_sd, rmse


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
    ap = argparse.ArgumentParser(description="Forecast next-week party support from blended series.")
    ap.add_argument("--model", choices=["legacy", "ssm"], default="ssm")
    ap.add_argument("--window-weeks", type=int, default=24)
    ap.add_argument("--horizon-weeks", type=int, default=1)
    ap.add_argument("--regime-guard", choices=["on", "off"], default="on")
    ap.add_argument("--regime-q-scale", type=float, default=2.0, help="Q scale when regime shift is triggered")
    ap.add_argument("--exog-approval", choices=["off", "on"], default="off")
    ap.add_argument("--approval-weekly-csv", default="outputs/president_approval_weekly.csv")
    args = ap.parse_args()

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
    regime = detect_regime_shift(weekly) if args.regime_guard == "on" else {"triggered": False, "reasons": ["disabled"], "score": 0.0}
    q_scale = args.regime_q_scale if regime.get("triggered", False) else 1.0
    approval_weekly = load_approval_weekly(Path(args.approval_weekly_csv)) if args.exog_approval == "on" else pd.Series(dtype=float)

    forecast_rows = []
    for col in weekly.columns:
        if args.model == "legacy":
            pred, sigma = forecast_next(
                weekly[col], horizon_weeks=args.horizon_weeks, window_weeks=args.window_weeks
            )
            row = {"party": col, "next_week_pred": pred, "rmse": sigma, "pred_sd": np.nan}
        else:
            if args.exog_approval == "on":
                pred, pred_sd, sigma = forecast_next_ssm_with_exog(
                    series=weekly[col],
                    approval_weekly=approval_weekly,
                    horizon_weeks=args.horizon_weeks,
                    window_weeks=args.window_weeks,
                    q_scale=q_scale,
                )
            else:
                pred, pred_sd, sigma = forecast_next_ssm(
                    weekly[col], horizon_weeks=args.horizon_weeks, window_weeks=args.window_weeks, q_scale=q_scale
                )
            row = {"party": col, "next_week_pred": pred, "rmse": sigma, "pred_sd": pred_sd}
        z80 = 1.2815515655446004
        if pd.notna(row["pred_sd"]):
            row["pred_lo_80"] = float(row["next_week_pred"] - z80 * row["pred_sd"])
            row["pred_hi_80"] = float(row["next_week_pred"] + z80 * row["pred_sd"])
        else:
            row["pred_lo_80"] = np.nan
            row["pred_hi_80"] = np.nan
        row["model"] = args.model
        row["exog_approval"] = args.exog_approval
        forecast_rows.append(row)

    out = pd.DataFrame(forecast_rows)
    outputs_dir.mkdir(parents=True, exist_ok=True)
    out.to_excel(outputs_dir / "forecast_next_week.xlsx", index=False)
    regime_out = outputs_dir / "regime_status.json"
    regime_payload = {
        "triggered": bool(regime.get("triggered", False)),
        "reasons": regime.get("reasons", []),
        "score": float(regime.get("score", 0.0)),
        "q_scale_applied": float(q_scale),
        "model": args.model,
        "exog_approval": args.exog_approval,
        "approval_rows": int(len(approval_weekly)),
    }
    regime_out.write_text(json.dumps(regime_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Wrote:", regime_out)
    print(out.sort_values("rmse").head(10))


if __name__ == "__main__":
    main()
