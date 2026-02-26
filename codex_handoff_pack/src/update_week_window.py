from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import requests
from bs4 import BeautifulSoup

try:
    from pipeline_core.constants import POLLSTERS, SHEETS
    from pipeline_core.sheet_loading import load_sheet
except Exception:
    # Backward compatibility for repos that still use monolithic pipeline module.
    from pipeline import POLLSTERS, SHEETS, load_sheet

WEEK_START = pd.Timestamp("2026-02-09")
WEEK_END = pd.Timestamp("2026-02-15")
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
)
NATIONAL_PARTY_POLL_KEYWORDS = [
    "정당 지지율",
    "정당지지율",
    "정당 지지도",
    "정당지지도",
    "정당별 지지율",
]
LOCAL_ELECTION_KEYWORDS = [
    "지방선거",
    "광역단체장",
    "기초단체장",
    "교육감",
    "후보 적합도",
    "당선 가능성",
    "가상 대결",
    "서울시장",
    "부산시장",
    "인천시장",
    "대전시장",
    "울산시장",
    "광주시장",
    "세종시장",
    "도지사",
    "구청장",
    "군수",
]
OBSERVED_WEIGHT_BOOST_SINGLE = 1.35
OBSERVED_WEIGHT_BOOST_MULTI = 1.80

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


def load_observed_points_jsonl(path: Path, week_start: pd.Timestamp, week_end: pd.Timestamp) -> List[dict]:
    if not path.exists():
        return []

    out: List[dict] = []
    context_cache: dict[str, dict] = {}

    def infer_context_from_url(url: str) -> dict:
        key = str(url or "").strip()
        if not key:
            return {"is_national_party_poll": False, "has_local_election_context": False}
        if key in context_cache:
            return context_cache[key]
        try:
            resp = requests.get(key, timeout=8, headers={"User-Agent": USER_AGENT}, allow_redirects=True)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            for tag in soup(["script", "style", "noscript"]):
                tag.decompose()
            text = " ".join(soup.stripped_strings)
        except Exception:
            context_cache[key] = {"is_national_party_poll": False, "has_local_election_context": False}
            return context_cache[key]
        text = " ".join(text.split())
        has_national = any(k in text for k in NATIONAL_PARTY_POLL_KEYWORDS)
        has_local = any(k in text for k in LOCAL_ELECTION_KEYWORDS)
        context_cache[key] = {
            "is_national_party_poll": has_national,
            "has_local_election_context": has_local,
        }
        return context_cache[key]
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue

        pollster = str(rec.get("pollster", "")).strip()
        date_end = pd.to_datetime(rec.get("date_end"), errors="coerce")
        values = rec.get("values", {}) or {}
        source_url = str(rec.get("source_url", "")).strip()
        context = rec.get("context") or {}
        if not isinstance(context, dict):
            context = {}
        if "is_national_party_poll" not in context or "has_local_election_context" not in context:
            inferred = infer_context_from_url(source_url)
            context = {
                "is_national_party_poll": bool(context.get("is_national_party_poll", inferred["is_national_party_poll"])),
                "has_local_election_context": bool(
                    context.get("has_local_election_context", inferred["has_local_election_context"])
                ),
            }

        if pollster not in POLLSTERS or pd.isna(date_end):
            continue
        if not (week_start <= date_end <= week_end):
            continue
        if not isinstance(values, dict) or not values:
            continue

        norm_vals = {}
        for k, v in values.items():
            try:
                norm_vals[str(k)] = float(v)
            except Exception:
                continue

        if not norm_vals:
            continue

        dm = norm_vals.get("더불어민주당")
        ppp = norm_vals.get("국민의힘")
        if dm is not None and ppp is not None:
            if dm < 5.0 or ppp < 5.0:
                context["is_national_party_poll"] = False

        out.append(
            {
                "pollster": pollster,
                "date_end": pd.Timestamp(date_end),
                "source_url": source_url,
                "values": norm_vals,
                "is_national_party_poll": bool(context.get("is_national_party_poll", True)),
                "has_local_election_context": bool(context.get("has_local_election_context", False)),
            }
        )
    return out


