from __future__ import annotations

import json
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

PARTY_STYLES = {
    "더불어민주당": {"color": "#003B96", "aliases": ["더불어민주당"]},
    "국민의힘": {"color": "#E61E2B", "aliases": ["국민의힘", "국민의 힘"]},
    "지지정당 없음": {"color": "#7A7A7A", "aliases": ["지지정당\n없음", "지지정당 없음", "무당층"]},
    "개혁신당": {"color": "#FF7210", "aliases": ["개혁신당"]},
    "조국혁신당": {"color": "#003A8C", "aliases": ["조국혁신당"]},
    "정의당": {"color": "#FFED00", "aliases": ["정의당"]},
    "진보당": {"color": "#C9152C", "aliases": ["진보당"]},
}
PARTY_ORDER = ["더불어민주당", "국민의힘", "지지정당 없음", "개혁신당", "조국혁신당"]
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

STYLE_CSS = """
:root {
  --bg: #071223;
  --panel: #0B1F3A;
  --panel-soft: #102746;
  --text: #E6ECF5;
  --muted: #9FB0C8;
  --line: #1D355A;
  --accent: #2E6CF6;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: radial-gradient(1200px 500px at 10% -10%, #173A67 0%, var(--bg) 52%);
  color: var(--text);
  font-family: "Inter","Pretendard",system-ui,sans-serif;
  font-feature-settings: "tnum" 1, "lnum" 1;
}
.wrap { max-width: 1320px; margin: 0 auto; padding: 24px 18px 44px; }
.top {
  display: flex; align-items: center; justify-content: space-between;
  padding-bottom: 14px; border-bottom: 1px solid var(--line); margin-bottom: 18px;
}
.brand { display: flex; align-items: center; gap: 10px; }
.logo {
  width: 26px; height: 26px; border-radius: 6px;
  background: linear-gradient(135deg, var(--accent), #5B8DFF);
  box-shadow: 0 0 0 1px rgba(255,255,255,.16) inset;
}
.title { font-size: 24px; font-weight: 800; letter-spacing: .1px; }
.stamp { color: var(--muted); font-size: 13px; }
.insights { display: grid; gap: 12px; grid-template-columns: repeat(3, minmax(0,1fr)); margin-bottom: 16px; }
.insight-card {
  background: linear-gradient(180deg, rgba(255,255,255,.03), transparent), var(--panel);
  border: 1px solid var(--line); border-radius: 12px; padding: 14px 14px 12px;
}
.insight-label { font-size: 12px; color: var(--muted); margin-bottom: 6px; }
.insight-value { font-size: 28px; font-weight: 800; line-height: 1.1; }
.insight-sub { margin-top: 4px; color: var(--muted); font-size: 12px; }
.main-grid { display: grid; gap: 14px; grid-template-columns: minmax(0,1.7fr) minmax(0,1fr); }
.panel { background: var(--panel); border: 1px solid var(--line); border-radius: 12px; padding: 12px; }
.panel-h { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.panel-title { font-size: 15px; font-weight: 700; }
.filters { display: flex; gap: 6px; flex-wrap: wrap; }
.fbtn {
  border: 1px solid var(--line); background: var(--panel-soft); color: var(--text);
  border-radius: 8px; padding: 6px 10px; font-size: 12px; cursor: pointer;
}
.fbtn.active { border-color: var(--accent); color: #DDE8FF; }
#chart { height: 540px; }
.rank-wrap { display: grid; gap: 9px; }
.rank-card {
  background: var(--panel-soft); border: 1px solid var(--line); border-radius: 10px;
  padding: 10px; cursor: pointer;
}
.rank-card.active { border-color: var(--accent); box-shadow: 0 0 0 1px rgba(46,108,246,.28) inset; }
.rank-head { display: flex; align-items: center; gap: 8px; }
.rank-num { font-weight: 700; width: 18px; color: var(--muted); }
.party-dot { width: 10px; height: 10px; border-radius: 50%; }
.rank-party { font-weight: 700; font-size: 14px; }
.rank-main { margin-top: 4px; display: flex; align-items: baseline; justify-content: space-between; }
.rank-pred { font-size: 23px; font-weight: 800; letter-spacing: .2px; }
.rank-pred small { font-size: 12px; color: var(--muted); margin-left: 3px; }
.rank-delta { font-size: 13px; color: var(--muted); }
.rank-sub { font-size: 12px; color: var(--muted); margin-top: 2px; }
.rank-band { font-size: 12px; color: #C5D7F6; margin-top: 2px; }
.spark { margin-top: 6px; opacity: .9; }
.news { margin-top: 14px; }
.news-status { color: var(--muted); font-size: 12px; margin: 0 0 8px; }
.news-grid { display: grid; gap: 10px; grid-template-columns: repeat(3, minmax(0,1fr)); }
.news-card {
  background: var(--panel); border: 1px solid var(--line); border-radius: 10px;
  padding: 10px 11px; text-decoration: none; color: var(--text); display: block; min-height: 92px;
}
.news-card:hover { border-color: #3D5E8D; }
.news-date { color: var(--muted); font-size: 12px; margin-bottom: 6px; }
.news-title { font-size: 13px; line-height: 1.45; font-weight: 600; margin-bottom: 6px; }
.news-source { color: var(--muted); font-size: 12px; }
.method { margin-top: 14px; }
details { background: var(--panel); border: 1px solid var(--line); border-radius: 12px; padding: 12px 12px 8px; }
summary { cursor: pointer; font-weight: 700; margin-bottom: 8px; }
.method-p { color: var(--muted); line-height: 1.6; font-size: 14px; margin: 6px 0 12px; }
table { width: 100%; border-collapse: collapse; }
th, td { border-bottom: 1px solid var(--line); padding: 8px 6px; font-size: 13px; }
th { color: var(--muted); text-align: left; font-weight: 600; }
.wbar-wrap { display: inline-block; width: 180px; height: 8px; border-radius: 999px; background: #152E4F; margin-right: 8px; vertical-align: middle; }
.wbar { height: 100%; border-radius: 999px; background: linear-gradient(90deg, #2E6CF6, #76A2FF); }
.wlabel { color: var(--text); font-size: 12px; }
@media (max-width: 980px) {
  .insights { grid-template-columns: 1fr; }
  .main-grid { grid-template-columns: 1fr; }
  #chart { height: 440px; }
  .news-grid { grid-template-columns: 1fr; }
}
""".strip()

