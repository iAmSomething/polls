from __future__ import annotations

from pathlib import Path

import pandas as pd

from .blending import apply_time_varying_house_effect, blend_time_series
from .config import PipelineConfig
from .constants import SHEETS
from .input_resolution import resolve_inputs
from .sheet_loading import load_sheet
from .weights import build_weights_table, compute_weights_from_mae
def run_pipeline(cfg: PipelineConfig) -> tuple[Path, Path]:
    try:
        xlsx, mae_xlsx = resolve_inputs(cfg.input_xlsx, cfg.mae_xlsx, cfg.data_dir)
    except Exception as e:
        raise SystemExit(
            "Input resolution failed. Place two .xlsx files under data/ or pass --input-xlsx and --mae-xlsx.\n"
            f"Detail: {e}"
        )
    print(f"Using input workbook: {xlsx}")
    print(f"Using MAE workbook:   {mae_xlsx}")

    df = pd.concat([load_sheet(xlsx, s) for s in SHEETS], ignore_index=True)
    weights = compute_weights_from_mae(mae_xlsx)
    use_sample_w = cfg.sample_size_weight == "on"
    house_diag_df = pd.DataFrame()
    if cfg.house_effect == "on":
        df_adj, house_diag_df = apply_time_varying_house_effect(
            df=df,
            weights=weights,
            ewma_lambda=cfg.house_lambda,
            bias_clip=cfg.house_clip,
            min_obs=cfg.house_min_obs,
            sample_size_weight=use_sample_w,
            sample_eps=cfg.sample_eps,
        )
        blended = blend_time_series(
            df_adj,
            weights,
            sample_size_weight=use_sample_w,
            sample_eps=cfg.sample_eps,
        )
    else:
        blended = blend_time_series(
            df,
            weights,
            sample_size_weight=use_sample_w,
            sample_eps=cfg.sample_eps,
        )
    weights_df = build_weights_table(mae_xlsx, weights)

    out = Path(cfg.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        blended.to_excel(writer, sheet_name="weighted_time_series", index=False)
        weights_df.to_excel(writer, sheet_name="weights", index=False)

    weights_csv = out.parent / "weights.csv"
    weights_df.to_csv(weights_csv, index=False)
    if cfg.house_effect == "on":
        house_out = Path(cfg.house_out)
        house_out.parent.mkdir(parents=True, exist_ok=True)
        house_diag_df.to_csv(house_out, index=False)
        print("Wrote:", house_out)
    print("Wrote:", out)
    print("Wrote:", weights_csv)
    return out, weights_csv


