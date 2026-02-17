from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

import pandas as pd

from .constants import SHEETS
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