APP_JS = """
(function () {
  const dataEl = document.getElementById("poll-data");
  if (!dataEl) return;
  const payload = JSON.parse(dataEl.textContent);
  const tracesData = payload.traces || [];
  const chartDiv = document.getElementById("chart");
  if (!chartDiv) return;

  function buildTraces() {
    const out = [];
    tracesData.forEach((p) => {
      out.push({
        x: p.actual_x, y: p.actual_y, type: "scatter", mode: "lines", name: p.party,
        legendgroup: p.party, line: { color: p.color, width: 2.7 },
        hovertemplate: "<b>%{fullData.name}</b>: %{y:.2f}%<extra></extra>"
      });
      out.push({
        x: p.forecast_x, y: p.forecast_y, type: "scatter", mode: "lines",
        legendgroup: p.party, showlegend: false, line: { color: p.color, width: 2.2, dash: "dot" },
        hoverinfo: "skip"
      });
      out.push({
        x: [p.pred_x], y: [p.pred_y], type: "scatter", mode: "markers+text",
        legendgroup: p.party, showlegend: false,
        marker: { color: p.color, size: 10, line: { color: "#DDE8FF", width: 1 } },
        text: ["예측치"], textposition: "middle right", textfont: { color: p.color, size: 11 },
        customdata: [[p.pred_lo_80, p.pred_hi_80]],
        hovertemplate: "<b>%{fullData.legendgroup} 예측</b><br>%{y:.2f}%<br>80% 구간: %{customdata[0]:.2f}% ~ %{customdata[1]:.2f}%<extra></extra>"
      });
    });
    return out;
  }

  const layout = {
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(255,255,255,0.02)",
    font: { color: "#E6ECF5", family: "Inter, Pretendard, sans-serif" },
    margin: { l: 55, r: 20, t: 10, b: 44 },
    hovermode: "x unified",
    hoverlabel: {
      bgcolor: "#0B1F3A",
      bordercolor: "#8FB3FF",
      font: { color: "#F7FAFF", size: 14, family: "Inter, Pretendard, sans-serif" },
      align: "left",
      namelength: -1
    },
    xaxis: {
      gridcolor: "rgba(255,255,255,0.08)",
      linecolor: "rgba(255,255,255,0.12)",
      showspikes: true,
      spikemode: "across",
      spikecolor: "rgba(255,255,255,0.35)",
      spikedash: "dot",
      spikethickness: 1
    },
    yaxis: { title: "지지율(%)", gridcolor: "rgba(255,255,255,0.08)", zeroline: false },
    legend: { orientation: "h", y: 1.08, x: 0 }
  };

  Plotly.newPlot(chartDiv, buildTraces(), layout, { displayModeBar: false, responsive: true });

  const fbtns = [...document.querySelectorAll(".fbtn")];
  function setBtnActive(key) { fbtns.forEach((b) => b.classList.toggle("active", b.dataset.range === key)); }
  function endDate() {
    let d = null;
    tracesData.forEach((p) => {
      const t = new Date(p.pred_x);
      if (!d || t > d) d = t;
    });
    return d;
  }
  function dateShift(base, months) {
    const d = new Date(base);
    d.setMonth(d.getMonth() - months);
    return d;
  }

  fbtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      const key = btn.dataset.range;
      if (key === "reset") {
        const op = chartDiv.data.map(() => 1);
        Plotly.restyle(chartDiv, "opacity", op);
        document.querySelectorAll(".rank-card").forEach((c) => c.classList.remove("active"));
        return;
      }
      setBtnActive(key);
      const e = endDate();
      if (key === "all") {
        Plotly.relayout(chartDiv, { "xaxis.autorange": true });
        return;
      }
      const start = key === "3m" ? dateShift(e, 3) : (key === "6m" ? dateShift(e, 6) : dateShift(e, 12));
      Plotly.relayout(chartDiv, { "xaxis.range": [start, e] });
    });
  });

  const rankCards = [...document.querySelectorAll(".rank-card")];
  rankCards.forEach((card) => {
    card.addEventListener("click", () => {
      const party = card.dataset.party;
      const op = chartDiv.data.map((t) => (t.legendgroup === party ? 1 : 0.15));
      Plotly.restyle(chartDiv, "opacity", op);
      rankCards.forEach((c) => c.classList.toggle("active", c.dataset.party === party));
    });
  });

  function esc(s) {
    return String(s || "").replace(/[&<>"']/g, (ch) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;"
    }[ch]));
  }

  function parseRss(xmlText) {
    const doc = new DOMParser().parseFromString(xmlText, "text/xml");
    const items = [...doc.querySelectorAll("item")];
    const rows = items.map((it) => {
      const title = (it.querySelector("title")?.textContent || "").trim();
      const link = (it.querySelector("link")?.textContent || "").trim();
      const desc = (it.querySelector("description")?.textContent || "").trim();
      const pubDateRaw = (it.querySelector("pubDate")?.textContent || "").trim();
      const source = (it.querySelector("source")?.textContent || "Google News").trim();
      const dt = pubDateRaw ? new Date(pubDateRaw) : null;
      return {
        title,
        link,
        desc,
        source,
        date: dt && !isNaN(dt.getTime()) ? dt : null
      };
    }).filter((r) => r.title && r.link);
    rows.sort((a, b) => (b.date ? b.date.getTime() : 0) - (a.date ? a.date.getTime() : 0));
    return rows;
  }

  function stripHtml(s) {
    return String(s || "").replace(/<[^>]*>/g, " ");
  }

  async function fetchViaCandidates(rssUrl) {
    const candidates = [
      `https://api.allorigins.win/raw?url=${encodeURIComponent(rssUrl)}`,
      `https://api.allorigins.win/get?url=${encodeURIComponent(rssUrl)}`,
      `https://r.jina.ai/http://${rssUrl.replace(/^https?:\\/\\//, "")}`
    ];
    for (const u of candidates) {
      try {
        const res = await fetch(u, { cache: "no-store" });
        if (!res.ok) continue;
        const text = await res.text();
        if (!text) continue;
        if (u.includes("/get?url=")) {
          const j = JSON.parse(text);
          const contents = j && j.contents ? String(j.contents) : "";
          if (contents.includes("<item>")) return contents;
        } else if (text.includes("<item>")) {
          return text;
        }
      } catch (_) {}
    }
    return "";
  }

  async function fetchRecentPollNews() {
    const grid = document.getElementById("news-grid");
    const status = document.getElementById("news-status");
    if (!grid) return;

    const phrase = "중앙선거여론조사심의위원회";
    if (status) status.textContent = "기사 목록 불러오는 중...";

    // Primary: same-origin static JSON generated at build time.
    try {
      const local = await fetch("news_latest.json", { cache: "no-store" });
      if (local.ok) {
        const rows = await local.json();
        if (Array.isArray(rows) && rows.length) {
          grid.innerHTML = rows.slice(0, 6).map((r) => `
            <a class="news-card" href="${esc(r.url || "")}" target="_blank" rel="noopener noreferrer">
              <div class="news-date">${esc(r.date || "")}</div>
              <div class="news-title">${esc(r.title || "")}</div>
              <div class="news-source">${esc(r.source || "출처")}</div>
            </a>
          `).join("");
          if (status) status.textContent = `자동 갱신 완료 (${Math.min(rows.length, 6)}건)`;
          return;
        }
      }
    } catch (_) {}

    const debugProxy = new URLSearchParams(window.location.search).get("newsProxy") === "1";
    if (!debugProxy) {
      if (status) status.textContent = "빌드 시점 수집 데이터 표시 중";
      return;
    }

    // Debug-only fallback path (disabled by default)
    const qStrict = encodeURIComponent(`"${phrase}"`);
    const qBroad = encodeURIComponent(`${phrase} 여론조사`);
    const rssStrict = `https://news.google.com/rss/search?q=${qStrict}&hl=ko&gl=KR&ceid=KR:ko`;
    const rssBroad = `https://news.google.com/rss/search?q=${qBroad}&hl=ko&gl=KR&ceid=KR:ko`;
    let xmlText = await fetchViaCandidates(rssStrict);
    if (!xmlText) xmlText = await fetchViaCandidates(rssBroad);
    if (!xmlText) {
      if (status) status.textContent = "디버그 프록시 로딩 실패(정적 데이터 유지)";
      return;
    }
    const rows = parseRss(xmlText).filter((r) => stripHtml(r.title + " " + r.desc).includes(phrase)).slice(0, 6);
    if (!rows.length) {
      if (status) status.textContent = "디버그 프록시 결과 없음(정적 데이터 유지)";
      return;
    }
    grid.innerHTML = rows.map((r) => {
      const d = r.date ? r.date.toISOString().slice(0, 10) : "";
      return `<a class="news-card" href="${esc(r.link)}" target="_blank" rel="noopener noreferrer"><div class="news-date">${esc(d)}</div><div class="news-title">${esc(r.title)}</div><div class="news-source">${esc(r.source)}</div></a>`;
    }).join("");
    if (status) status.textContent = `디버그 프록시 갱신 (${rows.length}건)`;
  }

  fetchRecentPollNews();
})();
""".strip()


