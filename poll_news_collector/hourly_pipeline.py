#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Iterable

from collector import POLLING_ORGS, collect_once, init_db
from extract_observed_point import extract_point_from_text, fetch_text

REQUIRED_PARTIES = {"더불어민주당", "국민의힘"}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Hourly orchestrator: collect -> extract -> update -> git")
    p.add_argument("--base-dir", default=".", help="collector workspace dir")
    p.add_argument("--project-dir", required=True, help="path to codex_handoff_pack")
    p.add_argument("--window-minutes", type=int, default=60)
    p.add_argument("--observed-jsonl", default="outputs/observed_web_points.jsonl")
    p.add_argument("--run-update", action="store_true", help="run update_week_window.py")
    p.add_argument(
        "--news-json-out",
        default="docs/news_latest.json",
        help="Path to stage1 recent-news JSON for dashboard",
    )
    p.add_argument("--news-limit", type=int, default=6, help="Max news items to keep in news JSON")
    p.add_argument("--force-url", action="append", default=[], help="Force-process URL(s) for testing")
    p.add_argument("--git-commit", action="store_true", help="commit changed project files")
    p.add_argument("--git-push", action="store_true", help="push after commit")
    p.add_argument(
        "--git-work-branch",
        default="main",
        help="Branch where hourly commits are created (e.g., codex/hourly-news-refresh)",
    )
    p.add_argument(
        "--git-main-branch",
        default="main",
        help="Main branch to promote hourly commits into",
    )
    p.add_argument(
        "--git-promote-main",
        action="store_true",
        help="When using a non-main work branch, rebase it onto origin/main and push to main",
    )
    p.add_argument("--max-retries", type=int, default=3, help="max retries for rejected extraction URLs")
    p.add_argument("--retry-delay-minutes", type=int, default=60, help="delay before retrying a rejected extraction URL")
    p.add_argument("--triage-md", default="outputs/extraction_triage.md", help="path to extraction triage markdown")
    return p.parse_args()


