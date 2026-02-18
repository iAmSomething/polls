from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from .constants import POLLSTERS
from .sheet_loading import _parse_sample_size_col, get_party_cols
def blend_time_series(
    df: pd.DataFrame,
    weights: Dict[str, float],
    sample_size_weight: bool = False,
    sample_eps: float = 0.01,
) -> pd.DataFrame:
    """
    Group by date_end and compute weighted mean per party column.
    Missing values are ignored per-party.
    """
    df = df[df["조사기관"].isin(POLLSTERS)].copy()
    party_cols = get_party_cols(df)

    for c in party_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    if "표본수(명)" in df.columns:
        df["표본수(명)"] = _parse_sample_size_col(df["표본수(명)"])

    rows = []
    for d, g in df.groupby("date_end"):
        row = {"date_end": d, "n_polls": len(g)}
        for party in party_cols:
            cols = ["조사기관", party] + (["표본수(명)"] if "표본수(명)" in g.columns else [])
            vals = g[cols].dropna(subset=[party])
            if len(vals) == 0:
                row[party] = np.nan
                continue
            w = np.array([weights.get(a, 0.0) for a in vals["조사기관"]], dtype=float)
            v = vals[party].to_numpy(dtype=float)
            if sample_size_weight and "표본수(명)" in vals.columns:
                n = vals["표본수(명)"].to_numpy(dtype=float)
                # p in [0,1], clipped for stable variance near 0/1.
                p = np.clip(v / 100.0, sample_eps, 1.0 - sample_eps)
                with np.errstate(divide="ignore", invalid="ignore"):
                    var_obs = p * (1.0 - p) / np.maximum(n, 1.0)
                    obs_w = 1.0 / np.maximum(var_obs, 1e-9)
                obs_w = np.where(np.isfinite(obs_w), obs_w, 0.0)
                w = w * obs_w
            if np.sum(w) <= 0:
                w = np.array([weights.get(a, 0.0) for a in vals["조사기관"]], dtype=float)
            if np.sum(w) <= 0:
                row[party] = np.nan
                continue
            row[party] = float(np.sum(w * v) / np.sum(w))
        rows.append(row)

    return pd.DataFrame(rows).sort_values("date_end")


def apply_time_varying_house_effect(
    df: pd.DataFrame,
    weights: Dict[str, float],
    ewma_lambda: float = 0.8,
    bias_clip: float = 6.0,
    min_obs: int = 3,
    sample_size_weight: bool = False,
    sample_eps: float = 0.01,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Estimate pollster-party time-varying house bias via lagged EWMA residuals.
    - residual_t = raw_t - baseline_t(date, party)
    - bias_state_t = lambda * bias_state_{t-1} + (1-lambda) * residual_t
    - adjustment applied at t uses prior state (lagged), clipped by +/- bias_clip
    """
    if not (0.0 <= ewma_lambda < 1.0):
        raise ValueError("ewma_lambda must be in [0, 1).")
    if min_obs < 0:
        raise ValueError("min_obs must be >= 0.")

    work = df[df["조사기관"].isin(POLLSTERS)].copy()
    party_cols = get_party_cols(work)
    if work.empty or not party_cols:
        return work, pd.DataFrame(
            columns=["date_end", "pollster", "party", "raw_value", "baseline_value", "residual", "house_bias", "adj_value", "obs_count"]
        )

    for c in party_cols:
        work[c] = pd.to_numeric(work[c], errors="coerce")

    baseline = blend_time_series(
        work,
        weights,
        sample_size_weight=sample_size_weight,
        sample_eps=sample_eps,
    )
    baseline = baseline[["date_end"] + party_cols].copy()
    baseline = baseline.rename(columns={p: f"__baseline__{p}" for p in party_cols})
    work = work.merge(baseline, on="date_end", how="left")

    work = work.sort_values(["조사기관", "date_end", "등록번호"], na_position="last").copy()
    diag_rows: List[Dict[str, float | str | pd.Timestamp]] = []

    for party in party_cols:
        bcol = f"__baseline__{party}"
        ac = work[party].to_numpy(dtype=float)
        bc = work[bcol].to_numpy(dtype=float)
        pollsters = work["조사기관"].astype(str).to_numpy()
        dates = work["date_end"].to_numpy()

        state_by_pollster: Dict[str, float] = {}
        cnt_by_pollster: Dict[str, int] = {}
        adjusted = ac.copy()
        house_bias_used = np.full(len(work), np.nan, dtype=float)
        residual_arr = np.full(len(work), np.nan, dtype=float)
        obs_count_arr = np.full(len(work), 0, dtype=int)

        for i in range(len(work)):
            raw = ac[i]
            base = bc[i]
            if np.isnan(raw) or np.isnan(base):
                continue

            pollster = pollsters[i]
            prev_state = state_by_pollster.get(pollster, 0.0)
            prev_count = cnt_by_pollster.get(pollster, 0)

            used_bias = float(np.clip(prev_state, -bias_clip, bias_clip)) if prev_count >= min_obs else 0.0
            residual = float(raw - base)
            adj = float(raw - used_bias)

            adjusted[i] = adj
            house_bias_used[i] = used_bias
            residual_arr[i] = residual
            obs_count_arr[i] = prev_count + 1

            state_by_pollster[pollster] = ewma_lambda * prev_state + (1.0 - ewma_lambda) * residual
            cnt_by_pollster[pollster] = prev_count + 1

            diag_rows.append(
                {
                    "date_end": dates[i],
                    "pollster": pollster,
                    "party": party,
                    "raw_value": raw,
                    "baseline_value": base,
                    "residual": residual,
                    "house_bias": used_bias,
                    "adj_value": adj,
                    "obs_count": prev_count + 1,
                }
            )

        work[party] = adjusted
        work[f"__house_bias__{party}"] = house_bias_used
        work[f"__residual__{party}"] = residual_arr
        work[f"__obs_count__{party}"] = obs_count_arr

    drop_cols = [c for c in work.columns if c.startswith("__baseline__")]
    work = work.drop(columns=drop_cols, errors="ignore")
    diag_df = pd.DataFrame(diag_rows).sort_values(["date_end", "pollster", "party"])
    return work, diag_df


