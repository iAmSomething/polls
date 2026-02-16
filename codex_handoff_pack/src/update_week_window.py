from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd

from pipeline import POLLSTERS, SHEETS, load_sheet

WEEK_START = pd.Timestamp("2026-02-09")
WEEK_END = pd.Timestamp("2026-02-15")

# Verified text-available public point within 2026-02-09~15.
# Source checked: Newsis article with full party breakdown text.
OBSERVED_POINTS = [
    {
        "pollster": "리얼미터",
        "date_end": pd.Timestamp("2026-02-13"),
        "source_url": "https://mobile.newsis.com/view/NISX20260216_0003342712",
        "values": {
            "더불어민주당": 44.8,
            "국민의힘": 36.1,
            "조국혁신당": 3.8,
            "개혁신당": 2.7,
            "진보당": 1.5,
            "기타정당": 2.0,
            "지지정당\n없음": 9.2,
        },
    }
]


@dataclass
class UpdateArtifacts:
    blended: pd.DataFrame
    points_df: pd.DataFrame
    log_text: str


def find_raw_input(data_dir: Path) -> Path:
    cands = sorted(data_dir.glob("*.xlsx"), key=lambda p: p.stat().st_mtime, reverse=True)
    for c in cands:
        try:
            x = pd.ExcelFile(c)
        except Exception:
            continue
        if all(s in x.sheet_names for s in SHEETS):
            return c
    raise FileNotFoundError("Raw polling workbook not found in data/")


def load_historical_raw(data_dir: Path) -> pd.DataFrame:
    raw_path = find_raw_input(data_dir)
    df = pd.concat([load_sheet(raw_path, s) for s in SHEETS], ignore_index=True)
    df = df[df["조사기관"].isin(POLLSTERS)].copy()
    return df


def party_columns_from_blended(blended: pd.DataFrame) -> List[str]:
    return [c for c in blended.columns if c not in {"date_end", "n_polls"}]


def baseline_projection(blended: pd.DataFrame, party_cols: List[str]) -> pd.Series:
    df = blended.copy()
    df["date_end"] = pd.to_datetime(df["date_end"])
    df = df.sort_values("date_end")

    last_date = df["date_end"].max()
    days_ahead = max(0, int((WEEK_END - last_date).days))

    out = {}
    for c in party_cols:
        s = pd.to_numeric(df[c], errors="coerce").dropna()
        if s.empty:
            out[c] = np.nan
            continue
        ew = s.ewm(halflife=5, adjust=False).mean().iloc[-1]
        if len(s) >= 5:
            y = s.iloc[-8:].to_numpy(dtype=float)
            x = np.arange(len(y), dtype=float)
            A = np.vstack([x, np.ones_like(x)]).T
            slope, intercept = np.linalg.lstsq(A, y, rcond=None)[0]
            trend = (0.5 * slope) * min(days_ahead, 7)
        else:
            trend = 0.0
        out[c] = float(ew + trend)

    base = pd.Series(out)
    return normalize_row(base)


def normalize_row(row: pd.Series) -> pd.Series:
    r = row.copy()
    r = pd.to_numeric(r, errors="coerce")
    r = r.fillna(0.0)
    r[r < 0] = 0.0
    s = float(r.sum())
    if s <= 0:
        return r
    return (r / s) * 100.0


