from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
def load_blended_input(outputs_dir: Path) -> pd.DataFrame:
    blended_path = outputs_dir / "weighted_time_series.xlsx"
    if blended_path.exists():
        return pd.read_excel(blended_path)
    fallback_path = outputs_dir / "weighted_poll_9_agencies_all_parties_2025_present.xlsx"
    if not fallback_path.exists():
        raise FileNotFoundError(
            "No blended input found. Expected either "
            "'outputs/weighted_time_series.xlsx' or "
            "'outputs/weighted_poll_9_agencies_all_parties_2025_present.xlsx'."
        )
    return pd.read_excel(fallback_path, sheet_name="weighted_time_series")




def write_forecast_outputs(outputs_dir: Path, out: pd.DataFrame, regime_payload: dict) -> Path:
    outputs_dir.mkdir(parents=True, exist_ok=True)
    out.to_excel(outputs_dir / "forecast_next_week.xlsx", index=False)
    regime_out = outputs_dir / "regime_status.json"
    regime_out.write_text(json.dumps(regime_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return regime_out
