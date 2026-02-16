from __future__ import annotations

import argparse
import re
from pathlib import Path

import numpy as np
import pandas as pd


RAW_COLUMNS = [
    "poll_end_date",
    "publisher",
    "client",
    "method",
    "sample_n",
    "approve",
    "disapprove",
    "dk",
    "source_url",
    "notes",
]


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", str(s or "")).strip().lower()


def _looks_like_header_row(row: pd.Series) -> bool:
    vals = [_norm(v) for v in row.tolist()]
    return any("등록번호" in v for v in vals) and any("조사기관" in v for v in vals)


def _parse_end_date(text: str) -> pd.Timestamp:
    s = str(text or "")
    # Matches: 26.02.09 / 2026.02.09 / 2026-02-09
    toks = re.findall(r"(\d{2,4})[.\-/](\d{1,2})[.\-/](\d{1,2})", s)
    dates: list[pd.Timestamp] = []
    for yy, mm, dd in toks:
        y = int(yy)
        if y < 100:
            y += 2000
        dt = pd.to_datetime(f"{y:04d}-{int(mm):02d}-{int(dd):02d}", errors="coerce")
        if pd.notna(dt):
            dates.append(dt)
    if not dates:
        return pd.NaT
    return max(dates)


def _rename_with_second_header(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    top = df.iloc[0]
    rename_map = {}
    for c in df.columns:
        if str(c).startswith("Unnamed:"):
            v = str(top.get(c, "")).strip()
            if v and v.lower() != "nan":
                rename_map[c] = v
    if rename_map:
        df = df.rename(columns=rename_map)
        # The first row is usually label row for merged headers.
        if pd.isna(top.get("등록번호", np.nan)):
            df = df.iloc[1:].copy()
    return df


def _find_metric_columns(columns: list[str]) -> dict[str, str]:
    c_norm = {c: _norm(c) for c in columns}
    out: dict[str, str] = {}
    for c, n in c_norm.items():
        if "대통령" not in n and "국정" not in n and "직무" not in n and "수행" not in n:
            continue
        if "긍정" in n or "잘함" in n or "잘하고" in n:
            out["approve"] = c
        elif "부정" in n or "잘못" in n or "못함" in n or "못하고" in n:
            out["disapprove"] = c
        elif "유보" in n or "모름" in n or "무응답" in n:
            out["dk"] = c

    # Fallback on short labels if merged header already resolved to short names.
    if "approve" not in out:
        for c, n in c_norm.items():
            if n in {"긍정", "잘함"}:
                out["approve"] = c
                break
    if "disapprove" not in out:
        for c, n in c_norm.items():
            if n in {"부정", "잘못함"}:
                out["disapprove"] = c
                break
    if "dk" not in out:
        for c, n in c_norm.items():
            if n in {"유보", "모름", "무응답"}:
                out["dk"] = c
                break
    return out


def _sheet_has_president_context(df: pd.DataFrame, sheet_name: str) -> bool:
    name_n = _norm(sheet_name)
    if any(k in name_n for k in ["대통령", "국정", "직무", "수행평가"]):
        return True
    col_text = " ".join([_norm(c) for c in df.columns])
    return any(k in col_text for k in ["대통령", "국정", "직무", "수행", "평가"])


def extract_president_rows_from_xlsx(xlsx_path: Path) -> pd.DataFrame:
    rows: list[dict] = []
    if not xlsx_path.exists():
        return pd.DataFrame(columns=RAW_COLUMNS)

    xl = pd.ExcelFile(xlsx_path)
    for sheet in xl.sheet_names:
        raw = pd.read_excel(xlsx_path, sheet_name=sheet, header=None)
        if raw.empty:
            continue

        header_idx = None
        max_scan = min(len(raw), 8)
        for i in range(max_scan):
            if _looks_like_header_row(raw.iloc[i]):
                header_idx = i
                break
        if header_idx is None:
            continue

        df = pd.read_excel(xlsx_path, sheet_name=sheet, header=header_idx)
        df = _rename_with_second_header(df)
        if not _sheet_has_president_context(df, sheet):
            continue

        metric_cols = _find_metric_columns(list(df.columns))
        if "approve" not in metric_cols or "disapprove" not in metric_cols:
            continue

        for ridx, r in df.iterrows():
            publisher = str(r.get("조사기관", "")).strip()
            if not publisher or publisher.lower() == "nan":
                continue
            poll_end_date = _parse_end_date(r.get("조사일자", ""))
            if pd.isna(poll_end_date):
                continue

            approve = pd.to_numeric(r.get(metric_cols["approve"]), errors="coerce")
            disapprove = pd.to_numeric(r.get(metric_cols["disapprove"]), errors="coerce")
            dk = (
                pd.to_numeric(r.get(metric_cols["dk"]), errors="coerce")
                if "dk" in metric_cols
                else np.nan
            )
            if pd.isna(approve) or pd.isna(disapprove):
                continue

            rows.append(
                {
                    "poll_end_date": poll_end_date,
                    "publisher": publisher,
                    "client": str(r.get("의뢰자", "")).strip(),
                    "method": str(r.get("조사방법", "")).strip(),
                    "sample_n": pd.to_numeric(r.get("표본수(명)"), errors="coerce"),
                    "approve": float(approve),
                    "disapprove": float(disapprove),
                    "dk": float(dk) if pd.notna(dk) else np.nan,
                    "source_url": f"nesdc_xlsx://{xlsx_path.name}",
                    "notes": f"sheet={sheet};row={int(ridx) + int(header_idx) + 2}",
                }
            )

    if not rows:
        return pd.DataFrame(columns=RAW_COLUMNS)
    out = pd.DataFrame(rows)
    return out[RAW_COLUMNS]


def load_existing_raw(raw_csv: Path) -> pd.DataFrame:
    if not raw_csv.exists():
        return pd.DataFrame(columns=RAW_COLUMNS)
    try:
        df = pd.read_csv(raw_csv)
    except Exception:
        return pd.DataFrame(columns=RAW_COLUMNS)
    for c in RAW_COLUMNS:
        if c not in df.columns:
            df[c] = np.nan
    df["poll_end_date"] = pd.to_datetime(df["poll_end_date"], errors="coerce")
    for c in ["sample_n", "approve", "disapprove", "dk"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df[RAW_COLUMNS]


def dedupe_raw(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    if df.empty:
        return df, 0
    d0 = len(df)
    work = df.copy()
    work["publisher"] = work["publisher"].astype(str).str.strip()
    work["poll_end_date"] = pd.to_datetime(work["poll_end_date"], errors="coerce")
    work["approve"] = pd.to_numeric(work["approve"], errors="coerce")
    work["disapprove"] = pd.to_numeric(work["disapprove"], errors="coerce")
    work = work.dropna(subset=["poll_end_date", "publisher", "approve", "disapprove"])
    work = work.drop_duplicates(
        subset=["publisher", "poll_end_date", "approve", "disapprove"], keep="last"
    )
    return work, d0 - len(work)


def build_weekly(raw_df: pd.DataFrame) -> pd.DataFrame:
    if raw_df.empty:
        return pd.DataFrame(
            columns=["week_monday", "approve", "disapprove", "dk", "n_obs", "total_sample_n"]
        )
    df = raw_df.copy()
    df["poll_end_date"] = pd.to_datetime(df["poll_end_date"], errors="coerce")
    for c in ["approve", "disapprove", "dk", "sample_n"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["poll_end_date", "approve", "disapprove"]).copy()
    df["week_monday"] = df["poll_end_date"] - pd.to_timedelta(df["poll_end_date"].dt.weekday, unit="D")
    df["w"] = df["sample_n"].fillna(0.0)
    df["w"] = np.where(df["w"] > 0, df["w"], 1.0)

    def wavg(g: pd.DataFrame, col: str) -> float:
        x = pd.to_numeric(g[col], errors="coerce")
        m = x.notna()
        if not m.any():
            return np.nan
        ww = g.loc[m, "w"].astype(float)
        return float(np.average(x[m].astype(float), weights=ww))

    agg_rows = []
    for dt, g in df.groupby("week_monday"):
        agg_rows.append(
            {
                "week_monday": pd.to_datetime(dt),
                "approve": wavg(g, "approve"),
                "disapprove": wavg(g, "disapprove"),
                "dk": wavg(g, "dk"),
                "n_obs": int(len(g)),
                "total_sample_n": float(pd.to_numeric(g["sample_n"], errors="coerce").fillna(0).sum()),
            }
        )
    out = pd.DataFrame(agg_rows).sort_values("week_monday").reset_index(drop=True)
    return out


def quality_report(raw_input_count: int, merged_raw: pd.DataFrame, dup_dropped: int) -> pd.DataFrame:
    n = len(merged_raw)
    miss_approve = float(merged_raw["approve"].isna().mean()) if n else np.nan
    miss_disapprove = float(merged_raw["disapprove"].isna().mean()) if n else np.nan
    miss_dk = float(merged_raw["dk"].isna().mean()) if n else np.nan
    return pd.DataFrame(
        [
            {"metric": "raw_input_rows", "value": float(raw_input_count)},
            {"metric": "raw_rows_after_merge_dedupe", "value": float(n)},
            {"metric": "duplicates_dropped", "value": float(dup_dropped)},
            {"metric": "missing_rate_approve", "value": miss_approve},
            {"metric": "missing_rate_disapprove", "value": miss_disapprove},
            {"metric": "missing_rate_dk", "value": miss_dk},
        ]
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Build president approval raw+weekly datasets from NESDC xlsx.")
    ap.add_argument(
        "--input-xlsx",
        default="data/전국단위+선거여론조사결과의+주요+데이터(2023.10.30.~).xlsx",
    )
    ap.add_argument("--raw-csv", default="data/president_approval.csv")
    ap.add_argument("--out-weekly", default="outputs/president_approval_weekly.csv")
    ap.add_argument("--out-quality", default="outputs/president_approval_quality_report.csv")
    args = ap.parse_args()

    base = Path(".")
    input_xlsx = base / args.input_xlsx
    raw_csv = base / args.raw_csv
    out_weekly = base / args.out_weekly
    out_quality = base / args.out_quality

    extracted = extract_president_rows_from_xlsx(input_xlsx)
    existing = load_existing_raw(raw_csv)
    merged = pd.concat([existing, extracted], ignore_index=True)
    merged, dup_dropped = dedupe_raw(merged)
    weekly = build_weekly(merged)
    q = quality_report(len(extracted), merged, dup_dropped)

    raw_csv.parent.mkdir(parents=True, exist_ok=True)
    out_weekly.parent.mkdir(parents=True, exist_ok=True)
    out_quality.parent.mkdir(parents=True, exist_ok=True)

    merged.to_csv(raw_csv, index=False)
    weekly.to_csv(out_weekly, index=False)
    q.to_csv(out_quality, index=False)

    print(f"Input xlsx: {input_xlsx}")
    print(f"Extracted rows: {len(extracted)}")
    print(f"Raw rows (deduped): {len(merged)}")
    print(f"Weekly rows: {len(weekly)}")
    print(f"Wrote: {raw_csv}")
    print(f"Wrote: {out_weekly}")
    print(f"Wrote: {out_quality}")


if __name__ == "__main__":
    main()