def estimate_pollster_bias(raw_df: pd.DataFrame, blended: pd.DataFrame, party_cols: List[str]) -> pd.DataFrame:
    # Compute pollster minus blended residuals on overlapping dates (recent-weighted mean).
    r = raw_df.copy()
    r["date_end"] = pd.to_datetime(r["date_end"])
    r = r[(r["date_end"] >= pd.Timestamp("2025-07-01")) & (r["date_end"] <= WEEK_END)].copy()

    b = blended.copy()
    b["date_end"] = pd.to_datetime(b["date_end"])
    b = b[["date_end"] + party_cols].copy()

    merged = r.merge(b, on="date_end", suffixes=("", "__blend"), how="inner")
    rows = []
    for pollster, g in merged.groupby("조사기관"):
        row: Dict[str, float] = {"pollster": pollster}
        if len(g) == 0:
            for p in party_cols:
                row[p] = 0.0
            rows.append(row)
            continue

        age_days = (WEEK_END - g["date_end"]).dt.days.clip(lower=0)
        w = np.exp(-age_days / 45.0)
        w = np.asarray(w, dtype=float)
        for p in party_cols:
            if p not in g.columns or f"{p}__blend" not in g.columns:
                row[p] = 0.0
                continue
            a = pd.to_numeric(g[p], errors="coerce")
            bb = pd.to_numeric(g[f"{p}__blend"], errors="coerce")
            d = (a - bb).to_numpy(dtype=float)
            m = np.isfinite(d)
            if m.sum() == 0:
                row[p] = 0.0
            else:
                ww = w[m]
                dd = d[m]
                row[p] = float(np.sum(ww * dd) / np.sum(ww))
        rows.append(row)

    out = pd.DataFrame(rows)
    if out.empty:
        out = pd.DataFrame({"pollster": POLLSTERS})
    return out.set_index("pollster").reindex(POLLSTERS).fillna(0.0).reset_index()


def build_week_points(
    weights_df: pd.DataFrame,
    baseline: pd.Series,
    bias_df: pd.DataFrame,
    party_cols: List[str],
) -> pd.DataFrame:
    rows = []
    observed_map = {d["pollster"]: d for d in OBSERVED_POINTS if WEEK_START <= d["date_end"] <= WEEK_END}

    for pollster in POLLSTERS:
        if pollster in observed_map:
            src = observed_map[pollster]
            values = pd.Series({p: src["values"].get(p, np.nan) for p in party_cols})
            # Fill missing parties by baseline share to keep coherent total.
            if values.isna().any():
                miss = values.isna()
                known_sum = float(values[~miss].sum())
                remain = max(0.0, 100.0 - known_sum)
                base_sub = baseline[miss]
                if float(base_sub.sum()) > 0:
                    values.loc[miss] = (base_sub / float(base_sub.sum()) * remain).to_numpy()
                else:
                    values.loc[miss] = 0.0
            values = normalize_row(values)
            row = {
                "pollster": pollster,
                "date_end": src["date_end"],
                "source_type": "observed_web",
                "source_url": src["source_url"],
            }
            for p in party_cols:
                row[p] = float(values[p])
            rows.append(row)
            continue

        b = bias_df[bias_df["pollster"] == pollster]
        bias = pd.Series(0.0, index=party_cols)
        if not b.empty:
            for p in party_cols:
                if p in b.columns:
                    bias[p] = float(b.iloc[0][p])

        est = normalize_row(baseline + bias)
        row = {
            "pollster": pollster,
            "date_end": WEEK_END,
            "source_type": "estimated_bias_adjusted",
            "source_url": "",
        }
        for p in party_cols:
            row[p] = float(est[p])
        rows.append(row)

    return pd.DataFrame(rows)


def blend_from_points(points_df: pd.DataFrame, weights_df: pd.DataFrame, party_cols: List[str]) -> pd.Series:
    w_map = dict(zip(weights_df["조사기관"], weights_df["weight"]))
    row = {"date_end": WEEK_END, "n_polls": len(points_df)}
    for p in party_cols:
        vals = pd.to_numeric(points_df[p], errors="coerce")
        ws = np.array([w_map.get(a, 0.0) for a in points_df["pollster"]], dtype=float)
        m = np.isfinite(vals.to_numpy(dtype=float)) & (ws > 0)
        if m.sum() == 0:
            row[p] = np.nan
        else:
            v = vals.to_numpy(dtype=float)[m]
            w = ws[m]
            row[p] = float(np.sum(w * v) / np.sum(w))
    return pd.Series(row)