def canonical_party_name(name: str) -> str:
    s = str(name).strip().replace("  ", " ")
    for canonical, meta in PARTY_STYLES.items():
        for a in meta["aliases"]:
            if s == a:
                return canonical
    return s


def load_blended(outputs: Path) -> pd.DataFrame:
    p = outputs / "weighted_time_series.xlsx"
    if p.exists():
        return pd.read_excel(p, sheet_name="weighted_time_series")
    fallback = outputs / "weighted_poll_9_agencies_all_parties_2025_present.xlsx"
    if fallback.exists():
        return pd.read_excel(fallback, sheet_name="weighted_time_series")
    raise FileNotFoundError("No blended workbook found in outputs/")


def load_forecast(outputs: Path) -> pd.DataFrame:
    p = outputs / "forecast_next_week.xlsx"
    if p.exists():
        return pd.read_excel(p)
    fallback = outputs / "weighted_poll_forecast_next_week.xlsx"
    if fallback.exists():
        return pd.read_excel(fallback, sheet_name="forecast")
    raise FileNotFoundError("No forecast workbook found in outputs/")


def load_weights(base: Path, outputs: Path) -> pd.DataFrame:
    weights_csv = outputs / "weights.csv"
    if weights_csv.exists():
        w = pd.read_csv(weights_csv)
        if {"조사기관", "mae", "weight", "weight_pct"}.issubset(w.columns):
            return w.sort_values("weight", ascending=False).reset_index(drop=True)

    mae_path = base / "data" / "pollster_accuracy_clusters_2024_2025.xlsx"
    if not mae_path.exists():
        return pd.DataFrame(columns=["조사기관", "mae", "weight", "weight_pct"])
    m = pd.read_excel(mae_path, sheet_name=0)
    mae_col = next((c for c in m.columns if "MAE" in str(c).upper()), None)
    if mae_col is None or "조사기관" not in m.columns:
        return pd.DataFrame(columns=["조사기관", "mae", "weight", "weight_pct"])
    m = m[m["조사기관"].isin(POLLSTERS)].copy()
    m[mae_col] = pd.to_numeric(m[mae_col], errors="coerce")
    m = m.dropna(subset=[mae_col])
    m["weight"] = 1.0 / m[mae_col]
    m["weight"] = m["weight"] / m["weight"].sum()
    m["weight_pct"] = m["weight"] * 100.0
    out = m[["조사기관", mae_col, "weight", "weight_pct"]].rename(columns={mae_col: "mae"})
    return out.sort_values("weight", ascending=False).reset_index(drop=True)


