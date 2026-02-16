from __future__ import annotations

import argparse
import json
import os
import re
import urllib.parse
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List

import pandas as pd

PARTY_ALIASES = {
    "더불어민주당": ["더불어민주당", "민주당", "더민주", "이재명"],
    "국민의힘": ["국민의힘", "국민의 힘", "국힘"],
    "조국혁신당": ["조국혁신당", "조국"],
    "개혁신당": ["개혁신당", "이준석"],
}
PARTY_LIST = list(PARTY_ALIASES.keys())
ISSUE_TYPES = ["경제", "안보", "사법", "인사", "부패/비리", "정책성과", "사고/참사"]

POS_WORDS = ["호재", "상승", "반등", "우세", "지지", "확대", "개선", "강세", "선전", "돌파", "성공"]
NEG_WORDS = ["악재", "하락", "논란", "비판", "의혹", "부진", "약세", "실패", "위기", "충돌", "수사", "기소"]

ISSUE_TYPE_KEYWORDS = {
    "경제": ["경제", "물가", "세금", "고용", "금리", "민생", "예산"],
    "안보": ["안보", "외교", "국방", "북한", "미사일"],
    "사법": ["사법", "재판", "수사", "기소", "법원", "검찰"],
    "인사": ["인사", "장관", "임명", "공천"],
    "부패/비리": ["비리", "부패", "의혹", "특혜"],
    "정책성과": ["정책", "성과", "개혁", "공약", "발표"],
    "사고/참사": ["사고", "참사", "재난", "붕괴", "화재"],
}


@dataclass
class NewsItem:
    title: str
    link: str
    published: datetime | None
    summary: str
    keyword: str


def fetch_url_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8", "ignore")


def parse_rss_items(xml_text: str, keyword: str) -> List[NewsItem]:
    root = ET.fromstring(xml_text)
    items: List[NewsItem] = []
    for it in root.findall(".//item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        summary = (it.findtext("description") or "").strip()
        pub = (it.findtext("pubDate") or "").strip()
        dt = None
        if pub:
            try:
                dt = datetime.strptime(pub, "%a, %d %b %Y %H:%M:%S %Z")
            except Exception:
                dt = None
        if title and link:
            items.append(NewsItem(title=title, link=link, published=dt, summary=summary, keyword=keyword))
    return items


def google_news_rss(keyword: str, week_start: str, week_end: str) -> str:
    query = f'"{keyword}" after:{week_start} before:{week_end}'
    q = urllib.parse.quote(query)
    return f"https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko"


def infer_issue_type(keyword: str, text: str) -> str:
    s = f"{keyword} {text}"
    for issue_type, kws in ISSUE_TYPE_KEYWORDS.items():
        if any(k in s for k in kws):
            return issue_type
    return "정책성과"


def score_text(text: str) -> int:
    pos = sum(text.count(w) for w in POS_WORDS)
    neg = sum(text.count(w) for w in NEG_WORDS)
    return pos - neg


def assess_party_scores_rule(items: List[NewsItem]) -> pd.DataFrame:
    rows = []
    for party, aliases in PARTY_ALIASES.items():
        total_score = 0
        mention_count = 0
        dominant_issue = "정책성과"
        issue_counter: Dict[str, int] = {}

        for it in items:
            text = f"{it.title} {it.summary}"
            if any(a in text for a in aliases):
                mention_count += 1
                total_score += score_text(text)
                t = infer_issue_type(it.keyword, text)
                issue_counter[t] = issue_counter.get(t, 0) + 1

        if issue_counter:
            dominant_issue = sorted(issue_counter.items(), key=lambda x: x[1], reverse=True)[0][0]

        rows.append(
            {
                "target_party": party,
                "mention_count": mention_count,
                "raw_score": float(total_score),
                "issue_type": dominant_issue,
                "confidence": 0.55,
                "rationale": "rule_based_lexicon",
            }
        )

    return pd.DataFrame(rows)


def _strip_json_block(s: str) -> str:
    t = s.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z0-9]*\n", "", t)
        t = re.sub(r"\n```$", "", t)
    return t.strip()


