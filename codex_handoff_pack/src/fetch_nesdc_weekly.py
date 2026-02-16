from __future__ import annotations

import argparse
import csv
import html
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import List

import pandas as pd

BASE = "https://www.nesdc.go.kr"
LIST_PATH = "/portal/bbs/B0000025/list.do?menuNo=200500"
UA = {"User-Agent": "Mozilla/5.0"}


@dataclass
class Post:
    ntt_id: int
    title: str
    posted_date: pd.Timestamp
    view_url: str


@dataclass
class Attachment:
    ntt_id: int
    posted_date: pd.Timestamp
    title: str
    filename: str
    url: str
    local_path: Path


def fetch_html(url: str) -> str:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "ignore")


def parse_list_posts(page_index: int) -> List[Post]:
    url = (
        f"{BASE}{LIST_PATH}&sdate=&edate=&searchCnd=&searchWrd=&pageIndex={page_index}"
    )
    h = fetch_html(url)
    posts: List[Post] = []

    pattern = re.compile(
        r"/portal/bbs/B0000025/view\.do[^\"]*\?nttId=(\d+)&menuNo=200500\"[^>]*>\s*([^<]+?)\s*</a>"
        r".*?<span class=\"col ws\"><i class=\"tit\"></i>(\d{4}-\d{2}-\d{2})</span>",
        re.S,
    )
    for m in pattern.finditer(h):
        ntt = int(m.group(1))
        title = m.group(2).strip()
        d = pd.to_datetime(m.group(3), errors="coerce")
        if pd.isna(d):
            continue
        view_url = f"{BASE}/portal/bbs/B0000025/view.do?nttId={ntt}&menuNo=200500"
        posts.append(Post(ntt, title, d, view_url))
    return posts


def parse_attachments_from_view(post: Post) -> List[tuple[str, str]]:
    h = fetch_html(post.view_url)
    out = []
    for m in re.finditer(r'href="(/portal/cmm/fms/FileDown\.do\?[^"]+)"[^>]*>(.*?)</a>', h, re.S):
        raw_url = html.unescape(m.group(1))
        raw_text = html.unescape(re.sub(r"<.*?>", "", m.group(2)).strip())
        if not raw_text:
            continue
        out.append((f"{BASE}{raw_url}", raw_text))
    return out


def is_xlsx(name: str) -> bool:
    n = name.lower()
    return n.endswith(".xlsx") or n.endswith(".xls")


def download(url: str, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    out_path.write_bytes(data)


def run(week_start: pd.Timestamp, week_end: pd.Timestamp, out_dir: Path, pages: int) -> List[Attachment]:
    posts: List[Post] = []
    for p in range(1, pages + 1):
        posts.extend(parse_list_posts(p))

    posts = [x for x in posts if week_start <= x.posted_date <= week_end]
    posts.sort(key=lambda x: (x.posted_date, x.ntt_id), reverse=True)

    attachments: List[Attachment] = []
    for post in posts:
        for url, fname in parse_attachments_from_view(post):
            ext = Path(fname).suffix.lower()
            if ext not in {".xlsx", ".xls", ".pdf"}:
                continue
            safe_name = re.sub(r"[\\/:*?\"<>|]", "_", fname)
            target = out_dir / f"{post.posted_date.date()}_ntt{post.ntt_id}_{safe_name}"
            download(url, target)
            attachments.append(
                Attachment(
                    ntt_id=post.ntt_id,
                    posted_date=post.posted_date,
                    title=post.title,
                    filename=fname,
                    url=url,
                    local_path=target,
                )
            )
    return attachments


def write_manifest(items: List[Attachment], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ntt_id", "posted_date", "title", "filename", "url", "local_path", "is_xlsx"])
        for it in items:
            w.writerow([
                it.ntt_id,
                it.posted_date.date(),
                it.title,
                it.filename,
                it.url,
                str(it.local_path),
                is_xlsx(it.filename),
            ])


def main() -> None:
    ap = argparse.ArgumentParser(description="Fetch NESDC weekly attachments (xlsx/pdf) from post detail pages")
    ap.add_argument("--week-start", default="2026-02-09")
    ap.add_argument("--week-end", default="2026-02-15")
    ap.add_argument("--pages", type=int, default=3, help="How many list pages to scan")
    ap.add_argument("--out-dir", default="data/nesdc_downloads")
    ap.add_argument("--manifest", default="outputs/nesdc_fetch_manifest.csv")
    args = ap.parse_args()

    ws = pd.to_datetime(args.week_start)
    we = pd.to_datetime(args.week_end)
    items = run(ws, we, Path(args.out_dir), args.pages)
    write_manifest(items, Path(args.manifest))

    print(f"Fetched attachments: {len(items)}")
    xlsx = [i for i in items if is_xlsx(i.filename)]
    pdf = [i for i in items if i.filename.lower().endswith('.pdf')]
    print(f"xlsx: {len(xlsx)}, pdf: {len(pdf)}")
    for it in items:
        print(f"- {it.posted_date.date()} ntt={it.ntt_id} {it.filename} -> {it.local_path}")


if __name__ == "__main__":
    main()