def load_recent_articles(base: Path) -> pd.DataFrame:
    p = base / "data" / "recent_articles.csv"
    cols = ["date", "source", "title", "url"]
    if not p.exists():
        return pd.DataFrame(columns=cols)
    df = pd.read_csv(p)
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date", "title", "url"])
    return df.sort_values("date", ascending=False).head(12).reset_index(drop=True)


def fetch_google_news_articles(phrase: str = "중앙선거여론조사심의위원회", limit: int = 12) -> pd.DataFrame:
    def _fetch_xml(url: str) -> str:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read().decode("utf-8", "ignore")

    queries = [f'"{phrase}"', f"{phrase} 여론조사"]
    rows = []
    for q in queries:
        try:
            rss = (
                "https://news.google.com/rss/search?"
                f"q={urllib.parse.quote(q)}&hl=ko&gl=KR&ceid=KR:ko"
            )
            root = ET.fromstring(_fetch_xml(rss))
            for it in root.findall(".//item"):
                title = (it.findtext("title") or "").strip()
                link = (it.findtext("link") or "").strip()
                desc = (it.findtext("description") or "").strip()
                source = (it.findtext("source") or "Google News").strip()
                pub = (it.findtext("pubDate") or "").strip()
                if not title or not link:
                    continue
                if phrase not in f"{title} {desc}":
                    continue
                dt = None
                if pub:
                    try:
                        dt = parsedate_to_datetime(pub)
                    except Exception:
                        dt = None
                rows.append(
                    {
                        "date": (dt.date().isoformat() if dt is not None else ""),
                        "source": source,
                        "title": title,
                        "url": link,
                        "_dt": dt,
                    }
                )
            if rows:
                break
        except Exception:
            continue

    if not rows:
        return pd.DataFrame(columns=["date", "source", "title", "url"])
    out = pd.DataFrame(rows).drop_duplicates(subset=["url"]).copy()
    out = out.sort_values("_dt", ascending=False, na_position="last")
    out = out[["date", "source", "title", "url"]].head(limit).reset_index(drop=True)
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out = out.dropna(subset=["date", "title", "url"])
    return out


