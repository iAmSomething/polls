from __future__ import annotations

from pathlib import Path
from typing import Tuple

import pandas as pd

REQUIRED_COLUMNS = [
    "issue_date",
    "issue_type",
    "intensity",
    "direction",
    "persistence",
    "target_party",
    "note",
]


def load_issue_events(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=REQUIRED_COLUMNS)

    df = pd.read_csv(path)
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required issue columns: {missing}")

    df = df.copy()
    df["issue_date"] = pd.to_datetime(df["issue_date"], errors="coerce")
    df["intensity"] = pd.to_numeric(df["intensity"], errors="coerce").fillna(0.0).clip(0, 3)
    return df.dropna(subset=["issue_date"])


def load_issue_coefficients(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=["issue_type", "target_party", "impact_coeff"])

    c = pd.read_csv(path)
    required = {"issue_type", "target_party", "impact_coeff"}
    if not required.issubset(c.columns):
        raise ValueError(f"Coefficient file must include: {sorted(required)}")
    c = c.copy()
    c["impact_coeff"] = pd.to_numeric(c["impact_coeff"], errors="coerce").fillna(0.0)
    return c


def compute_weekly_issue_impact(
    issues_df: pd.DataFrame, coeff_df: pd.DataFrame, week_start: pd.Timestamp, week_end: pd.Timestamp
) -> pd.DataFrame:
    if issues_df.empty or coeff_df.empty:
        return pd.DataFrame(columns=["target_party", "issue_impact"])

    w = issues_df[(issues_df["issue_date"] >= week_start) & (issues_df["issue_date"] <= week_end)].copy()
    if w.empty:
        return pd.DataFrame(columns=["target_party", "issue_impact"])

    merged = w.merge(coeff_df, on=["issue_type", "target_party"], how="left")
    merged["impact_coeff"] = merged["impact_coeff"].fillna(0.0)
    merged["issue_impact"] = merged["intensity"] * merged["impact_coeff"]
    out = merged.groupby("target_party", as_index=False)["issue_impact"].sum()
    return out


def demo_week_window(today: pd.Timestamp | None = None) -> Tuple[pd.Timestamp, pd.Timestamp]:
    t = pd.Timestamp.today().normalize() if today is None else pd.Timestamp(today).normalize()
    # Monday-start week window
    week_start = t - pd.Timedelta(days=t.weekday())
    week_end = week_start + pd.Timedelta(days=6)
    return week_start, week_end


def main():
    base = Path(".")
    issues = load_issue_events(base / "data/issues_input.csv")
    coeff = load_issue_coefficients(base / "config/issue_coefficients.csv")
    ws, we = demo_week_window()
    impact = compute_weekly_issue_impact(issues, coeff, ws, we)

    print(f"Issues loaded: {len(issues)}")
    print(f"Coeff rows: {len(coeff)}")
    print(f"Week window: {ws.date()} ~ {we.date()}")
    if impact.empty:
        print("No weekly issue impact.")
    else:
        print(impact.to_string(index=False))


if __name__ == "__main__":
    main()
