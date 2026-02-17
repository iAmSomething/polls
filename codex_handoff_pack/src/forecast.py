from __future__ import annotations

from forecast_core.config import parse_args
from forecast_core.features import detect_regime_shift, load_approval_weekly, to_weekly
from forecast_core.models import forecast_next, forecast_next_ssm, forecast_next_ssm_with_exog
from forecast_core.runner import run_forecast

__all__ = [
    "detect_regime_shift",
    "forecast_next",
    "forecast_next_ssm",
    "forecast_next_ssm_with_exog",
    "load_approval_weekly",
    "to_weekly",
    "parse_args",
    "run_forecast",
]


def main() -> None:
    cfg = parse_args()
    run_forecast(cfg)


if __name__ == "__main__":
    main()
