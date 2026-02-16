"""
Weekly run skeleton:
- (optional) scrape latest public releases per pollster (only if full party breakdown is text-available)
- update blended series
- compare to last week's forecast, compute errors
- update weights to reduce error (placeholder)
- re-forecast next week

NOTE: This is a scaffold. Plug in your scraper and an optimizer.
"""
from __future__ import annotations

from pathlib import Path
import pandas as pd

WEIGHT_UPDATE_LOSS = "huber"  # selected default: robust to outliers
TEXT_ONLY_SCRAPING = True  # selected default: skip PDF/table parsing
RUN_SCHEDULE = "weekly_monday_09_00"
RUN_TIMEZONE = "Asia/Seoul"


def scrape_latest_public_points() -> pd.DataFrame:
    """
    Return a DataFrame with columns:
      - date_end
      - pollster
      - party columns (e.g., 더불어민주당, 국민의힘, ...)
    Only include rows where full party breakdown is available as text.
    """
    # TODO: implement per-publisher parsing rules.
    # Respect TEXT_ONLY_SCRAPING=True:
    # include only pages where full party breakdown is available in text.
    return pd.DataFrame()


def update_weights(prev_weights: pd.DataFrame, errors: pd.DataFrame) -> pd.DataFrame:
    """
    Placeholder for constrained optimization:
      minimize loss(errors; weights) s.t. w>=0, sum(w)=1

    Inputs:
      - prev_weights: columns [pollster, weight]
      - errors: per-week errors by pollster (design your schema)
    """
    # TODO: implement optimizer with simplex projection.
    # Use WEIGHT_UPDATE_LOSS='huber' as baseline.
    return prev_weights


def main():
    base_dir = Path(".")
    outputs = base_dir / "outputs"
    outputs.mkdir(exist_ok=True)
    print(f"Schedule: {RUN_SCHEDULE} ({RUN_TIMEZONE})")
    print(f"Weight loss: {WEIGHT_UPDATE_LOSS}, text-only scraping: {TEXT_ONLY_SCRAPING}")

    # Load current blended + weights
    blended_path = outputs / "weighted_time_series.xlsx"
    weights_path = outputs / "weights.csv"

    if blended_path.exists():
        blended = pd.read_excel(blended_path)
    else:
        blended = pd.DataFrame()

    if weights_path.exists():
        weights = pd.read_csv(weights_path)
    else:
        weights = pd.DataFrame(columns=["pollster", "weight"])

    # 1) scrape
    new_points = scrape_latest_public_points()
    if len(new_points):
        # TODO merge into your raw store, rebuild blended, etc.
        pass

    # 2) compare errors vs last forecast (if exists)
    # TODO

    # 3) update weights
    # errors_df = ...
    # weights = update_weights(weights, errors_df)

    weights.to_csv(weights_path, index=False)
    print("Done.")

if __name__ == "__main__":
    main()