def resolve_news_articles(base: Path, outputs: Path) -> tuple[pd.DataFrame, str]:
    # Priority 1: build-time Google RSS fetch
    fetched_articles = fetch_google_news_articles()
    if not fetched_articles.empty:
        return fetched_articles, "google_rss"

    # Priority 2: issue intake output
    issue_news = outputs / "issue_news_latest.csv"
    if issue_news.exists():
        try:
            tmp = pd.read_csv(issue_news)
            tmp = tmp.rename(columns={"published": "date", "link": "url", "keyword": "source"})
            for c in ["date", "source", "title", "url"]:
                if c not in tmp.columns:
                    tmp[c] = ""
            tmp["date"] = pd.to_datetime(tmp["date"], errors="coerce")
            tmp = tmp.dropna(subset=["date", "title", "url"])[["date", "source", "title", "url"]]
            tmp = tmp.sort_values("date", ascending=False).head(12).reset_index(drop=True)
            if not tmp.empty:
                return tmp, "issue_news_latest_csv"
        except Exception:
            pass

    # Priority 3: manual fallback file
    return load_recent_articles(base), "recent_articles_csv"


def load_backtest_overall(outputs: Path) -> dict:
    p = outputs / "backtest_summary.csv"
    if not p.exists():
        return {}
    try:
        df = pd.read_csv(p)
    except Exception:
        return {}
    df = df[df.get("level", "") == "overall"].copy()
    if df.empty or "model" not in df.columns or "mae" not in df.columns:
        return {}
    out: dict[str, float] = {}
    for model in ["legacy", "ssm"]:
        r = df[df["model"] == model]
        if not r.empty:
            out[f"{model}_mae"] = float(pd.to_numeric(r.iloc[0]["mae"], errors="coerce"))
            out[f"{model}_rmse"] = float(pd.to_numeric(r.iloc[0].get("rmse"), errors="coerce"))
            out[f"{model}_n"] = int(pd.to_numeric(r.iloc[0].get("n"), errors="coerce"))
    if "legacy_mae" in out and "ssm_mae" in out and out["legacy_mae"] > 0:
        out["improvement_pct"] = (out["legacy_mae"] - out["ssm_mae"]) / out["legacy_mae"] * 100.0
    return out


def sparkline_svg(values: list[float], color: str) -> str:
    if not values:
        return ""
    w, h = 130, 28
    mn, mx = min(values), max(values)
    if mx - mn < 1e-9:
        mx = mn + 1.0
    pts = []
    for i, v in enumerate(values):
        x = i * (w / max(1, len(values) - 1))
        y = h - ((v - mn) / (mx - mn)) * h
        pts.append(f"{x:.2f},{y:.2f}")
    poly = " ".join(pts)
    return (
        f"<svg viewBox='0 0 {w} {h}' width='{w}' height='{h}' aria-hidden='true'>"
        f"<polyline fill='none' stroke='{color}' stroke-width='2' points='{poly}' />"
        "</svg>"
    )