@dataclass
class UpdateArtifacts:
    blended: pd.DataFrame
    points_df: pd.DataFrame
    watchlist_df: pd.DataFrame
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
    observed_points: List[dict],
) -> pd.DataFrame:
    rows = []
    observed_map = {d["pollster"]: d for d in observed_points if WEEK_START <= d["date_end"] <= WEEK_END}

    for pollster in POLLSTERS:
        if pollster in observed_map:
            src = observed_map[pollster]
            if not bool(src.get("has_local_election_context", False)):
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
                    "is_national_party_poll": bool(src.get("is_national_party_poll", True)),
                    "has_local_election_context": bool(src.get("has_local_election_context", False)),
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
            "is_national_party_poll": False,
            "has_local_election_context": False,
        }
        for p in party_cols:
            row[p] = float(est[p])
        rows.append(row)

    return pd.DataFrame(rows)


def blend_from_points(points_df: pd.DataFrame, weights_df: pd.DataFrame, party_cols: List[str]) -> pd.Series:
    w_map = dict(zip(weights_df["조사기관"], weights_df["weight"]))
    observed_count = int((points_df["source_type"] == "observed_web").sum())
    observed_boost = OBSERVED_WEIGHT_BOOST_MULTI if observed_count >= 2 else OBSERVED_WEIGHT_BOOST_SINGLE
    row = {"date_end": WEEK_END, "n_polls": len(points_df)}
    for p in party_cols:
        vals = pd.to_numeric(points_df[p], errors="coerce")
        ws = np.array([w_map.get(a, 0.0) for a in points_df["pollster"]], dtype=float)
        src = points_df["source_type"].astype(str).to_numpy()
        ws = np.where(src == "observed_web", ws * observed_boost, ws)
        m = np.isfinite(vals.to_numpy(dtype=float)) & (ws > 0)
        if m.sum() == 0:
            row[p] = np.nan
        else:
            v = vals.to_numpy(dtype=float)[m]
            w = ws[m]
            row[p] = float(np.sum(w * v) / np.sum(w))
    return pd.Series(row)


def _safe_zscore(values: pd.Series) -> pd.Series:
    s = pd.to_numeric(values, errors="coerce")
    mu = float(s.mean()) if len(s) else 0.0
    sigma = float(s.std(ddof=0)) if len(s) else 0.0
    if not np.isfinite(sigma) or sigma <= 1e-9:
        return pd.Series(0.0, index=s.index)
    return (s - mu) / sigma


def build_pollster_watchlist(
    points_df: pd.DataFrame,
    blend_row: pd.Series,
    party_cols: List[str],
    major_parties: Tuple[str, str] = ("더불어민주당", "국민의힘"),
    z_threshold: float = 1.5,
    abs_threshold: float = 6.0,
) -> pd.DataFrame:
    rows = []
    for _, r in points_df.iterrows():
        deltas = []
        major_deltas = []
        for p in party_cols:
            if p not in r.index or p not in blend_row.index:
                continue
            pv = pd.to_numeric(pd.Series([r[p]]), errors="coerce").iloc[0]
            bv = pd.to_numeric(pd.Series([blend_row[p]]), errors="coerce").iloc[0]
            if not (np.isfinite(pv) and np.isfinite(bv)):
                continue
            d = float(pv - bv)
            deltas.append(d)
            if p in major_parties:
                major_deltas.append(d)
        if not deltas:
            continue
        if major_deltas:
            delta_major = float(np.mean(np.abs(major_deltas)))
        else:
            delta_major = float(np.mean(np.abs(deltas)))
        row = {
            "pollster": r["pollster"],
            "date_end": pd.to_datetime(r["date_end"]).date().isoformat(),
            "source_type": r["source_type"],
            "delta_major_abs": delta_major,
            "max_abs_delta": float(np.max(np.abs(deltas))),
        }
        rows.append(row)

    out = pd.DataFrame(rows)
    if out.empty:
        return pd.DataFrame(
            columns=["pollster", "date_end", "source_type", "delta_major_abs", "z_score", "max_abs_delta", "alert"]
        )
    out["z_score"] = _safe_zscore(out["delta_major_abs"])
    # Alert only on upper-tail anomalies (large divergence), not low-tail z-scores.
    out["alert"] = (out["z_score"] >= z_threshold) | (out["max_abs_delta"] >= abs_threshold)
    out = out.sort_values(["alert", "delta_major_abs", "max_abs_delta"], ascending=[False, False, False]).reset_index(drop=True)
    return out


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


