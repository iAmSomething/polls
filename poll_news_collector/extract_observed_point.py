#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path
from typing import Dict, Optional

import requests
from bs4 import BeautifulSoup

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"

PARTY_ALIASES = {
    "더불어민주당": ["더불어민주당", "민주당"],
    "국민의힘": ["국민의힘"],
    "조국혁신당": ["조국혁신당"],
    "개혁신당": ["개혁신당"],
    "진보당": ["진보당"],
    "지지정당\n없음": ["무당층", "지지정당 없음", "지지 정당 없음", "없음"],
}

POLLSTERS = [
    "리서치앤리서치",
    "엠브레인퍼블릭",
    "리서치뷰",
    "에이스리서치",
    "한국리서치",
    "조원씨앤아이",
    "알앤써치",
    "리얼미터",
    "코리아리서치인터내셔널",
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Extract poll point from article text")
    p.add_argument("--url", default=None, help="Article URL")
    p.add_argument("--input-file", default=None, help="Plain text or collected .txt file")
    p.add_argument("--date", default=None, help="Force date_end (YYYY-MM-DD)")
    p.add_argument("--pollster", default=None, help="Force pollster")
    p.add_argument("--out", default=None, help="Write JSON output path")
    return p.parse_args()


def fetch_text(url: str) -> str:
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = " ".join(soup.stripped_strings)
    return re.sub(r"\s+", " ", text)


def load_text(input_file: Optional[str], url: Optional[str]) -> str:
    if input_file:
        return Path(input_file).expanduser().read_text(encoding="utf-8")
    if url:
        return fetch_text(url)
    raise SystemExit("Either --url or --input-file is required")


def parse_date(text: str, forced: Optional[str]) -> Optional[str]:
    if forced:
        return forced

    m = re.search(r"(20\d{2})[.\-/년\s]+(\d{1,2})[.\-/월\s]+(\d{1,2})", text)
    if not m:
        return None
    y, mo, d = map(int, m.groups())
    return dt.date(y, mo, d).isoformat()


def detect_pollster(text: str, forced: Optional[str]) -> Optional[str]:
    if forced:
        return forced
    for name in POLLSTERS:
        if name in text:
            return name
    return None


def _is_delta_percent(text: str, span_start: int, span_end: int) -> bool:
    # Exclude delta notations like "3.8%포인트", "3.8%p", "3.8% P".
    after = text[span_end : span_end + 10]
    if re.match(r"\s*(포인트|p|P)", after):
        return True
    return False


def parse_percent_near_alias(text: str, alias: str) -> Optional[float]:
    alias_esc = re.escape(alias)
    candidates: list[tuple[int, float]] = []
    for alias_m in re.finditer(alias_esc, text):
        win_start = alias_m.end()
        win_end = min(len(text), win_start + 140)
        window = text[win_start:win_end]
        for pct_m in re.finditer(r"(\d{1,2}(?:\.\d+)?)\s*%", window):
            abs_num_start = win_start + pct_m.start(1)
            abs_pct_end = win_start + pct_m.end()
            if _is_delta_percent(text, abs_num_start, abs_pct_end):
                continue
            try:
                v = float(pct_m.group(1))
            except Exception:
                continue
            if 0.0 <= v <= 100.0:
                # Prefer nearest valid percent after alias mention.
                candidates.append((abs_num_start - alias_m.start(), v))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


def extract_values(text: str) -> Dict[str, float]:
    values: Dict[str, float] = {}
    for canonical, aliases in PARTY_ALIASES.items():
        found = None
        for alias in aliases:
            v = parse_percent_near_alias(text, alias)
            if v is not None:
                found = v
                break
        if found is not None:
            values[canonical] = found
    return values


def extract_president_approval(text: str) -> Dict[str, float]:
    out: Dict[str, float] = {}
    keyword_map = {
        "positive": ["국정수행 지지율", "국정 지지율", "대통령 지지율", "긍정 평가", "긍정"],
        "negative": ["부정 평가", "국정수행 부정", "국정 부정", "부정"],
    }
    for key, keywords in keyword_map.items():
        candidates: list[tuple[int, float]] = []
        for kw in keywords:
            for kw_m in re.finditer(re.escape(kw), text):
                win_start = kw_m.end()
                win_end = min(len(text), win_start + 120)
                window = text[win_start:win_end]
                for pct_m in re.finditer(r"(\d{1,2}(?:\.\d+)?)\s*%", window):
                    abs_num_start = win_start + pct_m.start(1)
                    abs_pct_end = win_start + pct_m.end()
                    if _is_delta_percent(text, abs_num_start, abs_pct_end):
                        continue
                    try:
                        v = float(pct_m.group(1))
                    except Exception:
                        continue
                    if 0.0 <= v <= 100.0:
                        candidates.append((abs_num_start - kw_m.start(), v))
                # Also support forms like "37.2%가 부정 평가".
                back_start = max(0, kw_m.start() - 80)
                back_window = text[back_start : kw_m.start()]
                back_matches = list(re.finditer(r"(\d{1,2}(?:\.\d+)?)\s*%", back_window))
                if back_matches:
                    pct_m = back_matches[-1]
                    abs_num_start = back_start + pct_m.start(1)
                    abs_pct_end = back_start + pct_m.end()
                    if not _is_delta_percent(text, abs_num_start, abs_pct_end):
                        try:
                            v = float(pct_m.group(1))
                        except Exception:
                            v = -1.0
                        if 0.0 <= v <= 100.0:
                            candidates.append((kw_m.start() - abs_num_start, v))
        if candidates:
            candidates.sort(key=lambda x: x[0])
            out[key] = candidates[0][1]
    return out


def extract_point_from_text(
    text: str,
    source_url: str = "",
    forced_date: Optional[str] = None,
    forced_pollster: Optional[str] = None,
) -> dict:
    return {
        "pollster": detect_pollster(text, forced_pollster),
        "date_end": parse_date(text, forced_date),
        "source_url": source_url,
        "values": extract_values(text),
        "president_approval": extract_president_approval(text),
    }


def main() -> None:
    args = parse_args()
    text = load_text(args.input_file, args.url)
    out = extract_point_from_text(
        text=text,
        source_url=args.url or "",
        forced_date=args.date,
        forced_pollster=args.pollster,
    )

    as_json = json.dumps(out, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).expanduser().write_text(as_json + "\n", encoding="utf-8")
        print(f"wrote: {args.out}")
    else:
        print(as_json)


if __name__ == "__main__":
    main()
