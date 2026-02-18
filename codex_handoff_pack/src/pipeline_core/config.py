from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class PipelineConfig:
    input_xlsx: Optional[str]
    mae_xlsx: Optional[str]
    data_dir: str
    out: str
    house_effect: str
    house_lambda: float
    house_clip: float
    house_min_obs: int
    house_out: str
    sample_size_weight: str
    sample_eps: float


def parse_args() -> PipelineConfig:
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
    ns = parser.parse_args()
    return PipelineConfig(
        input_xlsx=ns.input_xlsx,
        mae_xlsx=ns.mae_xlsx,
        data_dir=ns.data_dir,
        out=ns.out,
        house_effect=ns.house_effect,
        house_lambda=ns.house_lambda,
        house_clip=ns.house_clip,
        house_min_obs=ns.house_min_obs,
        house_out=ns.house_out,
        sample_size_weight=ns.sample_size_weight,
        sample_eps=ns.sample_eps,
    )
