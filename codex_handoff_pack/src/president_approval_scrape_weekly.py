#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import html
import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple

import feedparser
import pandas as pd
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

POLLSTERS_HINT = [
    "리얼미터",
    "한국갤럽",
    "NBS",
    "엠브레인퍼블릭",
    "코리아리서치",
    "한국리서치",
    "케이스탯",
]

RE_APPROVE = [
    re.compile(r"(?:잘(?:하고|한다)|긍정(?:적)?\s*평가)[^0-9]{0,20}(\d{1,2}(?:\.\d+)?)\s*%"),
    re.compile(r"(?:국정\s*수행|직무\s*수행)[^0-9]{0,40}(?:잘(?:하고|한다)|긍정)[^0-9]{0,20}(\d{1,2}(?:\.\d+)?)\s*%"),
    re.compile(r"긍정[^0-9]{0,8}(\d{1,2}(?:\.\d+)?)\s*%"),
    re.compile(r"국정(?:수행)?지지율[^0-9]{0,8}(\d{1,2}(?:\.\d+)?)\s*%"),
    re.compile(r"지지율[^0-9]{0,8}(\d{1,2}(?:\.\d+)?)\s*%"),
]
RE_DISAPPROVE = [
    re.compile(r"(?:잘못(?:하고|한다)|부정(?:적)?\s*평가)[^0-9]{0,20}(\d{1,2}(?:\.\d+)?)\s*%"),
    re.compile(r"(?:국정\s*수행|직무\s*수행)[^0-9]{0,40}(?:잘못|부정)[^0-9]{0,20}(\d{1,2}(?:\.\d+)?)\s*%"),
    re.compile(r"부정[^0-9]{0,8}(\d{1,2}(?:\.\d+)?)\s*%"),
    re.compile(r"잘못(?:하고|한다|할것)[^0-9]{0,8}(\d{1,2}(?:\.\d+)?)\s*%"),
]

RE_DATE = re.compile(r"(\d{4})[.\-/년]\s*(\d{1,2})[.\-/월]\s*(\d{1,2})")


def daterange_weeks(start: date, end: date) -> list[tuple[date, date]]:
    out = []
    cur = start
    while cur <= end:
        w_end = min(cur + timedelta(days=6), end)
        out.append((cur, w_end))
        cur = w_end + timedelta(days=1)
    return out


def google_news_rss(query: str, from_d: date, to_d: date) -> str:
    q = f'{query} after:{from_d.isoformat()} before:{(to_d + timedelta(days=1)).isoformat()}'
    return f"https://news.google.com/rss/search?q={requests.utils.quote(q)}&hl=ko&gl=KR&ceid=KR:ko"


def fetch_rss_entries(url: str, timeout: int = 6) -> list[dict]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        if r.status_code != 200 or not r.text:
            return []
        feed = feedparser.parse(r.text)
    except Exception:
        return []
    out = []
    for e in getattr(feed, "entries", []):
        out.append(
            {
                "title": getattr(e, "title", ""),
                "url": getattr(e, "link", ""),
                "published": getattr(e, "published", ""),
                "summary": getattr(e, "summary", ""),
                "source": getattr(getattr(e, "source", None), "title", ""),
            }
        )
    return out


def fetch_article_text(url: str, timeout: int = 5) -> tuple[str, str]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        if r.status_code != 200 or not r.text:
            return "", ""
        final_url = str(r.url)
        soup = BeautifulSoup(r.text, "html.parser")
        art = soup.find("article")
        if art:
            return " ".join(art.get_text(" ").split()), final_url
        ps = soup.find_all("p")
        if ps:
            txt = " ".join(p.get_text(" ").strip() for p in ps[:120])
            return " ".join(txt.split()), final_url
        return " ".join(soup.get_text(" ").split()), final_url
    except Exception:
        return "", ""


def extract_numbers(text: str) -> Tuple[Optional[float], Optional[float]]:
    approve = None
    dis = None
    for pat in RE_APPROVE:
        m = pat.search(text)
        if m:
            approve = float(m.group(1))
            break
    for pat in RE_DISAPPROVE:
        m = pat.search(text)
        if m:
            dis = float(m.group(1))
            break
    return approve, dis


