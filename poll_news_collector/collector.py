#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sqlite3
import time
import urllib.parse
from pathlib import Path
from typing import Iterable

import feedparser
import requests
from bs4 import BeautifulSoup

RSS_QUERIES = [
    "여론조사",
    "정당 지지율 여론조사",
    "리얼미터 여론조사",
    "한국리서치 여론조사",
]
POLLING_ORGS = {
    "리서치앤리서치": ["리서치앤리서치"],
    "엠브레인퍼블릭": ["엠브레인퍼블릭", "엠브레인"],
    "리서치뷰": ["리서치뷰"],
    "에이스리서치": ["에이스리서치"],
    "한국리서치": ["한국리서치"],
    "조원씨앤아이": ["조원씨앤아이", "조원C&I", "조원씨앤아이"],
    "알앤써치": ["알앤써치", "Rnsearch", "R&Search"],
    "리얼미터": ["리얼미터"],
    "코리아리서치인터내셔널": ["코리아리서치인터내셔널", "코리아리서치"],
}
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
NAVER_SEARCH_URL = "https://search.naver.com/search.naver"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect polling-related news articles")
    parser.add_argument("--base-dir", default=".", help="Base directory for DB and collected files")
    parser.add_argument("--window-minutes", type=int, default=60, help="Look-back window in minutes")
    parser.add_argument(
        "--rss-query",
        action="append",
        default=[],
        help="Additional Google News RSS query. Can be passed multiple times.",
    )
    parser.add_argument(
        "--recent-json-out",
        default=None,
        help="Optional JSON output path for stage1 recent articles (date/source/title/url)",
    )
    parser.add_argument("--recent-limit", type=int, default=12, help="Max recent articles to save in JSON")
    parser.add_argument(
        "--min-export",
        type=int,
        default=6,
        help="Minimum number of articles to export; backfill with older items if needed",
    )
    parser.add_argument(
        "--backfill-hours",
        type=int,
        default=6,
        help="How far back to look when recent window has fewer than --min-export items",
    )
    parser.add_argument("--dry-run", action="store_true", help="Do not write files or DB")
    return parser.parse_args()


def ensure_dirs(base_dir: Path) -> tuple[Path, Path]:
    collected_dir = base_dir / "collected"
    collected_dir.mkdir(parents=True, exist_ok=True)
    db_path = base_dir / "collector.sqlite3"
    return collected_dir, db_path


def init_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS collected_articles (
            url TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            published_at TEXT NOT NULL,
            matched_orgs TEXT NOT NULL,
            saved_path TEXT NOT NULL,
            collected_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def parse_published(entry: feedparser.FeedParserDict) -> dt.datetime | None:
    if getattr(entry, "published_parsed", None):
        return dt.datetime(*entry.published_parsed[:6], tzinfo=dt.timezone.utc)
    if getattr(entry, "updated_parsed", None):
        return dt.datetime(*entry.updated_parsed[:6], tzinfo=dt.timezone.utc)
    return None


def build_rss_url(query: str) -> str:
    return f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl=ko&gl=KR&ceid=KR:ko"


def fetch_rss_entries(queries: list[str]) -> list[feedparser.FeedParserDict]:
    # Aggregate multiple RSS queries and dedupe by entry link.
    seen_links: set[str] = set()
    merged: list[feedparser.FeedParserDict] = []
    for q in queries:
        url = build_rss_url(q)
        feed = feedparser.parse(url)
        for entry in getattr(feed, "entries", []):
            link = str(getattr(entry, "link", "")).strip()
            if not link or link in seen_links:
                continue
            seen_links.add(link)
            merged.append(entry)
    return merged


def _parse_naver_time(raw: str, now_local: dt.datetime) -> dt.datetime | None:
    s = (raw or "").strip()
    if not s:
        return None

    m = re.search(r"(\d+)\s*분\s*전", s)
    if m:
        return (now_local - dt.timedelta(minutes=int(m.group(1)))).astimezone(dt.timezone.utc)
    m = re.search(r"(\d+)\s*시간\s*전", s)
    if m:
        return (now_local - dt.timedelta(hours=int(m.group(1)))).astimezone(dt.timezone.utc)
    m = re.search(r"(\d+)\s*일\s*전", s)
    if m:
        return (now_local - dt.timedelta(days=int(m.group(1)))).astimezone(dt.timezone.utc)

    m = re.search(r"(\d{4})\.(\d{1,2})\.(\d{1,2})\.", s)
    if m:
        y, mo, d = map(int, m.groups())
        try:
            local_midnight = now_local.replace(year=y, month=mo, day=d, hour=0, minute=0, second=0, microsecond=0)
            return local_midnight.astimezone(dt.timezone.utc)
        except ValueError:
            return None
    return None


def _fetch_page_title(url: str) -> str:
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=8, allow_redirects=True)
        resp.raise_for_status()
    except Exception:
        return ""
    soup = BeautifulSoup(resp.text, "html.parser")
    og = soup.find("meta", attrs={"property": "og:title"})
    if og and og.get("content"):
        return str(og.get("content", "")).strip()
    if soup.title and soup.title.string:
        return str(soup.title.string).strip()
    return ""


