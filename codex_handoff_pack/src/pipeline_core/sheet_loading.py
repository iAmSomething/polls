from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

import numpy as np
import pandas as pd

from .constants import BASE_COLS
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