def apply_update(outputs_dir: Path, new_blend_row: pd.Series) -> pd.DataFrame:
    wt_path = outputs_dir / "weighted_time_series.xlsx"
    blended = pd.read_excel(wt_path, sheet_name="weighted_time_series")
    blended["date_end"] = pd.to_datetime(blended["date_end"])
    blended = blended[blended["date_end"] != WEEK_END].copy()
    blended = pd.concat([blended, pd.DataFrame([new_blend_row])], ignore_index=True)
    blended = blended.sort_values("date_end").reset_index(drop=True)

    # Preserve weights sheet if exists.
    try:
        weights_sheet = pd.read_excel(wt_path, sheet_name="weights")
    except Exception:
        weights_sheet = pd.DataFrame()

    with pd.ExcelWriter(wt_path, engine="openpyxl") as w:
        blended.to_excel(w, sheet_name="weighted_time_series", index=False)
        if not weights_sheet.empty:
            weights_sheet.to_excel(w, sheet_name="weights", index=False)
    return blended


def build_log(points_df: pd.DataFrame, blend_row: pd.Series) -> str:
    observed = points_df[points_df["source_type"] == "observed_web"].copy()
    estimated = points_df[points_df["source_type"] == "estimated_bias_adjusted"].copy()

    lines = []
    lines.append(f"# Weekly Update Log ({WEEK_START.date()} ~ {WEEK_END.date()})")
    lines.append("")
    lines.append("## Web Verification")
    lines.append(f"- Observed text-verified points: {len(observed)}")
    for _, r in observed.iterrows():
        lines.append(f"- {r['pollster']} ({pd.to_datetime(r['date_end']).date()}): {r['source_url']}")
    if len(observed) == 0:
        lines.append("- No text-verified full breakdown points found for selected pollsters in this week.")

    lines.append("")
    lines.append("## Estimation Fallback")
    lines.append("- Missing pollsters were estimated via baseline projection (EWMA + damped trend) + pollster-specific bias adjustment.")
    lines.append(f"- Estimated pollsters: {len(estimated)}")

    lines.append("")
    lines.append("## Updated Blended Point")
    lines.append(f"- date_end: {WEEK_END.date()}")
    for k, v in blend_row.items():
        if k in {"date_end", "n_polls"}:
            continue
        lines.append(f"- {k}: {float(v):.2f}")

    return "\n".join(lines) + "\n"


def run_update(base_dir: Path) -> UpdateArtifacts:
    outputs = base_dir / "outputs"
    data_dir = base_dir / "data"

    blended = pd.read_excel(outputs / "weighted_time_series.xlsx", sheet_name="weighted_time_series")
    weights_df = pd.read_csv(outputs / "weights.csv")
    party_cols = party_columns_from_blended(blended)

    raw_df = load_historical_raw(data_dir)
    baseline = baseline_projection(blended, party_cols)
    bias_df = estimate_pollster_bias(raw_df, blended, party_cols)

    points_df = build_week_points(weights_df, baseline, bias_df, party_cols)
    blend_row = blend_from_points(points_df, weights_df, party_cols)
    blended_updated = apply_update(outputs, blend_row)

    points_out = outputs / f"weekly_public_points_{WEEK_START.date()}_{WEEK_END.date()}.csv"
    points_df.to_csv(points_out, index=False)

    log_text = build_log(points_df, blend_row)
    log_out = outputs / f"update_log_{WEEK_START.date()}_{WEEK_END.date()}.md"
    log_out.write_text(log_text, encoding="utf-8")

    return UpdateArtifacts(blended=blended_updated, points_df=points_df, log_text=log_text)


def main():
    base = Path(__file__).resolve().parents[1]
    res = run_update(base)
    print(f"Updated weekly points: {len(res.points_df)}")
    print(res.points_df[["pollster", "source_type", "date_end"]].to_string(index=False))


if __name__ == "__main__":
    main()