def build_party_payload(blended: pd.DataFrame, forecast: pd.DataFrame) -> tuple[list[dict], list[dict]]:
    df = blended.copy()
    df["date_end"] = pd.to_datetime(df["date_end"])
    df = df.sort_values("date_end")
    df = df.rename(columns={c: canonical_party_name(c) for c in df.columns})

    fc = forecast.copy()
    fc["party"] = fc["party"].map(canonical_party_name)
    fc["next_week_pred"] = pd.to_numeric(fc["next_week_pred"], errors="coerce")
    fc["rmse"] = pd.to_numeric(fc.get("rmse"), errors="coerce")
    fc["pred_lo_80"] = pd.to_numeric(fc.get("pred_lo_80"), errors="coerce")
    fc["pred_hi_80"] = pd.to_numeric(fc.get("pred_hi_80"), errors="coerce")
    fc["pred_sd"] = pd.to_numeric(fc.get("pred_sd"), errors="coerce")
    fc = fc.dropna(subset=["next_week_pred"])

    pred_date = (pd.to_datetime(df["date_end"]).max() + pd.Timedelta(days=7)).strftime("%Y-%m-%d")
    traces: list[dict] = []
    ranking_rows: list[dict] = []

    for party in PARTY_ORDER:
        if party not in df.columns:
            continue
        color = PARTY_STYLES[party]["color"]
        s = pd.to_numeric(df[party], errors="coerce")
        valid = pd.DataFrame({"x": df["date_end"], "y": s}).dropna()
        if valid.empty:
            continue
        pred_row = fc[fc["party"] == party]
        if pred_row.empty:
            continue

        pred = float(pred_row.iloc[0]["next_week_pred"])
        rmse = float(pred_row.iloc[0]["rmse"]) if pd.notna(pred_row.iloc[0]["rmse"]) else None
        pred_lo_80 = float(pred_row.iloc[0]["pred_lo_80"]) if pd.notna(pred_row.iloc[0]["pred_lo_80"]) else None
        pred_hi_80 = float(pred_row.iloc[0]["pred_hi_80"]) if pd.notna(pred_row.iloc[0]["pred_hi_80"]) else None
        pred_sd = float(pred_row.iloc[0]["pred_sd"]) if pd.notna(pred_row.iloc[0]["pred_sd"]) else None
        last_actual = float(valid.iloc[-1]["y"])
        delta = pred - last_actual
        spark_vals = valid.iloc[-16:]["y"].tolist()

        traces.append(
            {
                "party": party,
                "color": color,
                "actual_x": [d.strftime("%Y-%m-%d") for d in valid["x"]],
                "actual_y": [float(v) for v in valid["y"]],
                "forecast_x": [valid.iloc[-1]["x"].strftime("%Y-%m-%d"), pred_date],
                "forecast_y": [last_actual, pred],
                "pred_x": pred_date,
                "pred_y": pred,
                "pred_lo_80": pred_lo_80 if pred_lo_80 is not None else pred,
                "pred_hi_80": pred_hi_80 if pred_hi_80 is not None else pred,
            }
        )
        ranking_rows.append(
            {
                "party": party,
                "color": color,
                "pred": pred,
                "rmse": rmse,
                "pred_lo_80": pred_lo_80,
                "pred_hi_80": pred_hi_80,
                "pred_sd": pred_sd,
                "delta": delta,
                "spark_svg": sparkline_svg(spark_vals, color),
            }
        )

    ranking_rows = sorted(ranking_rows, key=lambda x: x["pred"], reverse=True)
    return traces, ranking_rows


