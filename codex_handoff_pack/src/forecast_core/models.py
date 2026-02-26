from __future__ import annotations

import numpy as np
import pandas as pd

RECENCY_SHRINK = 0.35
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
    # Pull the one-step forecast toward the latest observed level for faster adaptation.
    latest_y = float(y[-1])
    pred_mean = float((1.0 - RECENCY_SHRINK) * pred_mean + RECENCY_SHRINK * latest_y)
    pred_sd = float(np.sqrt(max(p_future + r, 1e-9)))
    rmse = float(np.sqrt(np.mean(np.square(pred_errors)))) if pred_errors else float("nan")
    return pred_mean, pred_sd, rmse


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
    latest_y = float(s.iloc[-1])
    pred = float((1.0 - RECENCY_SHRINK) * pred + RECENCY_SHRINK * latest_y)
    return float(pred), pred_sd, rmse

