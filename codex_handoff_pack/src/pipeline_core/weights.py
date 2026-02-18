from __future__ import annotations

from pathlib import Path
from typing import Dict

import pandas as pd

from .constants import POLLSTERS
def compute_weights_from_mae(mae_xlsx: Path) -> Dict[str, float]:
    """
    Expects a sheet with at least columns:
      - 조사기관
      - MAE (or a column whose name contains 'MAE')
    Weight = 1/MAE, normalized to sum to 1.
    """
    wdf = pd.read_excel(mae_xlsx, sheet_name=0)
    mae_col = _find_mae_column(wdf)

    wdf = wdf[wdf["조사기관"].isin(POLLSTERS)].copy()
    wdf[mae_col] = pd.to_numeric(wdf[mae_col], errors="coerce")
    wdf = wdf.dropna(subset=[mae_col])

    weights = (1.0 / wdf.set_index("조사기관")[mae_col]).to_dict()
    s = sum(weights.values())
    return {k: v / s for k, v in weights.items()}


def build_weights_table(mae_xlsx: Path, weights: Dict[str, float]) -> pd.DataFrame:
    wdf = pd.read_excel(mae_xlsx, sheet_name=0)
    mae_col = _find_mae_column(wdf)

    wdf = wdf[wdf["조사기관"].isin(POLLSTERS)].copy()
    wdf[mae_col] = pd.to_numeric(wdf[mae_col], errors="coerce")
    wdf = wdf.dropna(subset=[mae_col])
    out = wdf[["조사기관", mae_col]].copy()
    out = out.rename(columns={mae_col: "mae"})
    out["weight"] = out["조사기관"].map(weights).fillna(0.0)
    out["weight_pct"] = out["weight"] * 100.0
    return out.sort_values("weight", ascending=False).reset_index(drop=True)


def _find_mae_column(df: pd.DataFrame):
    for c in df.columns:
        if "MAE" in str(c).upper():
            return c
    raise ValueError("MAE column not found in mae_xlsx")