def call_llm_json(
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    base_url: str,
) -> dict:
    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    def _post(json_payload: dict) -> dict:
        req = urllib.request.Request(
            url,
            data=json.dumps(json_payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.loads(r.read().decode("utf-8", "ignore"))

    try:
        body = _post(payload)
    except urllib.error.HTTPError as e:
        # Perplexity sonar models may reject OpenAI response_format options.
        if e.code == 400 and "response_format" in payload:
            payload = dict(payload)
            payload.pop("response_format", None)
            body = _post(payload)
        else:
            raise

    content = body["choices"][0]["message"]["content"]
    return json.loads(_strip_json_block(content))


def assess_party_scores_llm(
    items: List[NewsItem],
    model: str,
    api_key: str,
    max_items: int,
    base_url: str,
) -> pd.DataFrame:
    compact = []
    for i, it in enumerate(items[:max_items], 1):
        compact.append(
            {
                "idx": i,
                "keyword": it.keyword,
                "title": it.title,
                "summary": it.summary[:280],
                "published": it.published.isoformat() if it.published else "",
            }
        )

    system_prompt = (
        "당신은 한국 정치 뉴스 분석가다. "
        "입력 기사들만 근거로 각 정당별 유불리 점수를 평가해 JSON만 출력하라."
    )
    schema_hint = {
        "party_assessments": [
            {
                "target_party": "더불어민주당|국민의힘|조국혁신당|개혁신당",
                "mention_count": 0,
                "raw_score": 0.0,
                "issue_type": "경제|안보|사법|인사|부패/비리|정책성과|사고/참사",
                "confidence": 0.0,
                "rationale": "짧은 근거",
            }
        ]
    }
    user_prompt = (
        "[기사 입력]\n"
        f"{json.dumps(compact, ensure_ascii=False)}\n\n"
        "[평가 규칙]\n"
        "- raw_score: 정당 유리(+) 불리(-), 대략 -30~+30 범위\n"
        "- mention_count: 기사에서 해당 정당 관련 언급 개수 추정\n"
        "- confidence: 0~1\n"
        "- 반드시 4개 정당 모두 반환\n\n"
        "[출력 JSON 스키마 예시]\n"
        f"{json.dumps(schema_hint, ensure_ascii=False)}"
    )

    parsed = call_llm_json(api_key, model, system_prompt, user_prompt, base_url)
    rows = parsed.get("party_assessments", []) if isinstance(parsed, dict) else []

    cleaned = []
    for party in PARTY_LIST:
        hit = None
        for r in rows:
            if str(r.get("target_party", "")).strip() == party:
                hit = r
                break
        if hit is None:
            cleaned.append(
                {
                    "target_party": party,
                    "mention_count": 0,
                    "raw_score": 0.0,
                    "issue_type": "정책성과",
                    "confidence": 0.0,
                    "rationale": "llm_missing_party_filled",
                }
            )
            continue

        issue_type = str(hit.get("issue_type", "정책성과")).strip()
        if issue_type not in ISSUE_TYPES:
            issue_type = "정책성과"

        conf = pd.to_numeric(hit.get("confidence", 0.0), errors="coerce")
        conf = float(conf) if pd.notna(conf) else 0.0
        conf = max(0.0, min(1.0, conf))

        mention = int(max(0, int(pd.to_numeric(hit.get("mention_count", 0), errors="coerce") or 0)))
        score = float(pd.to_numeric(hit.get("raw_score", 0.0), errors="coerce") or 0.0)

        cleaned.append(
            {
                "target_party": party,
                "mention_count": mention,
                "raw_score": score,
                "issue_type": issue_type,
                "confidence": conf,
                "rationale": str(hit.get("rationale", ""))[:240],
            }
        )

    return pd.DataFrame(cleaned)


def to_issue_rows(assess_df: pd.DataFrame, issue_date: str) -> pd.DataFrame:
    rows = []
    for _, r in assess_df.iterrows():
        mention = int(r["mention_count"])
        score = float(r["raw_score"])
        conf = float(pd.to_numeric(r.get("confidence", 0.0), errors="coerce") or 0.0)
        rationale = str(r.get("rationale", "")).strip()
        if mention == 0:
            continue

        avg = score / max(1, mention)
        intensity = int(max(1, min(3, round(abs(avg)))))
        if score > 0:
            direction = f"{r['target_party']} 유리"
        elif score < 0:
            direction = f"{r['target_party']} 불리"
        else:
            direction = "중립"
            intensity = 0

        rows.append(
            {
                "issue_date": issue_date,
                "issue_type": r["issue_type"],
                "intensity": intensity,
                "direction": direction,
                "persistence": "잔존",
                "target_party": r["target_party"],
                "note": f"news_mentions={mention}, raw_score={score:.1f}, confidence={conf:.2f}, rationale={rationale}",
            }
        )
    return pd.DataFrame(rows)


def merge_into_issue_input(issue_rows: pd.DataFrame, issue_input_path: Path) -> None:
    cols = ["issue_date", "issue_type", "intensity", "direction", "persistence", "target_party", "note"]
    if issue_input_path.exists():
        base = pd.read_csv(issue_input_path)
    else:
        base = pd.DataFrame(columns=cols)

    for c in cols:
        if c not in base.columns:
            base[c] = ""

    merged = pd.concat([base[cols], issue_rows[cols]], ignore_index=True)
    merged = merged.drop_duplicates(subset=["issue_date", "target_party", "direction", "note"], keep="last")
    merged.to_csv(issue_input_path, index=False)


def main() -> None:
    base = Path(__file__).resolve().parents[1]

    ap = argparse.ArgumentParser(description="Issue intake from keywords/articles -> weekly political impact rows")
    ap.add_argument("--week-start", required=True, help="YYYY-MM-DD")
    ap.add_argument("--week-end", required=True, help="YYYY-MM-DD (inclusive)")
    ap.add_argument("--keywords", required=True, help="comma-separated keywords")
    ap.add_argument("--extra-url", action="append", default=[], help="optional article url (repeatable)")
    ap.add_argument("--max-items-per-keyword", type=int, default=15)
    ap.add_argument("--mode", choices=["rule", "llm", "auto"], default="llm")
    ap.add_argument("--llm-provider", choices=["openai", "perplexity"], default="openai")
    ap.add_argument("--llm-model", default="", help="LLM model name (provider default if empty)")
    ap.add_argument("--llm-base-url", default="", help="Override chat completions base URL")
    ap.add_argument("--llm-max-items", type=int, default=40)
    ap.add_argument("--openai-api-key", default="")
    ap.add_argument("--perplexity-api-key", default="")
    ap.add_argument("--out-assess", default="outputs/issue_assessment_latest.csv")
    ap.add_argument("--out-news", default="outputs/issue_news_latest.csv")
    ap.add_argument("--issue-input", default="data/issues_input.csv")
    args = ap.parse_args()

    week_start = pd.to_datetime(args.week_start).date().isoformat()
    week_end_inclusive = pd.to_datetime(args.week_end).date()
    week_end_exclusive = (week_end_inclusive + timedelta(days=1)).isoformat()

    kws = [k.strip() for k in args.keywords.split(",") if k.strip()]
    if not kws:
        raise SystemExit("No keywords provided.")

    all_items: List[NewsItem] = []
    for kw in kws:
        rss_url = google_news_rss(kw, week_start, week_end_exclusive)
        try:
            xml_text = fetch_url_text(rss_url)
            items = parse_rss_items(xml_text, kw)[: args.max_items_per_keyword]
            all_items.extend(items)
        except Exception as e:
            print(f"WARN keyword '{kw}' rss fetch failed: {e}")

    for u in args.extra_url:
        try:
            page_html = fetch_url_text(u)
            m = re.search(r"<title>(.*?)</title>", page_html, re.I | re.S)
            title = re.sub(r"\s+", " ", m.group(1)).strip() if m else u
            all_items.append(NewsItem(title=title, link=u, published=None, summary="", keyword="direct_url"))
        except Exception as e:
            print(f"WARN url fetch failed: {u} ({e})")

    if not all_items:
        raise SystemExit("No news items collected from keywords/urls.")

    out_news = base / args.out_news
    out_assess = base / args.out_assess
    issue_input_path = base / args.issue_input

    news_df = pd.DataFrame(
        [
            {
                "keyword": i.keyword,
                "published": i.published.isoformat() if i.published else "",
                "title": i.title,
                "link": i.link,
                "summary": i.summary,
            }
            for i in all_items
        ]
    )
    out_news.parent.mkdir(parents=True, exist_ok=True)
    news_df.to_csv(out_news, index=False)

    if args.llm_provider == "perplexity":
        api_key = args.perplexity_api_key or os.getenv("PPLX_API_KEY", "")
        default_base_url = "https://api.perplexity.ai"
        default_model = "sonar"
    else:
        api_key = args.openai_api_key or os.getenv("OPENAI_API_KEY", "")
        default_base_url = "https://api.openai.com/v1"
        default_model = "gpt-4.1-mini"

    llm_base_url = args.llm_base_url or default_base_url
    llm_model = args.llm_model or default_model
    use_llm = args.mode == "llm" or (args.mode == "auto" and bool(api_key))

    if args.llm_provider == "perplexity":
        key_name = "PPLX_API_KEY"
    else:
        key_name = "OPENAI_API_KEY"

    if use_llm and not api_key:
        print(f"WARN LLM mode requested but {key_name} is missing. Falling back to rule mode.")
        use_llm = False

    if use_llm:
        try:
            assess_df = assess_party_scores_llm(
                all_items,
                llm_model,
                api_key,
                args.llm_max_items,
                llm_base_url,
            )
            assess_df["mode"] = "llm"
        except Exception as e:
            print(f"WARN LLM assessment failed: {e}. Falling back to rule mode.")
            assess_df = assess_party_scores_rule(all_items)
            assess_df["mode"] = "rule_fallback"
    else:
        assess_df = assess_party_scores_rule(all_items)
        assess_df["mode"] = "rule"

    issue_rows = to_issue_rows(assess_df, issue_date=str(week_end_inclusive))

    out_assess.parent.mkdir(parents=True, exist_ok=True)
    assess_df.to_csv(out_assess, index=False)
    merge_into_issue_input(issue_rows, issue_input_path)

    print(f"Collected news items: {len(all_items)}")
    print(f"Mode: {assess_df['mode'].iloc[0] if len(assess_df) else 'unknown'}")
    print(f"Wrote: {out_news}")
    print(f"Wrote: {out_assess}")
    print(f"Updated: {issue_input_path}")
    if len(issue_rows):
        print(issue_rows.to_string(index=False))


if __name__ == "__main__":
    main()