def fetch_naver_entries(queries: list[str], per_query_limit: int = 12) -> list[feedparser.FeedParserDict]:
    merged: list[feedparser.FeedParserDict] = []
    seen_links: set[str] = set()
    now_local = dt.datetime.now().astimezone()
    title_cache: dict[str, str] = {}

    for q in queries:
        params = {"where": "news", "query": q, "sort": "1", "pd": "1"}
        try:
            resp = requests.get(
                NAVER_SEARCH_URL,
                params=params,
                headers={"User-Agent": USER_AGENT},
                timeout=12,
            )
            resp.raise_for_status()
        except Exception as exc:
            print(f"[fallback] naver fetch failed: {q} ({exc})")
            continue

        soup = BeautifulSoup(resp.text, "html.parser")
        cards = soup.select("div.sds-comps-profile")
        added = 0
        for card in cards:
            keep_btn = card.find("button", attrs={"data-url": True})
            link = str(keep_btn.get("data-url", "") if keep_btn else "").strip()
            if not link or link in seen_links:
                continue

            info_text = " ".join(card.stripped_strings)
            published_utc = _parse_naver_time(info_text, now_local)
            if not published_utc:
                continue

            source_node = card.select_one("a[href*='media.naver.com/press/']")
            source = source_node.get_text(" ", strip=True) if source_node else "네이버뉴스"

            if link in title_cache:
                title = title_cache[link]
            else:
                title = _fetch_page_title(link)
                title_cache[link] = title
            if not title:
                continue

            seen_links.add(link)
            merged.append(
                feedparser.FeedParserDict(
                    {
                        "title": title,
                        "link": link,
                        "published_parsed": published_utc.utctimetuple(),
                        "source": feedparser.FeedParserDict({"title": source}),
                    }
                )
            )
            added += 1
            if added >= per_query_limit:
                break
        # Reduce chance of temporary blocking when running multiple queries.
        time.sleep(0.2)
    return merged


def sanitize_filename(name: str, max_len: int = 100) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|\n\r\t]", "_", name)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = cleaned.strip(".") or "untitled"
    return cleaned[:max_len]


def extract_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    chunks = [p.get_text(" ", strip=True) for p in soup.find_all(["p", "article", "h1", "h2", "h3"])]
    text = "\n".join(chunk for chunk in chunks if chunk)
    if not text:
        text = soup.get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()


def fetch_article_text(url: str, timeout: int = 12) -> tuple[str, str]:
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout, allow_redirects=True)
    resp.raise_for_status()
    return resp.url, extract_text(resp.text)


def normalize_for_match(text: str) -> str:
    # Ignore whitespace/newlines and symbols for more robust Korean org-name matching.
    return re.sub(r"[^0-9A-Za-z가-힣]+", "", text).lower()


def matched_orgs(text: str, orgs: dict[str, Iterable[str]]) -> list[str]:
    norm_text = normalize_for_match(text)
    hits: list[str] = []
    for canonical, aliases in orgs.items():
        for alias in aliases:
            if normalize_for_match(alias) in norm_text:
                hits.append(canonical)
                break
    return hits


