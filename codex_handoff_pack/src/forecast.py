from __future__ import annotations

from forecast_core.config import parse_args
from forecast_core.runner import run_forecast


def main() -> None:
    cfg = parse_args()
    run_forecast(cfg)


if __name__ == "__main__":
    main()
