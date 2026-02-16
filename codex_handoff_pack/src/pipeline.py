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


def blend_time_series(df: pd.DataFrame, weights: Dict[str, float]) -> pd.DataFrame:
    """
    Group by date_end and compute weighted mean per party column.
    Missing values are ignored per-party.
    """
    df = df[df["조사기관"].isin(POLLSTERS)].copy()

    base_cols = {
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
    party_cols = [c for c in df.columns if c not in base_cols]

    for c in party_cols + ["표본수(명)"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    rows = []
    for d, g in df.groupby("date_end"):
        row = {"date_end": d, "n_polls": len(g)}
        for party in party_cols:
            vals = g[["조사기관", party]].dropna()
            if len(vals) == 0:
                row[party] = np.nan
                continue
            w = np.array([weights.get(a, 0.0) for a in vals["조사기관"]], dtype=float)
            v = vals[party].to_numpy(dtype=float)
            row[party] = float(np.sum(w * v) / np.sum(w))
        rows.append(row)

    return pd.DataFrame(rows).sort_values("date_end")


def main():
    parser = argparse.ArgumentParser(description="Build weighted blended poll time series.")
    parser.add_argument("--input-xlsx", default=None, help="Raw polling workbook path or filename under --data-dir")
    parser.add_argument("--mae-xlsx", default=None, help="Pollster MAE workbook path or filename under --data-dir")
    parser.add_argument("--data-dir", default="data", help="Directory to search for input files")
    parser.add_argument("--out", default="outputs/weighted_time_series.xlsx", help="Output XLSX path")
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
    blended = blend_time_series(df, weights)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    blended.to_excel(out, index=False)
    print("Wrote:", out)


if __name__ == "__main__":
    main()
