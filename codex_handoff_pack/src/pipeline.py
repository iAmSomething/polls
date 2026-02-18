from __future__ import annotations

from pipeline_core.config import parse_args
from pipeline_core.runner import run_pipeline


def main() -> None:
    cfg = parse_args()
    run_pipeline(cfg)


if __name__ == "__main__":
    main()