def _entry_source(entry: feedparser.FeedParserDict, title: str) -> str:
    source_obj = getattr(entry, "source", None)
    source_title = str(getattr(source_obj, "title", "")).strip()
    if source_title:
        return source_title
    # Google News RSS title often ends with " - 언론사"
    if " - " in title:
        return title.rsplit(" - ", 1)[-1].strip()
    return "Google News"


def write_recent_json(path: Path, rows: list[dict], limit: int = 12) -> int:
    if not rows:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("[]\n", encoding="utf-8")
        return 0
    rows = sorted(rows, key=lambda r: str(r.get("_published", "")), reverse=True)

    by_url = {}
    for r in rows:
        url = str(r.get("url", "")).strip()
        if not url or url in by_url:
            continue
        by_url[url] = r
    rows = list(by_url.values())

    # Keep one article per same day + source (latest one first).
    deduped = []
    seen_day_source = set()
    for r in rows:
        k = (str(r.get("date", "")), str(r.get("source", "")))
        if k in seen_day_source:
            continue
        seen_day_source.add(k)
        deduped.append(r)
        if len(deduped) >= limit:
            break

    # If strict day+source dedupe leaves fewer than limit, fill with remaining newest rows.
    if len(deduped) < limit:
        used_urls = {str(r.get("url", "")).strip() for r in deduped}
        for r in rows:
            u = str(r.get("url", "")).strip()
            if not u or u in used_urls:
                continue
            deduped.append(r)
            used_urls.add(u)
            if len(deduped) >= limit:
                break

    payload = [
        {
            "date": str(r.get("date", "")),
            "source": str(r.get("source", "")),
            "title": str(r.get("title", "")),
            "url": str(r.get("url", "")),
            "published_at": str(r.get("published_at", "")),
        }
        for r in deduped
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(payload)


def exists_url(conn: sqlite3.Connection, url: str) -> bool:
    row = conn.execute("SELECT 1 FROM collected_articles WHERE url = ?", (url,)).fetchone()
    return row is not None


def save_article(
    collected_dir: Path,
    title: str,
    published_at_utc: dt.datetime,
    final_url: str,
    org_hits: list[str],
    article_text: str,
) -> Path:
    published_local = published_at_utc.astimezone()
    timestamp = published_local.strftime("%Y%m%d_%H%M%S")
    safe_title = sanitize_filename(title)
    path = collected_dir / f"{timestamp}_{safe_title}.txt"

    header = [
        f"title: {title}",
        f"published_at_utc: {published_at_utc.isoformat()}",
        f"published_at_local: {published_local.isoformat()}",
        f"url: {final_url}",
        f"matched_orgs: {', '.join(org_hits)}",
        "",
    ]
    path.write_text("\n".join(header) + article_text + "\n", encoding="utf-8")
    return path


def upsert_article(
    conn: sqlite3.Connection,
    final_url: str,
    title: str,
    published_at_utc: dt.datetime,
    org_hits: list[str],
    saved_path: Path,
) -> None:
    conn.execute(
        """
        INSERT INTO collected_articles (url, title, published_at, matched_orgs, saved_path, collected_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            final_url,
            title,
            published_at_utc.isoformat(),
            ", ".join(org_hits),
            str(saved_path),
            dt.datetime.now(dt.timezone.utc).isoformat(),
        ),
    )
    conn.commit()


def collect_once(
    base_dir: Path,
    window_minutes: int,
    rss_queries: list[str] | None = None,
    dry_run: bool = False,
    recent_json_out: Path | None = None,
    recent_limit: int = 12,
    min_export: int = 6,
    backfill_hours: int = 6,
) -> None:
    collected_dir, db_path = ensure_dirs(base_dir)
    conn = init_db(db_path)
    now_utc = dt.datetime.now(dt.timezone.utc)
    threshold = now_utc - dt.timedelta(minutes=window_minutes)
    backfill_threshold = now_utc - dt.timedelta(hours=max(1, backfill_hours))
    queries = [q.strip() for q in (rss_queries or RSS_QUERIES) if str(q).strip()]
    rss_entries = fetch_rss_entries(queries)
    naver_entries = fetch_naver_entries(queries)
    entries: list[feedparser.FeedParserDict] = []
    seen_links: set[str] = set()
    for e in [*rss_entries, *naver_entries]:
        link = str(getattr(e, "link", "")).strip()
        if not link or link in seen_links:
            continue
        seen_links.add(link)
        entries.append(e)

    total = len(entries)
    recent = 0  # Stage 1: passed the time-window filter.
    org_matched = 0  # Stage 2: passed pollster-name match in article body.
    org_missed = 0
    saved = 0
    stage1_rows: list[dict] = []
    backfill_rows: list[dict] = []

    for entry in entries:
        title = getattr(entry, "title", "(no title)")
        raw_url = getattr(entry, "link", "")
        published = parse_published(entry)

        if not raw_url or not published:
            continue
        published_local = published.astimezone()
        row = {
            "date": published_local.date().isoformat(),
            "source": _entry_source(entry, title),
            "title": title,
            "url": raw_url,
            "published_at": published_local.isoformat(),
            "_published": published.isoformat(),
        }
        if published >= threshold:
            recent += 1
            stage1_rows.append(row)
        elif published >= backfill_threshold:
            backfill_rows.append(row)
            continue
        else:
            continue

        try:
            final_url, article_text = fetch_article_text(raw_url)
        except Exception as exc:
            print(f"[skip] fetch failed: {title} ({exc})")
            continue

        if exists_url(conn, final_url):
            print(f"[dup] {title}")
            continue

        # Match against both body and title to reduce false misses on short/paywalled pages.
        hits = matched_orgs(f"{title}\n{article_text}", POLLING_ORGS)
        if not hits:
            org_missed += 1
            print(f"[pass] org not found: {title}")
            continue
        org_matched += 1

        if dry_run:
            print(f"[dry-run] save candidate: {title} | {hits}")
            saved += 1
            continue

        saved_path = save_article(collected_dir, title, published, final_url, hits, article_text)
        upsert_article(conn, final_url, title, published, hits, saved_path)
        saved += 1
        print(f"[saved] {saved_path.name}")

    exported_recent = 0
    if recent_json_out is not None:
        export_rows = list(stage1_rows)
        if len(export_rows) < min_export and backfill_rows:
            seen_urls = {str(r.get("url", "")).strip() for r in export_rows}
            for r in sorted(backfill_rows, key=lambda x: str(x.get("_published", "")), reverse=True):
                u = str(r.get("url", "")).strip()
                if not u or u in seen_urls:
                    continue
                export_rows.append(r)
                seen_urls.add(u)
                if len(export_rows) >= min_export:
                    break
        exported_recent = write_recent_json(recent_json_out, export_rows, limit=recent_limit)

    print(
        "done: "
        f"total={total}, "
        f"stage1_recent={recent}, "
        f"stage2_org_matched={org_matched}, "
        f"stage2_org_missed={org_missed}, "
        f"saved={saved}, "
        f"stage1_exported={exported_recent}, "
        f"stage1_backfill_pool={len(backfill_rows)}, "
        f"rss_queries={len(queries)}, "
        f"rss_total={len(rss_entries)}, "
        f"fallback_naver_total={len(naver_entries)}, "
        f"threshold_utc={threshold.isoformat()}"
    )


def main() -> None:
    args = parse_args()
    base_dir = Path(args.base_dir).expanduser().resolve()
    recent_json_out = None
    if args.recent_json_out:
        recent_json_out = Path(args.recent_json_out).expanduser()
        if not recent_json_out.is_absolute():
            recent_json_out = (base_dir / recent_json_out).resolve()
    collect_once(
        base_dir=base_dir,
        window_minutes=args.window_minutes,
        rss_queries=[*RSS_QUERIES, *[q.strip() for q in args.rss_query if str(q).strip()]],
        dry_run=args.dry_run,
        recent_json_out=recent_json_out,
        recent_limit=args.recent_limit,
        min_export=args.min_export,
        backfill_hours=args.backfill_hours,
    )


if __name__ == "__main__":
    main()
