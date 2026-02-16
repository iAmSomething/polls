"""
Pipeline skeleton for:
- loading Excel sheets (2025/2026)
- cleaning headers (party names) + renaming 민주당
- parsing date ranges
- blending 9 pollsters with accuracy weights

Fill in paths and extend as needed in Codex.
"""
from __future__ import annotations

import argparse
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


POLLSTERS: List[str] = [
    "리서치앤리서치",
    "엠브레인퍼블릭",
    "리서치뷰",
    "에이스리서치",
    "한국리서치",
    "조원씨앤아이",
    "알앤써치",
    "리얼미터",
    "코리아리서치인터내셔널",
]

SHEETS: List[str] = [
    "정당지지도 (25.1.1~12.31.)",
    "정당지지도 (26.1.1~)",
]

BASE_COLS = {
    "등록번호",
    "조사기관",
    "의뢰자",
    "조사일자",
    "조사방법",
    "표본추출틀",
    "표본수(명)",
    "접촉률(%)",
    "응답률(%)",
    "95%신뢰수준\n표본오차(%p)",
    "date_start",
    "date_end",
    "date_mid",
}


def _normalize_path(data_dir: Path, explicit: Optional[str]) -> Optional[Path]:
    if explicit is None:
        return None
    p = Path(explicit)
    if not p.is_absolute():
        p = data_dir / p
    if not p.exists():
        raise FileNotFoundError(f"File not found: {p}")
    return p


def _looks_like_raw_poll_xlsx(path: Path) -> bool:
    try:
        x = pd.ExcelFile(path)
        return all(s in x.sheet_names for s in SHEETS)
    except Exception:
        return False


def _looks_like_mae_xlsx(path: Path) -> bool:
    try:
        df = pd.read_excel(path, sheet_name=0, nrows=5)
    except Exception:
        return False
    cols = [str(c) for c in df.columns]
    has_pollster = "조사기관" in cols
    has_mae = any("MAE" in c.upper() for c in cols)
    return has_pollster and has_mae


def resolve_inputs(input_xlsx: Optional[str], mae_xlsx: Optional[str], data_dir: str) -> Tuple[Path, Path]:
    d = Path(data_dir)
    d.mkdir(parents=True, exist_ok=True)
    input_path = _normalize_path(d, input_xlsx)
    mae_path = _normalize_path(d, mae_xlsx)

    candidates = sorted(d.glob("*.xlsx"), key=lambda x: x.stat().st_mtime, reverse=True)

    if input_path is None:
        for c in candidates:
            if _looks_like_raw_poll_xlsx(c):
                input_path = c
                break
        if input_path is None:
            raise FileNotFoundError(f"No raw polling workbook found in: {d}")

    if mae_path is None:
        for c in candidates:
            if c == input_path:
                continue
            if _looks_like_mae_xlsx(c):
                mae_path = c
                break
        if mae_path is None:
            raise FileNotFoundError(f"No MAE workbook found in: {d}")

    if input_path == mae_path:
        raise ValueError(
            "Input and MAE paths resolved to the same file. "
            "Pass explicit --input-xlsx and --mae-xlsx values."
        )
    return input_path, mae_path


def parse_range(s: str) -> Tuple[pd.Timestamp, pd.Timestamp]:
    """
    Parse '조사일자' like:
      - '25.01.02.~03.'
      - '25.01.02~03.'
      - '25.01.02.~25.01.03.'

    Returns (start, end). If end lacks month/year, inherit from start.
    """
    if s is None or (isinstance(s, float) and np.isnan(s)):
        return (pd.NaT, pd.NaT)

    s = str(s).strip().replace(" ", "")
    parts = re.split(r"[~/]", s)
    if len(parts) == 1:
        a = b = parts[0]
    else:
        a, b = parts[0], parts[-1]

    def norm_date(token: str, ref: pd.Timestamp | None = None) -> pd.Timestamp:
        token = str(token).strip()
        if token == "":
            return pd.NaT

        # end date like '31.' only
        if re.fullmatch(r"\d{1,2}\.?", token):
            if ref is None or pd.isna(ref):
                return pd.NaT
            day = int(re.sub(r"\D", "", token))
            return pd.Timestamp(ref).replace(day=day)

        token = token.rstrip(".")
        try:
            return pd.Timestamp(datetime.strptime("20" + token, "%Y.%m.%d"))
        except Exception:
            return pd.NaT

    a_dt = norm_date(a)
    b_dt = norm_date(b, a_dt)
    return (a_dt, b_dt)


def load_sheet(xlsx_path: Path, sheet: str) -> pd.DataFrame:
    raw = pd.read_excel(xlsx_path, sheet_name=sheet, header=0)
    header_row = raw.iloc[0]
    cols = list(raw.columns)

    start_idx = cols.index("정당지지율(%)") + 1
    base_cols = cols[:start_idx]

    party_names: List[str] = []
    for c in cols[start_idx:]:
        v = header_row[c]
        party_names.append(str(v).strip() if not pd.isna(v) else str(c))

    df = raw.iloc[1:].copy()
    df.columns = list(base_cols) + party_names

    # 2025/2026: '정당지지율(%)' column is 민주당 value
    if "국민의힘" in df.columns and "더불어민주당" not in df.columns:
        df = df.rename(columns={"정당지지율(%)": "더불어민주당"})

    # parse dates
    ranges = df["조사일자"].apply(parse_range)
    df["date_start"] = ranges.apply(lambda x: x[0])
    df["date_end"] = ranges.apply(lambda x: x[1])
    df["date_mid"] = df[["date_start", "date_end"]].mean(axis=1)
    return df