def clean_snippet(text: str) -> str:
    s = html.unescape(str(text or ""))
    s = re.sub(r"(?is)<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def infer_pollster(text: str) -> Optional[str]:
    for h in POLLSTERS_HINT:
        if h in text:
            return h
    return None


def infer_date(text: str, fallback: date) -> date:
    m = RE_DATE.search(text)
    if not m:
        return fallback
    y, mo, d = map(int, m.groups())
    try:
        return date(y, mo, d)
    except Exception:
        return fallback


def collect_week(from_d: date, to_d: date, max_items: int = 15, sleep_sec: float = 0.05) -> dict:
    queries = [
        "대통령 지지율 리얼미터",
        "대통령 지지율 한국갤럽",
        "대통령 국정수행 긍정 부정",
    ]
    candidates = []
    for q in queries:
        rss = google_news_rss(q, from_d, to_d)
        entries = fetch_rss_entries(rss, timeout=6)
        for e in entries[:max_items]:
            candidates.append(e)
        time.sleep(sleep_sec)

    seen = set()
    uniq = []
    for c in candidates:
        u = str(c.get("url", "")).strip()
        if not u or u in seen:
            continue
        seen.add(u)
        uniq.append(c)

    best = {
        "week_start": from_d.isoformat(),
        "week_end": to_d.isoformat(),
        "approve": None,
        "disapprove": None,
        "dk": None,
        "pollster": None,
        "publisher": None,
        "poll_end_date": to_d.isoformat(),
        "source_url": None,
        "source_title": None,
        "notes": "",
        "candidates": uniq[:20],
    }

    for c in uniq[:40]:
        snippet = clean_snippet(f"{c.get('title','')} {c.get('summary','')}")
        approve, dis = extract_numbers(snippet)
        if approve is not None and dis is not None:
            pol = infer_pollster(snippet)
            best.update(
                {
                    "approve": approve,
                    "disapprove": dis,
                    "dk": max(0.0, round(100.0 - approve - dis, 1)),
                    "pollster": pol,
                    "publisher": pol or str(c.get("source", "")).strip() or None,
                    "poll_end_date": to_d.isoformat(),
                    "source_url": str(c.get("url", "")),
                    "source_title": str(c.get("title", "")),
                    "notes": "auto_from_rss_snippet",
                }
            )
            return best

    best["notes"] = "auto-extract failed; review candidates"
    return best


def build_outputs(rows: list[dict], out_dir: Path, data_dir: Path) -> None:
    df = pd.DataFrame(rows)
    detail_cols = [
        "week_start",
        "week_end",
        "approve",
        "disapprove",
        "dk",
        "pollster",
        "publisher",
        "poll_end_date",
        "source_title",
        "source_url",
        "notes",
    ]
    for c in detail_cols:
        if c not in df.columns:
            df[c] = None
    detail = df[detail_cols].copy()

    # Weekly file expected by existing pipeline
    weekly = detail.rename(columns={"week_start": "week_monday"})[
        ["week_monday", "approve", "disapprove", "dk"]
    ].copy()
    weekly["week_monday"] = pd.to_datetime(weekly["week_monday"], errors="coerce")
    weekly["n_obs"] = weekly["approve"].notna().astype(int)
    weekly["total_sample_n"] = weekly["n_obs"] * 1000.0
    weekly = weekly.sort_values("week_monday").reset_index(drop=True)

    # Raw file expected by president_approval_pipeline-compatible schema
    raw = detail.copy()
    raw["poll_end_date"] = pd.to_datetime(raw["poll_end_date"], errors="coerce")
    raw["sample_n"] = 1000.0
    raw["client"] = ""
    raw["method"] = ""
    raw["notes"] = raw["notes"].fillna("") + ";from_weekly_scraper"
    raw["source_url"] = raw["source_url"].fillna("")
    raw = raw.rename(columns={"publisher": "publisher"})
    raw = raw[
        [
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
    ]
    raw = raw.dropna(subset=["approve", "disapprove"]).copy()
    raw["publisher"] = raw["publisher"].fillna("unknown")
    raw = raw.drop_duplicates(subset=["publisher", "poll_end_date", "approve", "disapprove"], keep="last")

    out_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    detail.to_csv(out_dir / "president_approval_weekly_detail.csv", index=False, encoding="utf-8-sig")
    detail.to_excel(out_dir / "president_approval_weekly_detail.xlsx", index=False)
    weekly.to_csv(out_dir / "president_approval_weekly.csv", index=False)
    weekly.to_excel(out_dir / "president_approval_weekly.xlsx", index=False)
    raw.to_csv(data_dir / "president_approval.csv", index=False)

    with (out_dir / "president_approval_candidates.json").open("w", encoding="utf-8") as f:
        json.dump(
            [
                {
                    "week_start": r.get("week_start"),
                    "week_end": r.get("week_end"),
                    "candidates": r.get("candidates", []),
                }
                for r in rows
            ],
            f,
            ensure_ascii=False,
            indent=2,
        )
    print("Wrote:", out_dir / "president_approval_weekly.csv")
    print("Wrote:", out_dir / "president_approval_weekly.xlsx")
    print("Wrote:", out_dir / "president_approval_weekly_detail.csv")
    print("Wrote:", out_dir / "president_approval_candidates.json")
    print("Wrote:", data_dir / "president_approval.csv")
    print("filled_weeks=", int(weekly["approve"].notna().sum()), "total_weeks=", int(len(weekly)))


def main() -> None:
    start = date(2025, 6, 4)
    end = date(2026, 2, 16)
    weeks = daterange_weeks(start, end)
    rows = []
    for ws, we in weeks:
        print(f"[{ws}~{we}] collect", flush=True)
        rows.append(collect_week(ws, we))
        time.sleep(0.15)

    base = Path(".")
    build_outputs(rows, out_dir=base / "outputs", data_dir=base / "data")


if __name__ == "__main__":
    main()
