from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


def _ensure_weekly_range(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["week_monday"] = pd.to_datetime(out["week_monday"], errors="coerce")
    out = out.dropna(subset=["week_monday"]).sort_values("week_monday")
    if out.empty:
        return out
    full_idx = pd.date_range(out["week_monday"].min(), out["week_monday"].max(), freq="7D")
    out = out.set_index("week_monday").reindex(full_idx).reset_index().rename(columns={"index": "week_monday"})
    return out


def _outlier_mask(series: pd.Series) -> tuple[pd.Series, float]:
    d = series.diff()
    med = float(d.dropna().median()) if d.notna().any() else 0.0
    mad = float((d.dropna() - med).abs().median()) if d.notna().any() else 0.0
    thr = max(6.0, 3.5 * max(mad, 1e-6))
    mask = (d - med).abs() > thr
    return mask.fillna(False), thr


def build_outlier_report(weekly_raw: pd.DataFrame, weekly_filled: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for metric in ["approve", "disapprove"]:
        s_raw = pd.to_numeric(weekly_raw[metric], errors="coerce")
        mask, thr = _outlier_mask(s_raw)
        s_fill = pd.to_numeric(weekly_filled[metric], errors="coerce")
        for i in range(1, len(weekly_raw)):
            prev_v = s_raw.iloc[i - 1]
            cur_v = s_raw.iloc[i]
            diff = cur_v - prev_v if pd.notna(prev_v) and pd.notna(cur_v) else np.nan
            if not bool(mask.iloc[i]):
                continue
            rows.append(
                {
                    "week_monday": pd.to_datetime(weekly_raw.iloc[i]["week_monday"]).strftime("%Y-%m-%d"),
                    "metric": metric,
                    "prev_value": float(prev_v) if pd.notna(prev_v) else np.nan,
                    "value": float(cur_v) if pd.notna(cur_v) else np.nan,
                    "diff": float(diff) if pd.notna(diff) else np.nan,
                    "threshold": float(thr),
                    "is_outlier": True,
                    "suggested_value": float(s_fill.iloc[i]) if pd.notna(s_fill.iloc[i]) else np.nan,
                }
            )
    return pd.DataFrame(
        rows,
        columns=[
            "week_monday",
            "metric",
            "prev_value",
            "value",
            "diff",
            "threshold",
            "is_outlier",
            "suggested_value",
        ],
    )


def fill_missing_weekly(weekly: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = _ensure_weekly_range(weekly)
    if df.empty:
        return df, pd.DataFrame(columns=["week_monday", "fill_method"])
    for c in ["approve", "disapprove", "dk", "n_obs", "total_sample_n"]:
        if c not in df.columns:
            df[c] = np.nan
    for c in ["approve", "disapprove", "dk", "n_obs", "total_sample_n"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    miss_before = df["approve"].isna() | df["disapprove"].isna()
    # Fill only internal gaps to avoid extrapolation
    df["approve"] = df["approve"].interpolate(method="linear", limit_area="inside")
    df["disapprove"] = df["disapprove"].interpolate(method="linear", limit_area="inside")
    miss_after = df["approve"].isna() | df["disapprove"].isna()

    filled_mask = miss_before & (~miss_after)
    df.loc[filled_mask, "n_obs"] = 0
    df.loc[filled_mask, "total_sample_n"] = 0
    df.loc[df["dk"].isna() & df["approve"].notna() & df["disapprove"].notna(), "dk"] = (
        100.0 - df["approve"] - df["disapprove"]
    )
    fill_log = df.loc[filled_mask, ["week_monday"]].copy()
    fill_log["fill_method"] = "linear_interp"
    return df, fill_log


def update_detail_with_imputed(detail_path: Path, filled_weekly: pd.DataFrame, fill_log: pd.DataFrame) -> None:
    cols = [
        "week_start",
        "week_end",
        "approve",
        "disapprove",
        "dk",
        "pollster",
        "publisher",
        "poll_end_date",
        "source_title",
        "source_url",
        "notes",
    ]
    if detail_path.exists():
        d = pd.read_csv(detail_path)
    else:
        d = pd.DataFrame(columns=cols)
    for c in cols:
        if c not in d.columns:
            d[c] = ""
    if fill_log.empty:
        d.to_csv(detail_path, index=False, encoding="utf-8-sig")
        return

    fw = filled_weekly.copy()
    fw["week_monday"] = pd.to_datetime(fw["week_monday"], errors="coerce").dt.strftime("%Y-%m-%d")

    add_rows = []
    for _, r in fill_log.iterrows():
        ws = pd.to_datetime(r["week_monday"])
        key = ws.strftime("%Y-%m-%d")
        hit = fw[fw["week_monday"] == key]
        if hit.empty:
            continue
        row = hit.iloc[0]
        add_rows.append(
            {
                "week_start": ws.strftime("%Y-%m-%d"),
                "week_end": (ws + pd.Timedelta(days=6)).strftime("%Y-%m-%d"),
                "approve": float(row["approve"]),
                "disapprove": float(row["disapprove"]),
                "dk": float(row["dk"]) if pd.notna(row["dk"]) else np.nan,
                "pollster": "imputed",
                "publisher": "imputed",
                "poll_end_date": (ws + pd.Timedelta(days=6)).strftime("%Y-%m-%d"),
                "source_title": "결측 보완(선형)",
                "source_url": "",
                "notes": "imputed_linear",
            }
        )
    add_df = pd.DataFrame(add_rows)
    d = pd.concat([d[cols], add_df[cols]], ignore_index=True)
    d = d.drop_duplicates(subset=["week_start", "notes"], keep="last")
    d = d.sort_values("week_start")
    d.to_csv(detail_path, index=False, encoding="utf-8-sig")


def main() -> None:
    ap = argparse.ArgumentParser(description="Postprocess president approval weekly data: fill missing weeks + outlier report.")
    ap.add_argument("--weekly-csv", default="outputs/president_approval_weekly.csv")
    ap.add_argument("--detail-csv", default="outputs/president_approval_weekly_detail.csv")
    ap.add_argument("--out-outlier", default="outputs/president_approval_outlier_report.csv")
    args = ap.parse_args()

    base = Path(".")
    weekly_path = base / args.weekly_csv
    detail_path = base / args.detail_csv
    out_outlier = base / args.out_outlier

    if not weekly_path.exists():
        print(f"No weekly file: {weekly_path}")
        return

    raw = pd.read_csv(weekly_path)
    filled, fill_log = fill_missing_weekly(raw)
    report = build_outlier_report(raw, filled)

    weekly_path.parent.mkdir(parents=True, exist_ok=True)
    out_outlier.parent.mkdir(parents=True, exist_ok=True)

    filled["week_monday"] = pd.to_datetime(filled["week_monday"], errors="coerce").dt.strftime("%Y-%m-%d")
    filled.to_csv(weekly_path, index=False)
    report.to_csv(out_outlier, index=False)
    update_detail_with_imputed(detail_path, pd.read_csv(weekly_path), fill_log)

    print(f"Filled weeks: {len(fill_log)}")
    print(f"Wrote: {weekly_path}")
    print(f"Wrote: {detail_path}")
    print(f"Wrote: {out_outlier}")


if __name__ == "__main__":
    main()
