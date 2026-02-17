from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
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