def ensure_extract_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS extracted_articles (
            url TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            reason TEXT,
            date_end TEXT,
            pollster TEXT,
            values_json TEXT,
            source_url TEXT,
            extracted_at TEXT NOT NULL,
            retry_count INTEGER NOT NULL DEFAULT 0,
            next_retry_at TEXT
        )
        """
    )
    # Backward-compatible migration for pre-existing DBs.
    cols = {row[1] for row in conn.execute("PRAGMA table_info(extracted_articles)").fetchall()}
    if "retry_count" not in cols:
        conn.execute("ALTER TABLE extracted_articles ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0")
    if "next_retry_at" not in cols:
        conn.execute("ALTER TABLE extracted_articles ADD COLUMN next_retry_at TEXT")
    conn.commit()


def write_extraction_triage(project_dir: Path, conn: sqlite3.Connection, max_retries: int, out_path: Path) -> None:
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
    rows = conn.execute(
        """
        SELECT url, reason, retry_count, next_retry_at, extracted_at
        FROM extracted_articles
        WHERE status = 'rejected'
        ORDER BY extracted_at DESC
        """
    ).fetchall()

    reason_counts: dict[str, int] = {}
    blocked = 0
    queued = 0
    for _, reason, retry_count, next_retry_at, _ in rows:
        key = str(reason or "unknown")
        reason_counts[key] = reason_counts.get(key, 0) + 1
        rc = int(retry_count or 0)
        if rc >= max_retries:
            blocked += 1
        elif not next_retry_at or str(next_retry_at) <= now_iso:
            queued += 1

    lines = [
        "# Extraction Triage",
        "",
        f"- Rejected URLs: {len(rows)}",
        f"- Retry-eligible now: {queued}",
        f"- Max-retry blocked: {blocked}",
        "",
        "## Reasons",
    ]
    if reason_counts:
        for reason, count in sorted(reason_counts.items(), key=lambda kv: kv[1], reverse=True):
            lines.append(f"- {reason}: {count}")
    else:
        lines.append("- No rejected items.")

    lines.append("")
    lines.append("## Top Rejected URLs")
    for url, reason, retry_count, next_retry_at, extracted_at in rows[:15]:
        lines.append(
            f"- {url} | reason={reason or 'unknown'} | retry_count={int(retry_count or 0)} "
            f"| next_retry_at={next_retry_at or 'now'} | extracted_at={extracted_at}"
        )
    if not rows:
        lines.append("- None")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_article_text(saved_path: Path) -> str:
    text = saved_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if not line.strip():
            return "\n".join(lines[i + 1 :]).strip()
    return text


def read_metadata(saved_path: Path) -> dict:
    meta = {}
    for line in saved_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            break
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        meta[k.strip()] = v.strip()
    return meta


def is_valid_point(point: dict) -> tuple[bool, str]:
    pollster = str(point.get("pollster") or "")
    date_end = str(point.get("date_end") or "")
    values = point.get("values") or {}
    context = point.get("context") or {}

    if pollster not in POLLING_ORGS:
        return False, "pollster_not_target"
    if not date_end:
        return False, "missing_date"
    if not isinstance(values, dict) or len(values) < 2:
        return False, "insufficient_values"
    if isinstance(context, dict):
        if context.get("has_local_election_context") and not context.get("is_national_party_poll"):
            return False, "context_local_election_poll"
        if context.get("is_national_party_poll") is False:
            return False, "context_not_national_party_poll"
    if not REQUIRED_PARTIES.issubset(set(values.keys())):
        return False, "missing_major_parties"
    try:
        for v in values.values():
            fv = float(v)
            if fv < 0 or fv > 100:
                return False, "invalid_value_range"
    except Exception:
        return False, "invalid_value_type"
    return True, "ok"


def load_seen_signatures(jsonl_path: Path) -> set[tuple[str, str, str]]:
    seen: set[tuple[str, str, str]] = set()
    if not jsonl_path.exists():
        return seen
    for line in jsonl_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        sig = (
            str(rec.get("pollster", "")),
            str(rec.get("date_end", "")),
            str(rec.get("source_url", "")),
        )
        seen.add(sig)
    return seen


def append_jsonl(path: Path, records: Iterable[dict]) -> int:
    n = 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1
    return n


def monday_sunday_window(date_str: str) -> tuple[str, str]:
    d = dt.date.fromisoformat(date_str)
    start = d - dt.timedelta(days=d.weekday())
    end = start + dt.timedelta(days=6)
    return start.isoformat(), end.isoformat()


def run_update_week_window(project_dir: Path, observed_jsonl: Path, week_start: str, week_end: str) -> None:
    py = sys.executable
    script = project_dir / "src" / "update_week_window.py"
    cmd = [
        py,
        str(script),
        "--week-start",
        week_start,
        "--week-end",
        week_end,
        "--observed-jsonl",
        str(observed_jsonl),
    ]
    subprocess.run(cmd, cwd=project_dir, check=True)


def git_commit(
    project_dir: Path,
    paths: list[Path],
    message: str,
    push: bool,
    work_branch: str,
    main_branch: str,
    promote_main: bool,
) -> None:
    current_branch = (
        subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=project_dir,
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()
        or "main"
    )
    if current_branch != work_branch:
        raise RuntimeError(f"[git] expected work branch '{work_branch}', but current branch is '{current_branch}'")

    rel_paths = [str(p.relative_to(project_dir)) for p in paths if p.exists()]
    if not rel_paths:
        print("[git] no target files to add")
        return

    subprocess.run(["git", "add", "--", *rel_paths], cwd=project_dir, check=True)
    status = subprocess.run(["git", "diff", "--cached", "--name-only"], cwd=project_dir, text=True, capture_output=True, check=True)
    staged = [s for s in status.stdout.splitlines() if s.strip()]
    if not staged:
        print("[git] nothing staged")
        return

    subprocess.run(["git", "commit", "-m", message], cwd=project_dir, check=True)
    print(f"[git] committed: {message}")
    if push:
        if not promote_main or work_branch == main_branch:
            pushed = False
            for attempt in range(1, 4):
                try:
                    subprocess.run(["git", "push"], cwd=project_dir, check=True)
                    print("[git] pushed")
                    pushed = True
                    break
                except subprocess.CalledProcessError as exc:
                    print(f"[git] push failed (attempt {attempt}/3): {exc}")
                    if attempt >= 3:
                        raise
                    subprocess.run(["git", "fetch", "origin"], cwd=project_dir, check=True)
                    subprocess.run(["git", "pull", "--rebase", "--autostash", "origin", main_branch], cwd=project_dir, check=True)
            if not pushed:
                raise RuntimeError("[git] push failed after retries")
            return

        promoted = False
        for attempt in range(1, 4):
            try:
                # Keep work branch rebased on main to avoid repeated non-fast-forward failures.
                subprocess.run(["git", "fetch", "origin"], cwd=project_dir, check=True)
                subprocess.run(["git", "pull", "--rebase", "--autostash", "origin", main_branch], cwd=project_dir, check=True)
                subprocess.run(["git", "push", "--force-with-lease", "origin", work_branch], cwd=project_dir, check=True)
                subprocess.run(["git", "push", "origin", f"HEAD:{main_branch}"], cwd=project_dir, check=True)
                print("[git] pushed via work branch and promoted to main")
                promoted = True
                break
            except subprocess.CalledProcessError as exc:
                print(f"[git] promote failed (attempt {attempt}/3): {exc}")
                if attempt >= 3:
                    raise
        if not promoted:
            raise RuntimeError("[git] main promotion failed after retries")


def main() -> None:
    args = parse_args()
    base_dir = Path(args.base_dir).expanduser().resolve()
    project_dir = Path(args.project_dir).expanduser().resolve()
    observed_jsonl = Path(args.observed_jsonl)
    triage_md = Path(args.triage_md)
    if not observed_jsonl.is_absolute():
        observed_jsonl = (project_dir / observed_jsonl).resolve()
    if not triage_md.is_absolute():
        triage_md = (project_dir / triage_md).resolve()
    news_json_out = Path(args.news_json_out).expanduser()
    if not news_json_out.is_absolute():
        news_json_out = (project_dir / news_json_out).resolve()

    collect_once(
        base_dir=base_dir,
        window_minutes=args.window_minutes,
        dry_run=False,
        recent_json_out=news_json_out,
        recent_limit=args.news_limit,
    )

    conn = init_db(base_dir / "collector.sqlite3")
    ensure_extract_table(conn)

    now_utc = dt.datetime.now(dt.timezone.utc)
    now_iso = now_utc.isoformat()
    rows = conn.execute(
        """
        SELECT c.url, c.saved_path, c.published_at, COALESCE(e.retry_count, 0), e.next_retry_at
        FROM collected_articles c
        LEFT JOIN extracted_articles e ON c.url = e.url
        WHERE e.url IS NULL
           OR (
                e.status = 'rejected'
                AND COALESCE(e.retry_count, 0) < ?
                AND (e.next_retry_at IS NULL OR e.next_retry_at <= ?)
           )
        ORDER BY c.published_at ASC
        """
        ,
        (args.max_retries, now_iso),
    ).fetchall()

    seen = load_seen_signatures(observed_jsonl)
    to_append = []
    accepted_dates: list[str] = []
    retried_candidates = 0

    for url, saved_path, published_at, retry_count, _ in rows:
        prev_retry = int(retry_count or 0)
        if prev_retry > 0:
            retried_candidates += 1
        saved = Path(saved_path)
        if not saved.exists():
            new_retry = min(prev_retry + 1, args.max_retries)
            next_retry_at = None
            if new_retry < args.max_retries:
                next_retry_at = (now_utc + dt.timedelta(minutes=args.retry_delay_minutes)).isoformat()
            conn.execute(
                """
                INSERT OR REPLACE INTO extracted_articles
                (url, status, reason, date_end, pollster, values_json, source_url, extracted_at, retry_count, next_retry_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (url, "rejected", "missing_saved_file", None, None, "{}", "", now_iso, new_retry, next_retry_at),
            )
            continue

        meta = read_metadata(saved)
        article_text = read_article_text(saved)
        point = extract_point_from_text(
            text=article_text,
            source_url=str(meta.get("url") or url),
            forced_date=None,
            forced_pollster=None,
        )

        if not point.get("date_end") and published_at:
            point["date_end"] = str(published_at).split("T", 1)[0]

        ok, reason = is_valid_point(point)
        status = "accepted" if ok else "rejected"
        new_retry = 0
        next_retry_at = None
        if not ok:
            new_retry = min(prev_retry + 1, args.max_retries)
            if new_retry < args.max_retries:
                next_retry_at = (now_utc + dt.timedelta(minutes=args.retry_delay_minutes)).isoformat()

        conn.execute(
            """
            INSERT OR REPLACE INTO extracted_articles
            (url, status, reason, date_end, pollster, values_json, source_url, extracted_at, retry_count, next_retry_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                url,
                status,
                reason,
                point.get("date_end"),
                point.get("pollster"),
                json.dumps(point.get("values", {}), ensure_ascii=False),
                point.get("source_url", ""),
                now_iso,
                new_retry,
                next_retry_at,
            ),
        )

        if ok:
            sig = (
                str(point.get("pollster", "")),
                str(point.get("date_end", "")),
                str(point.get("source_url", "")),
            )
            if sig not in seen:
                to_append.append(point)
                seen.add(sig)
            accepted_dates.append(str(point.get("date_end")))

    for forced_url in args.force_url:
        point = extract_point_from_text(
            text=fetch_text(forced_url),
            source_url=forced_url,
            forced_date=None,
            forced_pollster=None,
        )
        if not point.get("date_end"):
            point["date_end"] = dt.date.today().isoformat()

        ok, reason = is_valid_point(point)
        status = "accepted" if ok else "rejected"
        new_retry = 0 if ok else 1
        next_retry_at = None if ok or new_retry >= args.max_retries else (now_utc + dt.timedelta(minutes=args.retry_delay_minutes)).isoformat()

        conn.execute(
            """
            INSERT OR REPLACE INTO extracted_articles
            (url, status, reason, date_end, pollster, values_json, source_url, extracted_at, retry_count, next_retry_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                forced_url,
                status,
                reason,
                point.get("date_end"),
                point.get("pollster"),
                json.dumps(point.get("values", {}), ensure_ascii=False),
                point.get("source_url", ""),
                now_iso,
                new_retry,
                next_retry_at,
            ),
        )

        if ok:
            sig = (
                str(point.get("pollster", "")),
                str(point.get("date_end", "")),
                str(point.get("source_url", "")),
            )
            if sig not in seen:
                to_append.append(point)
                seen.add(sig)
            accepted_dates.append(str(point.get("date_end")))

    write_extraction_triage(project_dir, conn, args.max_retries, triage_md)
    conn.commit()

    appended = append_jsonl(observed_jsonl, to_append) if to_append else 0
    print(f"[extract] candidates={len(rows)} retried={retried_candidates} accepted={len(accepted_dates)} appended={appended}")

    week_start, week_end = (None, None)
    update_ok = False
    if accepted_dates:
        week_start, week_end = monday_sunday_window(sorted(accepted_dates)[-1])
        if args.run_update:
            try:
                run_update_week_window(project_dir, observed_jsonl, week_start, week_end)
                update_ok = True
                print(f"[update] ran update_week_window for {week_start}~{week_end}")
            except subprocess.CalledProcessError as exc:
                print(f"[update] failed for {week_start}~{week_end}: {exc}; continuing with news refresh commit")
        else:
            update_ok = True

    if args.git_commit:
        targets = [triage_md, news_json_out]
        if week_start and week_end and update_ok:
            targets.extend(
                [
                    observed_jsonl,
                    project_dir / "outputs" / "weighted_time_series.xlsx",
                    project_dir / "outputs" / f"weekly_public_points_{week_start}_{week_end}.csv",
                    project_dir / "outputs" / "pollster_watchlist.csv",
                    project_dir / "outputs" / "pollster_watchlist.md",
                    project_dir / "outputs" / f"update_log_{week_start}_{week_end}.md",
                ]
            )
            msg = f"chore: hourly poll update ({week_start}~{week_end})"
        else:
            ts = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
            msg = f"chore: hourly news refresh ({ts})"
        git_commit(
            project_dir,
            targets,
            msg,
            push=args.git_push,
            work_branch=args.git_work_branch,
            main_branch=args.git_main_branch,
            promote_main=args.git_promote_main,
        )


if __name__ == "__main__":
    main()