def render_html(
    docs_dir: Path,
    traces: list[dict],
    ranking_rows: list[dict],
    weights_df: pd.DataFrame,
    articles_df: pd.DataFrame,
    latest_date: str,
    backtest_overall: dict,
) -> None:
    now_kst = datetime.now(tz=ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S KST")
    cache_bust = datetime.now(tz=ZoneInfo("Asia/Seoul")).strftime("%Y%m%d%H%M%S")

    cards = []
    if len(ranking_rows) >= 2:
        lead = ranking_rows[0]
        second = ranking_rows[1]
        cards.append({"label": "1위 정당 / 격차", "value": f"{lead['party']}", "sub": f"{(lead['pred'] - second['pred']):.2f}%p"})
    swing = sum(abs(float(r["delta"])) for r in ranking_rows) / len(ranking_rows) if ranking_rows else 0.0
    cards.append({"label": "이번주 평균 변동폭", "value": f"{swing:.2f}%p", "sub": "예측치-직전실측"})
    rmse_vals = [r["rmse"] for r in ranking_rows if r["rmse"] is not None]
    rmse_avg = sum(rmse_vals) / len(rmse_vals) if rmse_vals else 0.0
    cards.append({"label": "예측 오차(RMSE)", "value": f"{rmse_avg:.2f}", "sub": "정당 평균"})
    if backtest_overall.get("improvement_pct") is not None:
        cards.append(
            {
                "label": "백테스트 MAE 개선",
                "value": f"{float(backtest_overall['improvement_pct']):+.1f}%",
                "sub": "legacy 대비 ssm",
            }
        )

    cards_html = "".join(
        f"""
        <article class=\"insight-card\">
          <div class=\"insight-label\">{c['label']}</div>
          <div class=\"insight-value\">{c['value']}</div>
          <div class=\"insight-sub\">{c['sub']}</div>
        </article>
        """
        for c in cards
    )

    ranking_html = []
    for i, r in enumerate(ranking_rows, 1):
        sign = "▲" if r["delta"] > 0 else ("▼" if r["delta"] < 0 else "■")
        delta_txt = f"{sign} {abs(r['delta']):.2f}"
        rmse_txt = f"{r['rmse']:.2f}" if r["rmse"] is not None else "-"
        band_txt = (
            f"80% 구간 {r['pred_lo_80']:.2f}% ~ {r['pred_hi_80']:.2f}%"
            if r["pred_lo_80"] is not None and r["pred_hi_80"] is not None
            else "80% 구간 -"
        )
        ranking_html.append(
            f"""
            <article class=\"rank-card\" data-party=\"{r['party']}\">
              <div class=\"rank-head\">
                <div class=\"rank-num\">{i}.</div>
                <div class=\"party-dot\" style=\"background:{r['color']}\"></div>
                <div class=\"rank-party\">{r['party']}</div>
              </div>
              <div class=\"rank-main\">
                <span class=\"rank-pred\">{r['pred']:.2f}<small>%</small></span>
                <span class=\"rank-delta\">{delta_txt}</span>
              </div>
              <div class=\"rank-sub\">RMSE {rmse_txt}</div>
              <div class=\"rank-band\">{band_txt}</div>
              <div class=\"spark\">{r['spark_svg']}</div>
            </article>
            """
        )

    article_cards = []
    for _, a in articles_df.iterrows():
        d = pd.to_datetime(a["date"]).strftime("%Y-%m-%d")
        source = str(a.get("source", "")).strip() or "출처"
        title = str(a.get("title", "")).strip()
        url = str(a.get("url", "")).strip()
        article_cards.append(
            f"""
            <a class=\"news-card\" href=\"{url}\" target=\"_blank\" rel=\"noopener noreferrer\">
              <div class=\"news-date\">{d}</div>
              <div class=\"news-title\">{title}</div>
              <div class=\"news-source\">{source}</div>
            </a>
            """
        )

    weight_rows = []
    for _, r in weights_df.iterrows():
        agency = str(r.get("조사기관", ""))
        mae = pd.to_numeric(r.get("mae"), errors="coerce")
        w_pct = pd.to_numeric(r.get("weight_pct"), errors="coerce")
        mae_txt = f"{float(mae):.3f}" if pd.notna(mae) else "-"
        wp = float(w_pct) if pd.notna(w_pct) else 0.0
        weight_rows.append(
            f"""
            <tr>
              <td>{agency}</td>
              <td>{mae_txt}</td>
              <td>
                <div class=\"wbar-wrap\"><div class=\"wbar\" style=\"width:{wp:.2f}%\"></div></div>
                <span class=\"wlabel\">{wp:.2f}%</span>
              </td>
            </tr>
            """
        )

    payload_json = json.dumps({"traces": traces}, ensure_ascii=False)
    backtest_note = ""
    if backtest_overall:
        legacy_mae = backtest_overall.get("legacy_mae")
        ssm_mae = backtest_overall.get("ssm_mae")
        improve = backtest_overall.get("improvement_pct")
        if legacy_mae is not None and ssm_mae is not None and improve is not None:
            backtest_note = (
                f"최근 롤링 백테스트 기준 MAE는 legacy {legacy_mae:.3f}, "
                f"ssm {ssm_mae:.3f}이며 개선율은 {improve:+.2f}%입니다."
            )
    html = f"""<!doctype html>
<html lang=\"ko\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Weekly Korean Poll Tracker</title>
  <link rel=\"preconnect\" href=\"https://fonts.googleapis.com\" />
  <link rel=\"preconnect\" href=\"https://fonts.gstatic.com\" crossorigin />
  <link href=\"https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Pretendard:wght@400;500;600;700&display=swap\" rel=\"stylesheet\" />
  <link rel=\"stylesheet\" href=\"style.css?v={cache_bust}\" />
  <script src=\"https://cdn.plot.ly/plotly-2.35.2.min.js\"></script>
</head>
<body>
  <div class=\"wrap\">
    <header class=\"top\">
      <div class=\"brand\"><div class=\"logo\" aria-hidden=\"true\"></div><div class=\"title\">Weekly Korean Poll Tracker</div></div>
      <div class=\"stamp\">최근 조사 반영일 {latest_date} | 페이지 갱신 {now_kst}</div>
    </header>

    <section class=\"insights\">{cards_html}</section>

    <section class=\"main-grid\">
      <article class=\"panel\">
        <div class=\"panel-h\">
          <div class=\"panel-title\">정당 지지율 추세 + 다음주 예측치</div>
          <div class=\"filters\">
            <button class=\"fbtn active\" data-range=\"3m\">3M</button>
            <button class=\"fbtn\" data-range=\"6m\">6M</button>
            <button class=\"fbtn\" data-range=\"1y\">1Y</button>
            <button class=\"fbtn\" data-range=\"all\">All</button>
            <button class=\"fbtn\" data-range=\"reset\">정당 강조 해제</button>
          </div>
        </div>
        <div id=\"chart\"></div>
      </article>
      <aside class=\"panel\"><div class=\"panel-title\" style=\"margin-bottom:8px;\">예측 랭킹</div><div class=\"rank-wrap\">{''.join(ranking_html)}</div></aside>
    </section>

    <section class=\"news\"><div class=\"panel-title\" style=\"margin: 0 0 8px;\">최근 여론조사 기사 링크</div><div id=\"news-status\" class=\"news-status\">대기 중...</div><div id=\"news-grid\" class=\"news-grid\">{''.join(article_cards)}</div></section>

    <section class=\"method\">
      <details>
        <summary>방법론 (클릭하여 펼치기)</summary>
        <p class=\"method-p\">2023년부터 2025년 6월 선거까지, 여론조사기관의 정당지지율과 실제 선거결과를 비교해 정확도(MAE)를 산출했습니다. 이후 정확도 상위 클러스터(9개 기관)만 사용해 합성 시계열을 만들고, 기관별 가중치는 1/MAE를 정규화해 적용합니다. 주간 업데이트에서는 Huber 손실 기반으로 가중치 안정성을 유지하도록 설계했습니다.</p>
        <p class=\"method-p\">{backtest_note}</p>
        <table><thead><tr><th>조사기관</th><th>MAE</th><th>가중치(%)</th></tr></thead><tbody>{''.join(weight_rows)}</tbody></table>
      </details>
    </section>
  </div>

  <script id=\"poll-data\" type=\"application/json\">{payload_json}</script>
  <script src=\"app.js?v={cache_bust}\"></script>
</body>
</html>
"""
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / "index.html").write_text(html, encoding="utf-8")
    (docs_dir / "style.css").write_text(STYLE_CSS + "\n", encoding="utf-8")
    (docs_dir / "app.js").write_text(APP_JS + "\n", encoding="utf-8")
    news_payload = []
    for _, a in articles_df.head(12).iterrows():
        news_payload.append(
            {
                "date": pd.to_datetime(a["date"]).strftime("%Y-%m-%d"),
                "source": str(a.get("source", "")),
                "title": str(a.get("title", "")),
                "url": str(a.get("url", "")),
            }
        )
    (docs_dir / "news_latest.json").write_text(
        json.dumps(news_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main():
    base = Path(".")
    outputs = base / "outputs"
    docs = base / "docs"

    blended = load_blended(outputs)
    forecast = load_forecast(outputs)
    weights = load_weights(base, outputs)
    articles, news_source = resolve_news_articles(base, outputs)
    backtest_overall = load_backtest_overall(outputs)
    traces, ranking_rows = build_party_payload(blended, forecast)

    latest_date = str(pd.to_datetime(blended["date_end"]).max().date())
    render_html(
        docs,
        traces,
        ranking_rows,
        weights,
        articles,
        latest_date=latest_date,
        backtest_overall=backtest_overall,
    )
    print(f"News source: {news_source}, rows={len(articles)}")
    print("Wrote docs/index.html, docs/style.css, docs/app.js")


if __name__ == "__main__":
    main()