def build_log(points_df: pd.DataFrame, blend_row: pd.Series, watchlist_df: pd.DataFrame) -> str:
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
    if not watchlist_df.empty:
        alert_count = int(watchlist_df["alert"].fillna(False).sum())
        if alert_count > 0:
            top = watchlist_df[watchlist_df["alert"]].iloc[0]
            lines.append(
                "- Pollster anomaly alerts: "
                f"{alert_count} (top: {top['pollster']}, delta_major_abs={float(top['delta_major_abs']):.2f}, z={float(top['z_score']):.2f})"
            )

    lines.append("")
    lines.append("## Updated Blended Point")
    lines.append(f"- date_end: {WEEK_END.date()}")
    for k, v in blend_row.items():
        if k in {"date_end", "n_polls"}:
            continue
        lines.append(f"- {k}: {float(v):.2f}")

    return "\n".join(lines) + "\n"


def run_update(base_dir: Path, observed_jsonl: Path) -> UpdateArtifacts:
    outputs = base_dir / "outputs"
    data_dir = base_dir / "data"

    blended = pd.read_excel(outputs / "weighted_time_series.xlsx", sheet_name="weighted_time_series")
    weights_df = pd.read_csv(outputs / "weights.csv")
    party_cols = party_columns_from_blended(blended)

    raw_df = load_historical_raw(data_dir)
    baseline = baseline_projection(blended, party_cols)
    bias_df = estimate_pollster_bias(raw_df, blended, party_cols)
    observed_points = [*OBSERVED_POINTS, *load_observed_points_jsonl(observed_jsonl, WEEK_START, WEEK_END)]
    points_df = build_week_points(weights_df, baseline, bias_df, party_cols, observed_points)
    blend_row = blend_from_points(points_df, weights_df, party_cols)
    blended_updated = apply_update(outputs, blend_row)
    watchlist_df = build_pollster_watchlist(points_df, blend_row, party_cols)

    points_out = outputs / f"weekly_public_points_{WEEK_START.date()}_{WEEK_END.date()}.csv"
    points_df.to_csv(points_out, index=False)
    watchlist_csv = outputs / "pollster_watchlist.csv"
    watchlist_df.to_csv(watchlist_csv, index=False)
    watchlist_alerts = watchlist_df[watchlist_df["alert"]] if "alert" in watchlist_df.columns else pd.DataFrame()
    lines = [
        f"# Pollster Watchlist ({WEEK_START.date()} ~ {WEEK_END.date()})",
        "",
        f"- Pollsters analyzed: {len(watchlist_df)}",
        f"- Alerts: {len(watchlist_alerts)}",
    ]
    if len(watchlist_alerts) > 0:
        lines.append("")
        lines.append("## Alerted Pollsters")
        for _, r in watchlist_alerts.iterrows():
            lines.append(
                f"- {r['pollster']}: delta_major_abs={float(r['delta_major_abs']):.2f}, "
                f"max_abs_delta={float(r['max_abs_delta']):.2f}, z={float(r['z_score']):.2f}, "
                f"source_type={r['source_type']}"
            )
    else:
        lines.append("- No pollster alerts triggered for this week.")
    (outputs / "pollster_watchlist.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    log_text = build_log(points_df, blend_row, watchlist_df)
    log_out = outputs / f"update_log_{WEEK_START.date()}_{WEEK_END.date()}.md"
    log_out.write_text(log_text, encoding="utf-8")

    return UpdateArtifacts(blended=blended_updated, points_df=points_df, watchlist_df=watchlist_df, log_text=log_text)


def main():
    global WEEK_START, WEEK_END

    ap = argparse.ArgumentParser(description="Update blended weekly point from observed web points + fallback estimates.")
    ap.add_argument("--week-start", default=str(WEEK_START.date()), help="Week start date (YYYY-MM-DD)")
    ap.add_argument("--week-end", default=str(WEEK_END.date()), help="Week end date (YYYY-MM-DD)")
    ap.add_argument("--observed-jsonl", default="outputs/observed_web_points.jsonl")
    args = ap.parse_args()

    WEEK_START = pd.Timestamp(args.week_start)
    WEEK_END = pd.Timestamp(args.week_end)

    base = Path(__file__).resolve().parents[1]
    observed_jsonl = (base / args.observed_jsonl).resolve() if not Path(args.observed_jsonl).is_absolute() else Path(args.observed_jsonl)
    res = run_update(base, observed_jsonl=observed_jsonl)
    print(f"Updated weekly points: {len(res.points_df)}")
    print(res.points_df[["pollster", "source_type", "date_end"]].to_string(index=False))


if __name__ == "__main__":
    main()