def compute_weights_from_mae(mae_xlsx: Path) -> Dict[str, float]:
    """
    Expects a sheet with at least columns:
      - 조사기관
      - MAE (or a column whose name contains 'MAE')
    Weight = 1/MAE, normalized to sum to 1.
    """
    wdf = pd.read_excel(mae_xlsx, sheet_name=0)

    mae_col = None
    for c in wdf.columns:
        if "MAE" in str(c).upper():
            mae_col = c
            break
    if mae_col is None:
        raise ValueError("MAE column not found in mae_xlsx")

    wdf = wdf[wdf["조사기관"].isin(POLLSTERS)].copy()
    wdf[mae_col] = pd.to_numeric(wdf[mae_col], errors="coerce")
    wdf = wdf.dropna(subset=[mae_col])

    weights = (1.0 / wdf.set_index("조사기관")[mae_col]).to_dict()
    s = sum(weights.values())
    return {k: v / s for k, v in weights.items()}


def build_weights_table(mae_xlsx: Path, weights: Dict[str, float]) -> pd.DataFrame:
    wdf = pd.read_excel(mae_xlsx, sheet_name=0)
    mae_col = None
    for c in wdf.columns:
        if "MAE" in str(c).upper():
            mae_col = c
            break
    if mae_col is None:
        raise ValueError("MAE column not found in mae_xlsx")

    wdf = wdf[wdf["조사기관"].isin(POLLSTERS)].copy()
    wdf[mae_col] = pd.to_numeric(wdf[mae_col], errors="coerce")
    wdf = wdf.dropna(subset=[mae_col])
    out = wdf[["조사기관", mae_col]].copy()
    out = out.rename(columns={mae_col: "mae"})
    out["weight"] = out["조사기관"].map(weights).fillna(0.0)
    out["weight_pct"] = out["weight"] * 100.0
    return out.sort_values("weight", ascending=False).reset_index(drop=True)


def get_party_cols(df: pd.DataFrame) -> List[str]:
    return [c for c in df.columns if c not in BASE_COLS and not str(c).startswith("__")]


def _parse_sample_size_col(s: pd.Series) -> pd.Series:
    cleaned = (
        s.astype(str)
        .str.replace(",", "", regex=False)
        .str.replace(r"[^\d.]", "", regex=True)
        .replace("", np.nan)
    )
    return pd.to_numeric(cleaned, errors="coerce")


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


def main():
    parser = argparse.ArgumentParser(description="Build weighted blended poll time series.")
    parser.add_argument("--input-xlsx", default=None, help="Raw polling workbook path or filename under --data-dir")
    parser.add_argument("--mae-xlsx", default=None, help="Pollster MAE workbook path or filename under --data-dir")
    parser.add_argument("--data-dir", default="data", help="Directory to search for input files")
    parser.add_argument("--out", default="outputs/weighted_time_series.xlsx", help="Output XLSX path")
    parser.add_argument("--house-effect", choices=["on", "off"], default="on", help="Enable time-varying house-effect adjustment")
    parser.add_argument("--house-lambda", type=float, default=0.8, help="EWMA lambda for house-effect update")
    parser.add_argument("--house-clip", type=float, default=6.0, help="Absolute clip for lagged house bias (percentage points)")
    parser.add_argument("--house-min-obs", type=int, default=3, help="Minimum prior observations per pollster-party to apply bias adjustment")
    parser.add_argument("--house-out", default="outputs/house_effect_timeseries.csv", help="House-effect diagnostic CSV path")
    parser.add_argument("--sample-size-weight", choices=["on", "off"], default="on", help="Enable sample-size-aware observation weighting")
    parser.add_argument("--sample-eps", type=float, default=0.01, help="Probability clip epsilon for variance weighting")
    args = parser.parse_args()

    try:
        xlsx, mae_xlsx = resolve_inputs(args.input_xlsx, args.mae_xlsx, args.data_dir)
    except Exception as e:
        raise SystemExit(
            "Input resolution failed. Place two .xlsx files under data/ or pass --input-xlsx and --mae-xlsx.\n"
            f"Detail: {e}"
        )
    print(f"Using input workbook: {xlsx}")
    print(f"Using MAE workbook:   {mae_xlsx}")

    df = pd.concat([load_sheet(xlsx, s) for s in SHEETS], ignore_index=True)
    weights = compute_weights_from_mae(mae_xlsx)
    use_sample_w = args.sample_size_weight == "on"
    house_diag_df = pd.DataFrame()
    if args.house_effect == "on":
        df_adj, house_diag_df = apply_time_varying_house_effect(
            df=df,
            weights=weights,
            ewma_lambda=args.house_lambda,
            bias_clip=args.house_clip,
            min_obs=args.house_min_obs,
            sample_size_weight=use_sample_w,
            sample_eps=args.sample_eps,
        )
        blended = blend_time_series(
            df_adj,
            weights,
            sample_size_weight=use_sample_w,
            sample_eps=args.sample_eps,
        )
    else:
        blended = blend_time_series(
            df,
            weights,
            sample_size_weight=use_sample_w,
            sample_eps=args.sample_eps,
        )
    weights_df = build_weights_table(mae_xlsx, weights)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        blended.to_excel(writer, sheet_name="weighted_time_series", index=False)
        weights_df.to_excel(writer, sheet_name="weights", index=False)

    weights_csv = out.parent / "weights.csv"
    weights_df.to_csv(weights_csv, index=False)
    if args.house_effect == "on":
        house_out = Path(args.house_out)
        house_out.parent.mkdir(parents=True, exist_ok=True)
        house_diag_df.to_csv(house_out, index=False)
        print("Wrote:", house_out)
    print("Wrote:", out)
    print("Wrote:", weights_csv)


if __name__ == "__main__":
    main()
