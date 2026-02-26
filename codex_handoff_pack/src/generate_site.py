from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
import feedparser
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
RENAME_EFFECTIVE_KST = datetime(2026, 3, 1, 0, 0, 0, tzinfo=ZoneInfo("Asia/Seoul"))
NEW_PPP_NAME_PLACEHOLDER = "새 정당명(미공개)"
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
POLLSTER_COLOR_MAP = {
    "리얼미터": "#EF4444",
    "한국갤럽": "#2563EB",
    "갤럽": "#2563EB",
    "한국리서치": "#0EA5A4",
    "코리아리서치인터내셔널": "#8B5CF6",
    "코리아리서치": "#8B5CF6",
    "리서치앤리서치": "#14B8A6",
    "엠브레인퍼블릭": "#F59E0B",
    "리서치뷰": "#EC4899",
    "에이스리서치": "#22C55E",
    "조원씨앤아이": "#6366F1",
    "알앤써치": "#06B6D4",
    "천지일보": "#D946EF",
    "JTBC": "#0F172A",
}
POLLSTER_COLOR_FALLBACK = "#64748B"

STYLE_CSS = """
/* TOKENS */
:root {
  --font-sans: ui-sans-serif, system-ui, -apple-system, "SF Pro Display", "Apple SD Gothic Neo", "Noto Sans KR", "Inter", "Segoe UI", Roboto, Arial, sans-serif;
  --bg: 15 17 21;
  --surface: 21 24 33;
  --surface-2: 28 33 48;
  --border: 255 255 255;
  --text: 245 247 250;
  --muted: 161 167 179;
  --muted-2: 107 114 128;
  --accent-1: 37 99 235;
  --accent-2: 59 130 246;
  --accent-3: 148 163 184;
  --success: 16 185 129;
  --danger: 239 68 68;
  --warning: 245 158 11;
  --r-sm: 8px;
  --r-md: 12px;
  --r-lg: 16px;
  --shadow-1: 0 8px 24px rgba(2, 6, 23, 0.22);
  --shadow-2: 0 8px 24px rgba(2, 6, 23, 0.22);
  --s-1: 4px;
  --s-2: 8px;
  --s-3: 12px;
  --s-4: 16px;
  --s-5: 20px;
  --s-6: 24px;
  --s-7: 32px;
  --s-8: 40px;
  --s-9: 48px;
  --s-10: 64px;
  --fs-0: 12px;
  --fs-1: 14px;
  --fs-2: 16px;
  --fs-3: 18px;
  --fs-4: 22px;
  --fs-5: 28px;
  --fs-6: 36px;
  --lh-tight: 1.15;
  --lh-snug: 1.3;
  --lh-normal: 1.55;
  --focus: 0 0 0 3px rgba(59, 130, 246, 0.28);

  --panel: rgb(var(--surface));
  --panel-soft: rgb(var(--surface-2));
  --line: rgba(var(--border), 0.08);
  --line-strong: rgba(var(--accent-2), 0.45);
  --accent: rgb(var(--accent-2));
}
html[data-theme="light"] {
  --bg: 246 247 249;
  --surface: 255 255 255;
  --surface-2: 251 251 252;
  --border: 232 232 236;
  --text: 17 17 17;
  --muted: 107 111 118;
  --muted-2: 154 160 166;
  --accent-1: 37 99 235;
  --accent-2: 59 130 246;
  --accent-3: 100 116 139;
  --shadow-1: 0 6px 16px rgba(2, 6, 23, 0.06);
  --shadow-2: 0 6px 16px rgba(2, 6, 23, 0.06);
  --line: rgba(var(--border), 0.95);
}
@media (prefers-color-scheme: light) {
  html:not([data-theme]) {
    --bg: 246 247 249;
    --surface: 255 255 255;
    --surface-2: 251 251 252;
    --border: 232 232 236;
    --text: 17 17 17;
    --muted: 107 111 118;
    --muted-2: 154 160 166;
    --accent-1: 37 99 235;
    --accent-2: 59 130 246;
    --accent-3: 100 116 139;
    --shadow-1: 0 6px 16px rgba(2, 6, 23, 0.06);
    --shadow-2: 0 6px 16px rgba(2, 6, 23, 0.06);
    --line: rgba(var(--border), 0.95);
  }
}
html[data-theme="light"] { color-scheme: light; }
html[data-theme="dark"] { color-scheme: dark; }

/* GLOBALS */
* { box-sizing: border-box; }
html, body { height: 100%; }
body {
  margin: 0;
  font-family: var(--font-sans);
  color: rgb(var(--text));
  background: rgb(var(--bg));
  font-feature-settings: "tnum" 1, "lnum" 1;
}
.app-bg {
  min-height: 100%;
  background: rgb(var(--bg));
}
.container {
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 var(--s-6);
}
.wrap { padding-bottom: var(--s-10); }
.section { padding: var(--s-9) 0; }
.section-tight { padding: var(--s-7) 0; }
.h1 {
  font-size: var(--fs-6);
  line-height: var(--lh-tight);
  letter-spacing: -0.02em;
  font-weight: 750;
}
.h3 {
  font-size: var(--fs-4);
  line-height: var(--lh-snug);
  letter-spacing: -0.01em;
  font-weight: 680;
}
.p {
  font-size: var(--fs-2);
  line-height: var(--lh-normal);
  color: rgb(var(--muted));
}
::selection { background: rgba(var(--accent-1), 0.35); }
:focus-visible {
  outline: none;
  box-shadow: var(--focus);
  border-radius: 12px;
}

/* COMPONENTS */
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--s-2);
  border-radius: var(--r-md);
  border: 1px solid var(--line);
  background: var(--panel);
  color: rgb(var(--text));
  font-weight: 600;
  cursor: pointer;
  transition: transform 120ms ease, background 160ms ease, border-color 160ms ease;
}
.btn:hover { transform: translateY(-1px); border-color: var(--line-strong); background: var(--panel-soft); }
.btn:active { transform: translateY(0); }
.btn:disabled { opacity: .5; cursor: not-allowed; }
.btn-sm { padding: 8px 12px; font-size: var(--fs-1); min-height: 36px; }
.btn.primary {
  color: #fff;
  border-color: rgba(var(--accent-1), .95);
  background: rgb(var(--accent-1));
}
.btn.primary:hover { background: rgb(var(--accent-2)); border-color: rgba(var(--accent-2), .95); }
.btn.ghost { background: transparent; border-color: var(--line); }
.btn.soft { background: var(--panel-soft); border-color: var(--line); }

.card, .panel {
  border-radius: var(--r-lg);
  border: 1px solid var(--line);
  background: var(--panel);
  box-shadow: var(--shadow-1);
  padding: var(--s-5);
}
.card-header { padding-bottom: var(--s-4); border-bottom: 1px solid var(--line); margin-bottom: var(--s-4); }
.card-body { padding: 0; }
.accent-line {
  height: 2px;
  border-radius: 999px;
  background: rgba(var(--accent-2), .75);
  opacity: .85;
  margin-bottom: var(--s-4);
}
.chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.05);
  color: rgb(var(--text));
  font-size: var(--fs-1);
  font-weight: 620;
}
.input {
  width: 100%;
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.04);
  color: rgb(var(--text));
  font-size: var(--fs-2);
}
.table, table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  overflow: hidden;
  border-radius: var(--r-lg);
  border: 1px solid var(--line);
  background: rgb(var(--bg));
}
th, td {
  padding: 14px 14px;
  text-align: left;
  border-bottom: 1px solid var(--line);
  font-size: var(--fs-1);
  line-height: 1.5;
}
th {
  font-size: var(--fs-0);
  color: rgb(var(--muted));
  font-weight: 650;
  background: rgb(var(--surface));
}
tbody tr:nth-child(odd) td { background: rgb(var(--bg)); }
tbody tr:hover td { background: rgb(var(--surface)); }
tbody tr:last-child td { border-bottom: none; }

.top {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  grid-template-rows: auto auto;
  gap: var(--s-4);
  align-items: center;
  padding: var(--s-7) 0 var(--s-4);
  border-bottom: 1px solid var(--line);
}
.brand { display: flex; align-items: center; gap: 12px; }
.logo {
  width: 30px;
  height: 30px;
  border-radius: 9px;
  background: rgb(var(--accent-1));
  box-shadow: 0 0 0 1px rgba(var(--accent-1), .35) inset;
}
.title { font-size: var(--fs-4); font-weight: 760; letter-spacing: -0.01em; }
.top-meta { display: flex; align-items: center; gap: var(--s-2); justify-content: flex-end; flex-wrap: wrap; }
.time-banner-row { grid-column: 1 / -1; display: flex; justify-content: center; }
.time-banner {
  width: min(100%, 760px);
  text-align: center;
  font-size: var(--fs-1);
  font-weight: 700;
  padding: 10px 16px;
  border-radius: var(--r-md);
  color: rgb(var(--text));
  border: 1px solid var(--line);
  background: rgb(var(--surface-2));
}
.freshness-badge,
.status-badge {
  font-size: 12px;
  font-weight: 700;
  border-radius: 999px;
  border: 1px solid transparent;
  padding: 7px 11px;
}
.freshness-badge.fresh, .status-badge.fresh {
  color: rgb(var(--success));
  border-color: rgba(var(--success), .45);
  background: rgba(var(--success), .18);
}
.freshness-badge.stale, .status-badge.stale {
  color: #ffa84f;
  border-color: rgba(255, 150, 64, .78);
  background: rgba(255, 120, 40, .3);
}
.freshness-badge.old, .status-badge.old {
  color: #ff7b7b;
  border-color: rgba(255, 88, 88, .82);
  background: rgba(255, 56, 56, .28);
}
.theme-toggle {
  display: inline-flex;
  gap: 4px;
  padding: 4px;
  background: rgb(var(--surface));
  border: 1px solid var(--line);
  border-radius: var(--r-md);
}
.theme-btn {
  border: 0;
  background: transparent;
  color: rgb(var(--muted));
  font-size: 12px;
  font-weight: 700;
  border-radius: var(--r-sm);
  padding: 6px 9px;
  cursor: pointer;
}
.theme-btn.active {
  color: rgb(var(--text));
  background: rgb(var(--bg));
  box-shadow: inset 0 0 0 1px var(--line);
}

.insights {
  display: grid;
  gap: var(--s-5);
}
.insights > .panel-title { margin: 0; }
.insights-cards {
  display: grid;
  gap: var(--s-5);
  grid-template-columns: repeat(4, minmax(0, 1fr));
}
.insight-card {
  border-radius: var(--r-md);
  border: 1px solid var(--line);
  padding: var(--s-5);
  min-height: 196px;
  background: rgb(var(--surface));
  transition: transform 160ms ease, box-shadow 160ms ease, border-color 160ms ease;
}
.insight-card:hover { transform: translateY(-2px); box-shadow: var(--shadow-1); }
.insight-card.featured {
  border-color: rgba(var(--accent-2), .45);
  background: rgb(var(--surface));
}
.insight-card.hero {
  border-color: rgba(var(--accent-2), .8);
  background: linear-gradient(140deg, rgba(var(--accent-1), .18), rgba(var(--surface), 1) 58%);
  box-shadow: inset 0 0 0 1px rgba(var(--accent-2), .28), var(--shadow-1);
}
.insight-label { font-size: var(--fs-0); color: rgb(var(--muted)); margin-bottom: 6px; }
.insight-value {
  font-size: clamp(2rem, 2.7vw, 2.75rem);
  font-weight: 800;
  line-height: 1.08;
  letter-spacing: -0.02em;
  word-break: keep-all;
}
.insight-value.textual {
  font-size: clamp(1.95rem, 2.45vw, 2.5rem);
  line-height: 1.04;
}
.insight-value small { font-size: var(--fs-0); color: rgb(var(--muted)); font-weight: 700; margin-left: 4px; }
.insight-sub { margin-top: 8px; color: rgb(var(--muted)); font-size: var(--fs-0); line-height: 1.5; }
.metric-tooltip {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  margin-left: 4px;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.18);
  background: rgba(255, 255, 255, 0.08);
  color: rgb(var(--muted));
  font-size: 10px;
  font-weight: 800;
  cursor: help;
}
.metric-tooltip::after {
  content: attr(data-tip);
  position: absolute;
  left: 50%;
  bottom: calc(100% + 8px);
  transform: translateX(-50%);
  width: 230px;
  opacity: 0;
  pointer-events: none;
  background: rgb(var(--text));
  color: rgb(var(--surface));
  border-radius: 8px;
  padding: 7px 9px;
  font-size: 11px;
  line-height: 1.35;
  transition: opacity .16s ease;
  z-index: 20;
}
.metric-tooltip:hover::after,
.metric-tooltip:focus-visible::after { opacity: 1; }

.main-grid { display: grid; gap: var(--s-4); grid-template-columns: minmax(0, 1.72fr) minmax(0, 1fr); align-items: stretch; }
.results-grid { display: grid; gap: var(--s-4); grid-template-columns: minmax(0, 1fr); align-items: start; }
.chart-panel { display: flex; flex-direction: column; min-height: 100%; }
.panel-h { display: grid; gap: var(--s-2); margin-bottom: var(--s-2); }
.panel-title-wrap { display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap; }
.panel-title { font-size: var(--fs-2); font-weight: 780; letter-spacing: .02em; }
.panel-title small { color: rgb(var(--muted)); font-size: var(--fs-0); font-weight: 600; margin-left: 6px; }
.panel-help {
  border: 1px solid var(--line);
  background: rgb(var(--surface));
  color: rgb(var(--muted));
  border-radius: var(--r-sm);
  min-width: 24px;
  min-height: 24px;
  cursor: help;
}
.filters { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.range-group { display: inline-flex; gap: 6px; padding: 4px; border: 1px solid var(--line); border-radius: var(--r-md); background: rgb(var(--surface)); }
.toggle-group { display: inline-flex; align-items: center; gap: 6px; }
.fbtn {
  border: 1px solid var(--line);
  background: rgb(var(--surface));
  color: rgb(var(--text));
  border-radius: var(--r-md);
  padding: 8px 12px;
  min-height: 36px;
  font-size: var(--fs-1);
  font-weight: 650;
  cursor: pointer;
  transition: transform 120ms ease, background 160ms ease, border-color 160ms ease;
}
.fbtn:hover { transform: translateY(-1px); border-color: var(--line-strong); background: rgb(var(--surface-2)); }
.fbtn.active {
  border-color: rgba(var(--accent-1), .9);
  background: rgb(var(--accent-1));
  color: #fff;
  box-shadow: none;
}
.range-group .fbtn:not(.active) { color: rgb(var(--muted)); background: transparent; border-color: var(--line); }
#chart { height: 640px; }
.chart-caption {
  margin-top: var(--s-2);
  color: rgb(var(--text));
  background: rgb(var(--surface-2));
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  padding: 10px 12px;
  font-size: var(--fs-0);
  line-height: 1.55;
}
.disclosure-note {
  margin-top: var(--s-2);
  font-size: var(--fs-0);
  color: rgb(var(--muted));
  line-height: 1.55;
}
.chart-legend-note { margin: 0 0 8px; display: flex; gap: 8px; flex-wrap: wrap; }
.legend-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: var(--fs-0);
  color: rgb(var(--muted));
  padding: 5px 9px;
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  background: rgb(var(--surface));
}
.dot-open, .dot-diamond { width: 12px; height: 12px; display: inline-block; }
.dot-open { border: 2px solid rgb(var(--muted)); border-radius: 50%; }
.dot-diamond { transform: rotate(45deg); border: 2px solid rgb(var(--muted)); }

.rank-wrap { display: grid; gap: 9px; }
.rank-card {
  background: rgb(var(--surface-2));
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  padding: 12px;
  cursor: pointer;
  min-height: 124px;
  transition: transform 160ms ease, box-shadow 160ms ease, border-color 160ms ease, opacity 160ms ease;
}
.rank-card:hover { transform: translateY(-2px); box-shadow: var(--shadow-1); }
.rank-card.active { border-color: rgba(var(--accent-2), .9); box-shadow: inset 0 0 0 1px rgba(var(--accent-2), .26); }
.rank-card.muted { opacity: .5; }
.rank-head { display: flex; align-items: center; gap: 8px; }
.rank-num { font-weight: 700; width: 20px; color: rgb(var(--muted)); }
.party-dot { width: 10px; height: 10px; border-radius: 50%; }
.rank-party { font-weight: 700; font-size: var(--fs-1); }
.rank-main { margin-top: 4px; display: flex; align-items: baseline; justify-content: space-between; }
.rank-pred { font-size: 24px; font-weight: 800; letter-spacing: .2px; }
.rank-pred small { font-size: var(--fs-0); color: rgb(var(--muted)); margin-left: 3px; }
.rank-delta, .rank-sub, .rank-band { font-size: var(--fs-0); color: rgb(var(--muted)); }
.spark { margin-top: 8px; opacity: 1; }

.section-title-row { display: flex; align-items: center; justify-content: space-between; margin: 0 0 10px; gap: var(--s-2); }
.news-grid { display: grid; gap: 12px; grid-template-columns: repeat(2, minmax(0, 1fr)); }
.news-card {
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  padding: 14px;
  text-decoration: none;
  color: rgb(var(--text));
  display: block;
  min-height: 110px;
  background: rgb(var(--surface));
  transition: border-color 160ms ease, background 160ms ease, transform 160ms ease;
}
.news-card + .news-card { border-top: 1px solid var(--line); }
.news-card:hover { border-color: var(--line-strong); background: rgb(var(--surface-2)); transform: translateY(-2px); }
.news-date { color: rgb(var(--muted)); font-size: var(--fs-0); margin-bottom: 5px; font-weight: 600; }
.news-title { font-size: var(--fs-1); line-height: 1.45; font-weight: 700; margin-bottom: 8px; padding-bottom: 8px; border-bottom: 1px solid var(--line); }
.news-source { color: rgb(var(--text)); font-size: var(--fs-0); font-weight: 600; opacity: .85; }

.latest-poll-grid { display: grid; gap: 12px; grid-template-columns: minmax(0, 1.2fr) minmax(0, 1fr); }
.latest-poll-list, .poll-compare-list { display: grid; gap: 8px; }
#latest-poll-chart, #poll-compare-chart { height: 320px; }
.latest-poll-card, .poll-compare-card {
  background: rgb(var(--surface));
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 10px;
}
.latest-poll-head, .poll-compare-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
}
.latest-poll-source { display: inline-block; margin-top: 6px; }
.latest-poll-pollster, .poll-compare-party { font-size: var(--fs-1); font-weight: 700; }
.latest-poll-date, .poll-compare-meta { color: rgb(var(--muted)); font-size: var(--fs-0); }
.latest-poll-values { color: rgb(var(--text)); font-size: var(--fs-0); line-height: 1.6; }
.poll-compare-grid { display: grid; gap: 12px; grid-template-columns: minmax(0, 1.1fr) minmax(0, 1fr); }
.poll-compare-delta { font-size: 13px; font-weight: 700; }

.link-out, .ext-link, a.latest-poll-source, td a {
  color: rgb(var(--accent-1));
  font-size: 12px;
  font-weight: 700;
  text-decoration: underline;
  text-decoration-thickness: 1.5px;
  text-underline-offset: 2px;
  transition: color .15s ease;
}
.link-out::after, .ext-link::after, a.latest-poll-source::after, td a::after { content: " ↗"; font-size: 11px; }
.link-out:hover, .ext-link:hover, a.latest-poll-source:hover, td a:hover { color: rgb(var(--accent-2)); }

.pollster-chip {
  display: inline-block;
  width: 9px;
  height: 9px;
  border-radius: 50%;
  margin-right: 6px;
  vertical-align: middle;
}
.method { margin-top: 24px; }
#section-news { margin-top: var(--s-6); }
details { border: 1px solid var(--line); border-radius: var(--r-md); padding: 12px 12px 8px; background: rgb(var(--surface)); }
summary { cursor: pointer; font-weight: 700; margin-bottom: 8px; }
.method-p { color: rgb(var(--muted)); line-height: 1.6; font-size: var(--fs-1); margin: 6px 0 12px; }
.wbar-wrap { display: inline-block; width: 180px; height: 8px; border-radius: 999px; background: rgb(var(--surface-2)); margin-right: 8px; vertical-align: middle; }
.wbar { height: 100%; border-radius: 999px; background: rgb(var(--accent-1)); }
.wlabel { color: rgb(var(--text)); font-size: 12px; }
.table-scroll {
  max-height: 360px;
  overflow: auto;
  border: 1px solid var(--line);
  border-radius: var(--r-lg);
}
.table-scroll .table,
.table-scroll table {
  border: 0;
  border-radius: 0;
}
.sr-only {
  position: absolute !important;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  border: 0;
}

@media (max-width: 980px) {
  .container { padding: 0 var(--s-4); }
  .top { grid-template-columns: 1fr; grid-template-rows: auto auto auto; }
  .top-meta { justify-content: flex-start; }
  .insights-cards { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--s-4); }
  .main-grid, .latest-poll-grid, .poll-compare-grid, .results-grid { grid-template-columns: 1fr; }
  .filters { width: 100%; display: grid; grid-template-columns: 1fr; }
  .range-group { width: 100%; overflow-x: auto; }
  .toggle-group { width: 100%; justify-content: flex-start; flex-wrap: wrap; }
  #chart { height: 440px; }
  .news-grid { grid-template-columns: 1fr; gap: var(--s-3); }
  #latest-poll-chart, #poll-compare-chart { height: 280px; }
}
@media (max-width: 768px) {
  .insights-cards { grid-template-columns: 1fr; }
  .title { font-size: 22px; }
  .time-banner { width: 100%; font-size: 13px; padding: 9px 11px; }
  th, td { font-size: 13px; padding: 10px; }
  .news-title { font-size: 13px; }
}
""".strip()

APP_JS = """
(function () {
  const THEME_STORAGE_KEY = "wk_poll_theme_mode";

  function getThemeMode() {
    const v = localStorage.getItem(THEME_STORAGE_KEY);
    if (v === "light" || v === "dark" || v === "system") return v;
    return "system";
  }

  function applyTheme(mode) {
    const root = document.documentElement;
    if (mode === "system") {
      root.removeAttribute("data-theme");
    } else {
      root.setAttribute("data-theme", mode);
    }
    localStorage.setItem(THEME_STORAGE_KEY, mode);
    document.querySelectorAll(".theme-btn").forEach((btn) => {
      const active = btn.dataset.theme === mode;
      btn.classList.toggle("active", active);
      btn.setAttribute("aria-pressed", active ? "true" : "false");
    });
  }

  function initThemeToggle() {
    const mode = getThemeMode();
    applyTheme(mode);
    document.querySelectorAll(".theme-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const next = btn.dataset.theme || "system";
        applyTheme(next);
        const chart = document.getElementById("chart");
        if (chart && window.Plotly && chart.data) {
          Plotly.react(chart, chart.data, buildLayout(), {
            displayModeBar: false,
            responsive: true,
            scrollZoom: false,
            doubleClick: false
          });
        }
      });
    });
  }

  function daysBetween(a, b) {
    const ms = b.getTime() - a.getTime();
    if (!Number.isFinite(ms)) return null;
    return Math.floor(ms / 86400000);
  }

  function updateFreshnessBadge() {
    const badge = document.getElementById("freshness-badge");
    const stamp = document.getElementById("stamp");
    if (!badge || !stamp) return;
    const latestRaw = stamp.dataset.latestDate || "";
    const updatedRaw = stamp.dataset.updatedAt || "";
    const latest = latestRaw ? new Date(`${latestRaw}T00:00:00+09:00`) : null;
    const updated = updatedRaw ? new Date(updatedRaw) : null;
    if (!latest || Number.isNaN(latest.getTime()) || !updated || Number.isNaN(updated.getTime())) {
      badge.textContent = "최신성 확인 불가";
      badge.className = "freshness-badge stale";
      return;
    }
    const diff = daysBetween(latest, updated);
    if (diff === null) return;
    if (diff < 0) {
      badge.className = "freshness-badge old";
      badge.textContent = `반영일이 갱신시각보다 미래 (${Math.abs(diff)}일)`;
    } else if (diff <= 3) {
      badge.className = "freshness-badge fresh";
      badge.textContent = `데이터 최신성 높음 · ${diff}일 차`;
    } else if (diff <= 10) {
      badge.className = "freshness-badge stale";
      badge.textContent = `데이터 시차 ${diff}일`;
    } else {
      badge.className = "freshness-badge old";
      badge.textContent = `데이터 시차 큼 · ${diff}일`;
    }
  }

  initThemeToggle();
  updateFreshnessBadge();

  const dataEl = document.getElementById("poll-data");
  if (!dataEl) return;
  const payload = JSON.parse(dataEl.textContent);
  const tracesData = payload.traces || [];
  const presidentRaw = payload.president_raw || {};
  const latestPollResults = payload.latest_poll_results || [];
  const pollsterColorMap = payload.pollster_color_map || {};
  const partyColorMap = {};
  tracesData.forEach((t) => {
    if (t && t.party && t.color && !partyColorMap[t.party]) {
      partyColorMap[t.party] = t.color;
    }
  });
  const chartDiv = document.getElementById("chart");
  if (!chartDiv) return;
  const BAND_BASE_HALF_WIDTH = 2.2;
  const BAND_VOL_MULTIPLIER = 0.85;
  const BAND_MIN_HALF_WIDTH = 1.8;
  const BAND_MAX_HALF_WIDTH = 4.2;
  const BAND_OPACITY = 0.30;
  const BAND_CENTER_WINDOW = 7;
  const BAND_WIDTH_WINDOW = 7;

  function hexToRgba(hex, alpha) {
    const clean = String(hex || "").replace("#", "").trim();
    if (clean.length !== 6) return `rgba(70, 95, 135, ${alpha})`;
    const r = parseInt(clean.slice(0, 2), 16);
    const g = parseInt(clean.slice(2, 4), 16);
    const b = parseInt(clean.slice(4, 6), 16);
    if (![r, g, b].every((v) => Number.isFinite(v))) return `rgba(70, 95, 135, ${alpha})`;
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  }

  function smoothSeries(values, windowSize) {
    const src = (values || []).map((v) => (Number.isFinite(v) ? Number(v) : null));
    const half = Math.max(1, Math.floor(windowSize / 2));
    const out = [];
    for (let i = 0; i < src.length; i++) {
      if (src[i] === null) {
        out.push(null);
        continue;
      }
      let wSum = 0;
      let vSum = 0;
      for (let j = Math.max(0, i - half); j <= Math.min(src.length - 1, i + half); j++) {
        const v = src[j];
        if (v === null) continue;
        const w = half + 1 - Math.abs(i - j);
        wSum += w;
        vSum += w * v;
      }
      out.push(wSum > 0 ? (vSum / wSum) : src[i]);
    }
    return out;
  }

  function clamp(v, lo, hi) {
    return Math.max(lo, Math.min(hi, v));
  }

  function getPollsterColor(name) {
    const s = String(name || "").trim();
    if (!s) return "#64748B";
    const keys = Object.keys(pollsterColorMap);
    for (const k of keys) {
      if (s.includes(k)) return pollsterColorMap[k];
    }
    return "#64748B";
  }

  function buildSmoothedBand(y) {
    const raw = (y || []).map((v) => (Number.isFinite(v) ? Number(v) : null));
    const center = smoothSeries(raw, BAND_CENTER_WINDOW);
    const residualAbs = raw.map((v, i) => {
      if (v === null || center[i] === null) return null;
      return Math.abs(v - center[i]);
    });
    const localVol = smoothSeries(residualAbs, BAND_WIDTH_WINDOW);
    const halfWidth = localVol.map((v) => {
      const vol = v === null ? 0.0 : v;
      return clamp(BAND_BASE_HALF_WIDTH + BAND_VOL_MULTIPLIER * vol, BAND_MIN_HALF_WIDTH, BAND_MAX_HALF_WIDTH);
    });
    const upper = center.map((v, i) => {
      if (v === null) return null;
      return Math.min(100, v + halfWidth[i]);
    });
    const lower = center.map((v, i) => {
      if (v === null) return null;
      return Math.max(0, v - halfWidth[i]);
    });
    return { upper, lower };
  }

  function buildTraces() {
    const out = [];
    const dashStyles = ["solid", "dash", "dot", "longdash", "dashdot"];
    const markerSymbols = ["circle", "square", "triangle-up", "cross", "star"];
    tracesData.forEach((p, idx) => {
      const dash = dashStyles[idx % dashStyles.length];
      const symbol = markerSymbols[idx % markerSymbols.length];
      const band = buildSmoothedBand(p.actual_y);
      out.push({
        x: p.actual_x, y: band.upper, type: "scatter", mode: "lines",
        legendgroup: p.party, showlegend: false, hoverinfo: "skip",
        line: { color: "rgba(0,0,0,0)", width: 0, shape: "spline", smoothing: 0.65 },
        meta: "band"
      });
      out.push({
        x: p.actual_x, y: band.lower, type: "scatter", mode: "lines",
        legendgroup: p.party, showlegend: false, hoverinfo: "skip",
        line: { color: "rgba(0,0,0,0)", width: 0, shape: "spline", smoothing: 0.65 },
        fill: "tonexty", fillcolor: hexToRgba(p.color, BAND_OPACITY),
        meta: "band"
      });
      out.push({
        x: p.actual_x, y: p.actual_y, type: "scatter", mode: "lines", name: (p.display_party || p.party),
        legendgroup: p.party, line: { color: p.color, width: 2.7, dash },
        hovertemplate: "<b>%{fullData.name}</b>: %{y:.2f}%<extra></extra>"
      });
      out.push({
        x: p.forecast_x, y: p.forecast_y, type: "scatter", mode: "lines",
        legendgroup: p.party, showlegend: false, line: { color: p.color, width: 2.2, dash: "dot" },
        hoverinfo: "skip"
      });
      out.push({
        x: [p.pred_x], y: [p.pred_y], type: "scatter", mode: "markers+text",
        legendgroup: p.party, showlegend: false, meta: (p.display_party || p.party),
        marker: { color: p.color, size: 10, symbol, line: { color: "#DDE8FF", width: 1 } },
        text: ["예측치"], textposition: "middle right", textfont: { color: p.color, size: 11 },
        customdata: [[p.pred_lo_80, p.pred_hi_80]],
        hovertemplate: "<b>%{meta} 예측</b><br>%{y:.2f}%<br>80% 구간: %{customdata[0]:.2f}% ~ %{customdata[1]:.2f}%<extra></extra>"
      });
    });
    if (Array.isArray(latestPollResults) && latestPollResults.length) {
      const top = latestPollResults[0] || {};
      const pollDate = top.date_end || null;
      const pollster = top.pollster || "최신 조사";
      const parties = Array.isArray(top.parties) ? top.parties : [];
      if (pollDate) {
        parties.forEach((row) => {
          const party = row.party;
          const displayParty = row.display_party || row.party || "";
          const val = Number(row.value);
          if (!party || !Number.isFinite(val)) return;
          const exists = tracesData.some((t) => t.party === party);
          if (!exists) return;
          const color = partyColorMap[party] || "#94A3B8";
          out.push({
            x: [pollDate],
            y: [val],
            type: "scatter",
            mode: "markers",
            showlegend: false,
            legendgroup: party,
            marker: { symbol: "diamond", size: 10, color, line: { color: "#DDE8FF", width: 1 } },
            hovertemplate: `<b>최신 여론조사</b><br>${pollster} (${pollDate})<br>${displayParty}: %{y:.1f}%<extra></extra>`
          });
        });
      }
    }
    if (Array.isArray(presidentRaw.x) && presidentRaw.x.length) {
      const approveBand = buildSmoothedBand(presidentRaw.approve || []);
      out.push({
        x: presidentRaw.x,
        y: approveBand.upper,
        type: "scatter",
        mode: "lines",
        legendgroup: "president_raw_approve",
        showlegend: false,
        hoverinfo: "skip",
        line: { color: "rgba(0,0,0,0)", width: 0, shape: "spline", smoothing: 0.65 },
        meta: "band"
      });
      out.push({
        x: presidentRaw.x,
        y: approveBand.lower,
        type: "scatter",
        mode: "lines",
        legendgroup: "president_raw_approve",
        showlegend: false,
        hoverinfo: "skip",
        line: { color: "rgba(0,0,0,0)", width: 0, shape: "spline", smoothing: 0.65 },
        fill: "tonexty",
        fillcolor: hexToRgba("#1D9BF0", BAND_OPACITY),
        meta: "band"
      });
      out.push({
        x: presidentRaw.x,
        y: presidentRaw.approve || [],
        type: "scatter",
        mode: "lines+markers",
        name: "대통령 긍정평가(raw)",
        legendgroup: "president_raw_approve",
        line: { color: "#1D9BF0", width: 2, dash: "dash" },
        marker: { size: 4, color: "#1D9BF0" },
        hovertemplate: "<b>대통령 긍정평가(raw)</b>: %{y:.2f}%<extra></extra>"
      });
      const disapproveBand = buildSmoothedBand(presidentRaw.disapprove || []);
      out.push({
        x: presidentRaw.x,
        y: disapproveBand.upper,
        type: "scatter",
        mode: "lines",
        legendgroup: "president_raw_disapprove",
        showlegend: false,
        hoverinfo: "skip",
        line: { color: "rgba(0,0,0,0)", width: 0, shape: "spline", smoothing: 0.65 },
        meta: "band"
      });
      out.push({
        x: presidentRaw.x,
        y: disapproveBand.lower,
        type: "scatter",
        mode: "lines",
        legendgroup: "president_raw_disapprove",
        showlegend: false,
        hoverinfo: "skip",
        line: { color: "rgba(0,0,0,0)", width: 0, shape: "spline", smoothing: 0.65 },
        fill: "tonexty",
        fillcolor: hexToRgba("#D83A3A", BAND_OPACITY),
        meta: "band"
      });
      out.push({
        x: presidentRaw.x,
        y: presidentRaw.disapprove || [],
        type: "scatter",
        mode: "lines+markers",
        name: "대통령 부정평가(raw)",
        legendgroup: "president_raw_disapprove",
        line: { color: "#D83A3A", width: 2, dash: "dash" },
        marker: { size: 4, color: "#D83A3A" },
        hovertemplate: "<b>대통령 부정평가(raw)</b>: %{y:.2f}%<extra></extra>"
      });
    }
    return out;
  }

  function isDarkMode() {
    const explicit = document.documentElement.getAttribute("data-theme");
    if (explicit === "dark") return true;
    if (explicit === "light") return false;
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  }

  function isTouchDevice() {
    return (
      (window.matchMedia && window.matchMedia("(pointer: coarse)").matches) ||
      ("ontouchstart" in window) ||
      (navigator.maxTouchPoints > 0)
    );
  }

  function isMobileViewport() {
    return window.matchMedia && window.matchMedia("(max-width: 980px)").matches;
  }

  function buildLayout() {
    const dark = isDarkMode();
    const compactHover = isTouchDevice() || isMobileViewport();
    return {
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: dark ? "#152338" : "#F8FAFD",
      font: { color: dark ? "#EAF0FA" : "#1A2332", family: "Inter, Pretendard, sans-serif" },
      margin: { l: 55, r: 20, t: 92, b: 44 },
      hovermode: compactHover ? "closest" : "x unified",
      dragmode: "pan",
      hoverlabel: {
        bgcolor: dark ? "#111A2B" : "#FFFFFF",
        bordercolor: "#8FB3FF",
        font: { color: dark ? "#EAF0FA" : "#1A2332", size: compactHover ? 11 : 13, family: "Inter, Pretendard, sans-serif" },
        align: "left",
        namelength: compactHover ? 32 : -1
      },
      xaxis: {
        gridcolor: dark ? "rgba(158,176,204,0.16)" : "rgba(71,85,105,0.18)",
        linecolor: dark ? "rgba(158,176,204,0.24)" : "rgba(100,116,139,0.35)",
        showspikes: !compactHover,
        spikemode: "across",
        spikecolor: dark ? "rgba(158,176,204,0.5)" : "rgba(71,85,105,0.5)",
        spikedash: "dot",
        spikethickness: 1,
        fixedrange: true
      },
      yaxis: {
        title: "지지율(%)",
        gridcolor: dark ? "rgba(158,176,204,0.16)" : "rgba(71,85,105,0.18)",
        zeroline: false,
        fixedrange: true
      },
      legend: {
        orientation: "h",
        x: 0,
        xanchor: "left",
        y: 1.16,
        yanchor: "bottom",
        bgcolor: dark ? "rgba(17,26,41,0.88)" : "rgba(255,255,255,0.92)",
        bordercolor: dark ? "rgba(110,138,174,0.45)" : "rgba(106,125,160,0.45)",
        borderwidth: 1,
        font: { size: 12 }
      }
    };
  }

  function getIntroRange() {
    let end = null;
    tracesData.forEach((p) => {
      if (p.pred_x) {
        const d = new Date(p.pred_x);
        if (!Number.isNaN(d.getTime()) && (!end || d > end)) end = d;
      }
    });
    if (!end) return null;
    const start = new Date(end);
    start.setMonth(start.getMonth() - 3);
    const introEnd = new Date(start);
    introEnd.setDate(introEnd.getDate() + 14);
    if (introEnd >= end) return { start, introEnd: new Date(end), end };
    return { start, introEnd, end };
  }

  function animateSeriesRevealOnce() {
    if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const range = getIntroRange();
    if (!range) return;
    const startMs = range.start.getTime();
    const introMs = range.introEnd.getTime();
    const endMs = range.end.getTime();
    if (!Number.isFinite(startMs) || !Number.isFinite(introMs) || !Number.isFinite(endMs)) return;
    if (startMs >= introMs || introMs > endMs) return;

    Plotly.relayout(chartDiv, { "xaxis.range": [range.start, range.introEnd] }).then(() => {
      Plotly.animate(
        chartDiv,
        { layout: { "xaxis.range": [range.start, range.end] } },
        {
          transition: { duration: 950, easing: "cubic-in-out" },
          frame: { duration: 950, redraw: false },
          mode: "immediate"
        }
      );
    });
  }

  function renderChart() {
    return Plotly.react(chartDiv, buildTraces(), buildLayout(), {
      displayModeBar: false,
      responsive: true,
      scrollZoom: false,
      doubleClick: false
    });
  }

  function syncChartHeightToRanking() {
    const left = document.querySelector(".main-grid > article.panel.chart-panel");
    const right = document.querySelector(".main-grid > aside.panel");
    if (!left || !right) return;
    const nonChartHeight = left.offsetHeight - chartDiv.offsetHeight;
    const target = right.offsetHeight - nonChartHeight;
    if (Number.isFinite(target) && target > 420) {
      chartDiv.style.height = `${Math.round(target)}px`;
    }
  }

  function renderAndSync() {
    syncChartHeightToRanking();
    const shouldAnimate = !chartDiv.dataset.animated;
    const renderPromise = renderChart();
    if (renderPromise && typeof renderPromise.then === "function") {
      renderPromise.then(() => {
        if (shouldAnimate) {
          animateSeriesRevealOnce();
          chartDiv.dataset.animated = "1";
        }
        Plotly.Plots.resize(chartDiv);
      });
      return;
    }
    if (shouldAnimate) {
      animateSeriesRevealOnce();
      chartDiv.dataset.animated = "1";
    }
    Plotly.Plots.resize(chartDiv);
  }

  renderAndSync();
  window.addEventListener("resize", renderAndSync);
  if (window.matchMedia) {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    if (mq.addEventListener) mq.addEventListener("change", renderAndSync);
    else if (mq.addListener) mq.addListener(renderAndSync);
  }

  if (isTouchDevice()) {
    chartDiv.addEventListener("touchend", () => {
      setTimeout(() => Plotly.Fx.unhover(chartDiv), 0);
    }, { passive: true });
  }

  const rangeBtns = [...document.querySelectorAll(".fbtn[data-range]")];
  const bandBtn = document.getElementById("toggle-band");
  const hiddenParties = new Set();
  let showBands = true;

  function applyPartyVisibility() {
    const vis = chartDiv.data.map((t) => {
      if (hiddenParties.has(t.legendgroup)) return "legendonly";
      if (!showBands && t.meta === "band") return "legendonly";
      return true;
    });
    Plotly.restyle(chartDiv, { visible: vis });
    document.querySelectorAll(".rank-card").forEach((c) => {
      c.classList.toggle("muted", hiddenParties.has(c.dataset.party));
    });
  }

  function setBtnActive(key) {
    rangeBtns.forEach((b) => {
      const active = b.dataset.range === key;
      b.classList.toggle("active", active);
      b.setAttribute("aria-pressed", active ? "true" : "false");
    });
  }
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

  rangeBtns.forEach((btn) => {
    if (btn.dataset.range !== "reset") {
      btn.setAttribute("role", "button");
      btn.setAttribute("aria-pressed", btn.classList.contains("active") ? "true" : "false");
    }
    btn.addEventListener("click", () => {
      const key = btn.dataset.range;
      if (key === "reset") {
        hiddenParties.clear();
        applyPartyVisibility();
        document.querySelectorAll(".rank-card").forEach((c) => c.classList.remove("active", "muted"));
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

  if (bandBtn) {
    bandBtn.setAttribute("aria-pressed", "true");
    bandBtn.addEventListener("click", () => {
      showBands = !showBands;
      bandBtn.classList.toggle("active", showBands);
      bandBtn.textContent = showBands ? "오차 범위 표시: 켜짐" : "오차 범위 표시: 꺼짐";
      bandBtn.setAttribute("aria-pressed", showBands ? "true" : "false");
      applyPartyVisibility();
    });
  }

  const rankCards = [...document.querySelectorAll(".rank-card")];
  rankCards.forEach((card) => {
    card.addEventListener("click", () => {
      const party = card.dataset.party;
      if (hiddenParties.has(party)) hiddenParties.delete(party);
      else hiddenParties.add(party);
      applyPartyVisibility();
      card.classList.toggle("active", !hiddenParties.has(party));
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

  function renderLatestPollSection() {
    const section = document.getElementById("latest-poll-section");
    if (!section) return;
    if (!Array.isArray(latestPollResults) || !latestPollResults.length) {
      section.style.display = "none";
      return;
    }
    section.style.display = "";

    const listEl = document.getElementById("latest-poll-list");
    if (listEl) {
      listEl.innerHTML = latestPollResults.slice(0, 6).map((row) => {
        const sourceUrl = esc(row.source_url || "");
        const pColor = esc(getPollsterColor(row.pollster || ""));
        const valueLines = (row.parties || [])
          .map((p) => `${esc(p.display_party || p.party)} ${Number(p.value).toFixed(1)}%`)
          .join(" · ");
        return `
          <article class="latest-poll-card">
            <div class="latest-poll-head">
              <div class="latest-poll-pollster"><span class="pollster-chip" style="background:${pColor};"></span>${esc(row.pollster || "-")}</div>
              <div class="latest-poll-date">${esc(row.date_end || "")}</div>
            </div>
            <div class="latest-poll-values">${valueLines}</div>
            ${sourceUrl ? `<a class="latest-poll-source link-out" href="${sourceUrl}" target="_blank" rel="noopener noreferrer">기사 링크</a>` : `<div class="latest-poll-source">출처 없음</div>`}
          </article>
        `;
      }).join("");
    }

    const chartEl = document.getElementById("latest-poll-chart");
    if (!chartEl) return;
    const top = latestPollResults[0] || {};
    const pieRows = (top.parties || []).filter((p) => Number.isFinite(Number(p.value)) && Number(p.value) > 0);
    const labels = pieRows.map((p) => p.display_party || p.party);
    const values = pieRows.map((p) => Number(p.value));
    const colors = pieRows.map((p) => partyColorMap[p.party] || "#94A3B8");
    const dark = isDarkMode();
    Plotly.react(
      chartEl,
      [
        {
          type: "pie",
          labels,
          values,
          hole: 0.42,
          showlegend: false,
          sort: false,
          textinfo: "label",
          marker: { colors, line: { color: dark ? "#1B2638" : "#FFFFFF", width: 1 } },
          hovertemplate: "<b>%{label}</b>: %{value:.1f}%<extra></extra>",
        }
      ],
      {
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: dark ? "#152338" : "#F8FAFD",
        margin: { l: 20, r: 20, t: 52, b: 20 },
        font: { color: dark ? "#EAF0FA" : "#1A2332", family: "Inter, Pretendard, sans-serif" },
        title: {
          text: `${top.pollster || "최신 조사"} · ${top.date_end || ""}`,
          x: 0,
          xanchor: "left",
          font: { size: 13 }
        },
      },
      { displayModeBar: false, responsive: true }
    );
  }

  function renderForecastComparisonSection() {
    const section = document.getElementById("poll-compare-section");
    if (!section) return;
    if (!Array.isArray(latestPollResults) || !latestPollResults.length || !Array.isArray(tracesData) || !tracesData.length) {
      section.style.display = "none";
      return;
    }
    const top = latestPollResults[0] || {};
    const forecastMap = {};
    tracesData.forEach((t) => {
      if (t && t.party && Number.isFinite(Number(t.pred_y))) {
        forecastMap[t.party] = Number(t.pred_y);
      }
    });
    const rows = (top.parties || [])
      .map((p) => {
        const latest = Number(p.value);
        const pred = forecastMap[p.party];
        if (!Number.isFinite(latest) || !Number.isFinite(pred)) return null;
        return {
          party: p.party,
          display_party: p.display_party || p.party,
          latest,
          pred,
          delta: latest - pred,
          color: partyColorMap[p.party] || "#94A3B8",
        };
      })
      .filter(Boolean)
      .sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta));

    if (!rows.length) {
      section.style.display = "none";
      return;
    }
    section.style.display = "";

    const listEl = document.getElementById("poll-compare-list");
    if (listEl) {
      listEl.innerHTML = rows.map((r) => {
        const sign = r.delta > 0 ? "+" : "";
        const deltaColor = r.delta >= 0 ? "#0F9D58" : "#D83A3A";
        return `
          <article class="poll-compare-card">
            <div class="poll-compare-head">
              <div class="poll-compare-party">${esc(r.display_party || r.party)}</div>
              <div class="poll-compare-delta" style="color:${deltaColor}">${sign}${r.delta.toFixed(1)}%p</div>
            </div>
            <div class="poll-compare-meta">최신 ${r.latest.toFixed(1)}% · 예측 ${r.pred.toFixed(1)}%</div>
          </article>
        `;
      }).join("");
    }

    const chartEl = document.getElementById("poll-compare-chart");
    if (!chartEl) return;
    const dark = isDarkMode();
    const sorted = rows.slice().reverse();
    const labels = sorted.map((r) => r.display_party || r.party);

    const traces = [];
    sorted.forEach((r) => {
      traces.push({
        type: "scatter",
        mode: "lines",
        x: [r.pred, r.latest],
        y: [r.display_party || r.party, r.display_party || r.party],
        line: { color: dark ? "rgba(234,240,250,0.35)" : "rgba(26,35,50,0.28)", width: 3 },
        hoverinfo: "skip",
        showlegend: false,
      });
    });
    traces.push({
      type: "scatter",
      mode: "markers",
      name: "예측치",
      x: sorted.map((r) => r.pred),
      y: labels,
      marker: {
        size: 9,
        color: sorted.map((r) => r.color),
        symbol: "circle-open",
        line: { width: 2, color: sorted.map((r) => r.color) },
      },
      hovertemplate: "<b>%{y}</b><br>예측: %{x:.1f}%<extra></extra>",
    });
    traces.push({
      type: "scatter",
      mode: "markers+text",
      name: "최신 조사",
      x: sorted.map((r) => r.latest),
      y: labels,
      marker: {
        size: 10,
        color: sorted.map((r) => r.color),
        symbol: "diamond",
        line: { width: 1, color: dark ? "#EAF0FA" : "#FFFFFF" },
      },
      text: sorted.map((r) => {
        const d = r.delta;
        return `${d > 0 ? "+" : ""}${d.toFixed(1)}%p`;
      }),
      textposition: "middle right",
      textfont: { size: 11, color: dark ? "#EAF0FA" : "#1A2332" },
      hovertemplate: "<b>%{y}</b><br>최신: %{x:.1f}%<extra></extra>",
    });

    Plotly.react(
      chartEl,
      traces,
      {
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: dark ? "#152338" : "#F8FAFD",
        margin: { l: 90, r: 20, t: 20, b: 34 },
        font: { color: dark ? "#EAF0FA" : "#1A2332", family: "Inter, Pretendard, sans-serif" },
        xaxis: {
          title: "지지율(%)",
          zeroline: true,
          zerolinecolor: dark ? "rgba(234,240,250,0.5)" : "rgba(26,35,50,0.5)",
          gridcolor: dark ? "rgba(158,176,204,0.16)" : "rgba(71,85,105,0.18)",
        },
        yaxis: { automargin: true, categoryorder: "array", categoryarray: labels },
        legend: { orientation: "h", x: 0, y: 1.08, xanchor: "left" },
      },
      { displayModeBar: false, responsive: true }
    );
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

  function parseNewsDate(row) {
    const raw = row && (row.published_at || row.date);
    if (!raw) return null;
    const dt = new Date(raw);
    return Number.isNaN(dt.getTime()) ? null : dt;
  }

  function formatRelative(dt) {
    if (!dt) return "";
    const diffMs = Date.now() - dt.getTime();
    if (!Number.isFinite(diffMs) || diffMs < 0) return dt.toLocaleDateString("ko-KR");
    const min = Math.floor(diffMs / 60000);
    if (min < 1) return "방금 전";
    if (min < 60) return `${min}분 전`;
    const hour = Math.floor(min / 60);
    if (hour < 24) return `${hour}시간 전`;
    const day = Math.floor(hour / 24);
    return `${day}일 전`;
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
    function setStatus(text, tone) {
      if (!status) return;
      status.textContent = text;
      status.classList.remove("fresh", "stale", "old");
      if (tone) status.classList.add(tone);
    }

    const phrase = "중앙선거여론조사심의위원회";
    setStatus("기사 목록 불러오는 중...", "stale");

    // Primary: same-origin static JSON generated at build time.
    try {
      const local = await fetch("news_latest.json", { cache: "no-store" });
      if (local.ok) {
        const rows = await local.json();
        if (Array.isArray(rows) && rows.length) {
          const sorted = rows
            .map((r) => ({ ...r, _dt: parseNewsDate(r) }))
            .sort((a, b) => (b._dt ? b._dt.getTime() : 0) - (a._dt ? a._dt.getTime() : 0));
          grid.innerHTML = sorted.slice(0, 6).map((r) => `
            <a class="news-card link-out" href="${esc(r.url || "")}" target="_blank" rel="noopener noreferrer">
              <div class="news-date">${esc(formatRelative(r._dt) || (r.date || ""))}</div>
              <div class="news-title">${esc(r.title || "")}</div>
              <div class="news-source">${esc(r.source || "출처")}</div>
            </a>
          `).join("");
          setStatus(`자동 갱신 완료 (${Math.min(sorted.length, 6)}건)`, "fresh");
          return;
        }
        if (Array.isArray(rows) && rows.length === 0) {
          setStatus("조건에 맞는 최신 기사 없음", "stale");
          return;
        }
      }
    } catch (_) {}

    const debugProxy = new URLSearchParams(window.location.search).get("newsProxy") === "1";
    if (!debugProxy) {
      setStatus("빌드 시점 수집 데이터 표시 중", "stale");
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
      setStatus("디버그 프록시 로딩 실패(정적 데이터 유지)", "old");
      return;
    }
    const rows = parseRss(xmlText).filter((r) => stripHtml(r.title + " " + r.desc).includes(phrase)).slice(0, 6);
    if (!rows.length) {
      setStatus("디버그 프록시 결과 없음(정적 데이터 유지)", "old");
      return;
    }
    grid.innerHTML = rows.map((r) => {
      const d = r.date && !Number.isNaN(r.date.getTime()) ? formatRelative(r.date) : "";
      return `<a class="news-card link-out" href="${esc(r.link)}" target="_blank" rel="noopener noreferrer"><div class="news-date">${esc(d)}</div><div class="news-title">${esc(r.title)}</div><div class="news-source">${esc(r.source)}</div></a>`;
    }).join("");
    setStatus(`디버그 프록시 갱신 (${rows.length}건)`, "fresh");
  }

  fetchRecentPollNews();
  renderLatestPollSection();
  renderForecastComparisonSection();
})();
""".strip()


def canonical_party_name(name: str) -> str:
    s = str(name).strip().replace("  ", " ")
    for canonical, meta in PARTY_STYLES.items():
        for a in meta["aliases"]:
            if s == a:
                return canonical
    return s


def party_display_name(party: str, as_of_kst: datetime | None = None) -> str:
    p = canonical_party_name(party)
    if p == "국민의힘":
        return "국민의힘"
    return p


def pollster_color(name: str) -> str:
    s = str(name or "").strip()
    if not s:
        return POLLSTER_COLOR_FALLBACK
    for key, color in POLLSTER_COLOR_MAP.items():
        if key in s:
            return color
    return POLLSTER_COLOR_FALLBACK


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


def dedupe_same_day_same_source(df: pd.DataFrame, limit: int = 12) -> pd.DataFrame:
    cols = ["date", "source", "title", "url", "published_at"]
    if df is None or df.empty:
        return pd.DataFrame(columns=cols)
    out = df.copy()
    for c in cols:
        if c not in out.columns:
            out[c] = ""
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out["source"] = out["source"].astype(str).str.strip()
    out["title"] = out["title"].astype(str).str.strip()
    out["url"] = out["url"].astype(str).str.strip()
    out = out.dropna(subset=["date"]).copy()
    out = out[(out["source"] != "") & (out["title"] != "") & (out["url"] != "")].copy()
    if "_dt" in out.columns:
        out = out.sort_values("_dt", ascending=False, na_position="last")
    else:
        out = out.sort_values("date", ascending=False, na_position="last")
    out["date_only"] = out["date"].dt.date.astype(str)
    out = out.drop_duplicates(subset=["date_only", "source"], keep="first")
    out = out.drop(columns=["date_only"], errors="ignore")
    out = out.sort_values("date", ascending=False, na_position="last")
    return out[["date", "source", "title", "url", "published_at"]].head(limit).reset_index(drop=True)


def load_cached_news_json(base: Path) -> pd.DataFrame:
    p = base / "docs" / "news_latest.json"
    cols = ["date", "source", "title", "url", "published_at"]
    if not p.exists():
        return pd.DataFrame(columns=cols)
    try:
        rows = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return pd.DataFrame(columns=cols)
    if not isinstance(rows, list):
        return pd.DataFrame(columns=cols)
    df = pd.DataFrame(rows)
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    df["published_at"] = pd.to_datetime(df["published_at"], errors="coerce", utc=True)
    df["date"] = pd.to_datetime(df["date"], errors="coerce", utc=True)
    df["_dt"] = df["published_at"].where(df["published_at"].notna(), df["date"])
    df = df.dropna(subset=["date", "title", "url"])
    return dedupe_same_day_same_source(df, limit=12)


def fetch_google_news_articles(
    phrase: str = "중앙선거여론조사심의위원회",
    limit: int = 12,
    max_content_checks: int = 80,
) -> pd.DataFrame:
    def _fetch_html(url: str, timeout: int = 12) -> str:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "ignore")

    def _extract_naver_links(search_html: str) -> list[str]:
        cands = re.findall(r'https://n\.news\.naver\.com/mnews/article/\d+/\d+', search_html)
        uniq: list[str] = []
        for u in cands:
            if u not in uniq:
                uniq.append(u)
        return uniq

    def _extract_title(html: str, fallback_url: str) -> str:
        for pat in [
            r'<meta\s+property="og:title"\s+content="([^"]+)"',
            r"<meta\s+property='og:title'\s+content='([^']+)'",
            r"<title>(.*?)</title>",
        ]:
            m = re.search(pat, html, flags=re.I | re.S)
            if m:
                return re.sub(r"\s+", " ", m.group(1)).strip()
        return fallback_url

    def _extract_source(html: str) -> str:
        patterns = [
            r'<meta\s+name="twitter:creator"\s+content="([^"]+)"',
            r'<meta\s+property="og:article:author"\s+content="([^"]+)"',
            r'alt="([^"]+)"\s+title="[^"]*"\s+class="media_end_head_top_logo_img',
        ]
        for pat in patterns:
            m = re.search(pat, html, flags=re.I | re.S)
            if m:
                s = re.sub(r"\s+", " ", m.group(1)).strip()
                if "|" in s:
                    s = s.split("|", 1)[0].strip()
                if s:
                    return s
        return "네이버뉴스"

    def _extract_published_dt(html: str) -> pd.Timestamp:
        patterns = [
            r'data-date-time="([^"]+)"',
            r'"date":"([0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2})"',
        ]
        for pat in patterns:
            m = re.search(pat, html, flags=re.I | re.S)
            if not m:
                continue
            ts = pd.to_datetime(m.group(1), errors="coerce")
            if pd.notna(ts):
                if getattr(ts, "tzinfo", None) is None:
                    ts = ts.tz_localize("Asia/Seoul")
                return ts
        return pd.Timestamp.now(tz=ZoneInfo("Asia/Seoul"))

    pollster_keywords = [str(x).strip() for x in POLLSTERS if str(x).strip()]
    priority_steps = [
        {
            "priority": 1,
            "name": "phrase",
            "queries": [f"{phrase} 여론조사", f"{phrase} 정당 지지율", phrase],
        },
        {
            "priority": 2,
            "name": "pollster_name",
            "queries": [f"{k} 여론조사" for k in pollster_keywords],
        },
        {
            "priority": 3,
            "name": "general_poll",
            "queries": ["여론조사 정당 지지율", "여론조사"],
        },
    ]
    article_cache: dict[str, tuple[bool, str, str]] = {}
    seen_urls: set[str] = set()

    content_checks = 0
    rows = []

    def _fetch_article_payload(url: str) -> tuple[bool, str, str]:
        nonlocal content_checks
        if url in article_cache:
            return article_cache[url]
        if content_checks >= max_content_checks:
            article_cache[url] = (False, "", "")
            return article_cache[url]
        try:
            content_checks += 1
            html = _fetch_html(url, timeout=8)
            txt = re.sub(r"(?is)<script.*?>.*?</script>|<style.*?>.*?</style>|<[^>]+>", " ", html)
            txt = re.sub(r"\s+", " ", txt).strip()
            ok = True
        except Exception:
            ok = False
            html = ""
            txt = ""
        article_cache[url] = (ok, html, txt)
        return article_cache[url]

    def _match_priority(text: str, title: str) -> int | None:
        t = f"{title} {text}"
        if phrase in t:
            return 1
        if any(k in t for k in pollster_keywords):
            return 2
        if "여론조사" in t:
            return 3
        return None

    for step in priority_steps:
        for q in step["queries"]:
            try:
                surl = (
                    "https://search.naver.com/search.naver"
                    f"?where=news&sm=tab_jum&query={urllib.parse.quote(q)}"
                )
                search_html = _fetch_html(surl, timeout=12)
                links = _extract_naver_links(search_html)[:40]
            except Exception:
                links = []
            for link in links:
                if link in seen_urls:
                    continue
                ok, html, text = _fetch_article_payload(link)
                if not ok:
                    continue
                title = _extract_title(html, link)
                matched_priority = _match_priority(text, title)
                if matched_priority != step["priority"]:
                    continue
                seen_urls.add(link)
                article_dt = _extract_published_dt(html)
                rows.append(
                    {
                        "date": article_dt.date().isoformat(),
                        "published_at": article_dt.isoformat(),
                        "source": _extract_source(html),
                        "title": title,
                        "url": link,
                        "priority": matched_priority,
                        "priority_name": step["name"],
                        "_dt": article_dt,
                    }
                )
                if len(rows) >= limit:
                    break
            if len(rows) >= limit:
                break
        if len(rows) >= limit:
            break

    if not rows:
        return pd.DataFrame(columns=["date", "source", "title", "url"])
    out = pd.DataFrame(rows).drop_duplicates(subset=["url"]).copy()
    out = out.sort_values(["priority", "_dt"], ascending=[True, False], na_position="last")
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out = out.dropna(subset=["date", "title", "url"])
    return dedupe_same_day_same_source(out, limit=limit)


def fetch_google_rss_fallback(limit: int = 12) -> pd.DataFrame:
    phrase = "중앙선거여론조사심의위원회"
    pollster_keywords = [str(x).strip() for x in POLLSTERS if str(x).strip()]
    queries = [f'"{phrase}"', f"{phrase} 여론조사", "여론조사"]

    rows = []
    seen = set()

    def _priority(text: str) -> int | None:
        if phrase in text:
            return 1
        if any(k in text for k in pollster_keywords):
            return 2
        if "여론조사" in text:
            return 3
        return None

    for q in queries:
        try:
            rss = (
                "https://news.google.com/rss/search"
                f"?q={urllib.parse.quote(q)}&hl=ko&gl=KR&ceid=KR:ko"
            )
            entries = getattr(feedparser.parse(rss), "entries", [])
        except Exception:
            entries = []

        for e in entries[:80]:
            title = str(getattr(e, "title", "")).strip()
            desc = str(getattr(e, "summary", "")).strip()
            link = str(getattr(e, "link", "")).strip()
            src = str(getattr(getattr(e, "source", None), "title", "")).strip() or "Google News"
            txt = re.sub(r"\s+", " ", f"{title} {desc}")
            p = _priority(txt)
            if p is None or not link or link in seen:
                continue
            seen.add(link)
            pub = pd.to_datetime(str(getattr(e, "published", "")), errors="coerce")
            if pd.isna(pub):
                pub = pd.Timestamp.now(tz=ZoneInfo("Asia/Seoul"))
            rows.append(
                {
                    "date": pd.to_datetime(pub).date().isoformat(),
                    "published_at": pd.to_datetime(pub).isoformat(),
                    "source": src,
                    "title": title,
                    "url": link,
                    "priority": p,
                    "_dt": pd.to_datetime(pub),
                }
            )

    if not rows:
        return pd.DataFrame(columns=["date", "source", "title", "url"])
    out = pd.DataFrame(rows).drop_duplicates(subset=["url"]).copy()
    out = out.sort_values(["priority", "_dt"], ascending=[True, False], na_position="last")
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out = out.dropna(subset=["date", "title", "url"])
    return dedupe_same_day_same_source(out, limit=limit)


def resolve_news_articles(base: Path, outputs: Path) -> tuple[pd.DataFrame, str]:
    # Priority 1: collector-generated cached JSON (hourly stage1 feed).
    cached = load_cached_news_json(base)
    if not cached.empty:
        return dedupe_same_day_same_source(cached, limit=12), "collector_cached_news_latest_json"

    # Priority 2: build-time article fetch + content verification
    fetched_articles = fetch_google_news_articles()
    if not fetched_articles.empty:
        return dedupe_same_day_same_source(fetched_articles, limit=12), "naver_priority_1_2_3"

    # Priority 3: Google RSS fallback for freshness when naver parsing fails.
    rss_articles = fetch_google_rss_fallback(limit=12)
    if not rss_articles.empty:
        return dedupe_same_day_same_source(rss_articles, limit=12), "google_rss_priority_1_2_3"

    # Priority 4: manual fallback file (curated), use same priority concept on title text.
    phrase = "중앙선거여론조사심의위원회"
    pollster_keywords = [str(x).strip() for x in POLLSTERS if str(x).strip()]
    manual = load_recent_articles(base)
    if not manual.empty:
        t = manual["title"].astype(str)
        cond1 = t.str.contains(phrase, na=False)
        cond2 = t.apply(lambda x: any(k in x for k in pollster_keywords))
        cond3 = t.str.contains("여론조사", na=False)
        manual = manual[cond1 | cond2 | cond3].copy()
        manual = dedupe_same_day_same_source(manual, limit=12)
        if not manual.empty:
            return manual, "recent_articles_csv_priority_1_2_3"

    # If nothing matches the strict rule, return empty list.
    return pd.DataFrame(columns=["date", "source", "title", "url"]), "no_matching_articles"


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
    for model in ["legacy", "ssm", "ssm_exog"]:
        r = df[df["model"] == model]
        if not r.empty:
            out[f"{model}_mae"] = float(pd.to_numeric(r.iloc[0]["mae"], errors="coerce"))
            out[f"{model}_rmse"] = float(pd.to_numeric(r.iloc[0].get("rmse"), errors="coerce"))
            out[f"{model}_n"] = int(pd.to_numeric(r.iloc[0].get("n"), errors="coerce"))
    if "legacy_mae" in out and "ssm_mae" in out and out["legacy_mae"] > 0:
        out["improvement_pct"] = (out["legacy_mae"] - out["ssm_mae"]) / out["legacy_mae"] * 100.0
    if "ssm_mae" in out and "ssm_exog_mae" in out and out["ssm_mae"] > 0:
        out["improvement_exog_pct"] = (out["ssm_mae"] - out["ssm_exog_mae"]) / out["ssm_mae"] * 100.0
    return out


def load_president_approval_overall(outputs: Path) -> dict:
    p = outputs / "president_approval_weekly.csv"
    if not p.exists():
        return {}
    try:
        df = pd.read_csv(p)
    except Exception:
        return {}
    if "week_monday" not in df.columns or "approve" not in df.columns:
        return {}
    df["week_monday"] = pd.to_datetime(df["week_monday"], errors="coerce")
    for c in ["approve", "disapprove", "dk"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["week_monday", "approve"]).sort_values("week_monday")
    if df.empty:
        return {}
    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) >= 2 else None
    out = {
        "week_monday": latest["week_monday"].strftime("%Y-%m-%d"),
        "approve": float(latest["approve"]),
        "disapprove": float(latest["disapprove"]) if "disapprove" in df.columns and pd.notna(latest.get("disapprove")) else None,
        "dk": float(latest["dk"]) if "dk" in df.columns and pd.notna(latest.get("dk")) else None,
    }
    if prev is not None and pd.notna(prev.get("approve")):
        out["approve_delta"] = float(latest["approve"] - prev["approve"])
    return out


def load_president_approval_raw_series(outputs: Path) -> dict:
    p = outputs / "president_approval_weekly.csv"
    if not p.exists():
        return {"x": [], "approve": [], "disapprove": []}
    try:
        df = pd.read_csv(p)
    except Exception:
        return {"x": [], "approve": [], "disapprove": []}
    if "week_monday" not in df.columns:
        return {"x": [], "approve": [], "disapprove": []}
    if "approve" not in df.columns or "disapprove" not in df.columns:
        return {"x": [], "approve": [], "disapprove": []}
    df["week_monday"] = pd.to_datetime(df["week_monday"], errors="coerce")
    df["approve"] = pd.to_numeric(df["approve"], errors="coerce")
    df["disapprove"] = pd.to_numeric(df["disapprove"], errors="coerce")
    df = df.dropna(subset=["week_monday"]).sort_values("week_monday")
    if df.empty:
        return {"x": [], "approve": [], "disapprove": []}
    x = []
    approve = []
    disapprove = []
    for _, r in df.iterrows():
        x.append(r["week_monday"].strftime("%Y-%m-%d"))
        approve.append(float(r["approve"]) if pd.notna(r["approve"]) else None)
        disapprove.append(float(r["disapprove"]) if pd.notna(r["disapprove"]) else None)
    return {"x": x, "approve": approve, "disapprove": disapprove}


def load_president_approval_table_rows(outputs: Path, max_rows: int = 24) -> list[dict]:
    detail = outputs / "president_approval_weekly_detail.csv"
    if not detail.exists():
        return []
    try:
        df = pd.read_csv(detail)
    except Exception:
        return []
    req = {"week_start", "week_end", "approve", "disapprove", "publisher", "source_url"}
    if not req.issubset(set(df.columns)):
        return []
    df["week_start"] = pd.to_datetime(df["week_start"], errors="coerce")
    df["approve"] = pd.to_numeric(df["approve"], errors="coerce")
    df["disapprove"] = pd.to_numeric(df["disapprove"], errors="coerce")
    df = df.dropna(subset=["week_start", "approve", "disapprove"]).copy()
    if df.empty:
        return []
    if "source_title" not in df.columns:
        df["source_title"] = ""
    if "notes" not in df.columns:
        df["notes"] = ""
    df = df.sort_values("week_start", ascending=False).head(max_rows)
    rows = []
    for _, r in df.iterrows():
        rows.append(
            {
                "week_start": pd.to_datetime(r["week_start"]).strftime("%Y-%m-%d"),
                "week_end": str(r.get("week_end", "")),
                "approve": float(r["approve"]),
                "disapprove": float(r["disapprove"]),
                "publisher": str(r.get("publisher", "")).strip() or "-",
                "source_url": str(r.get("source_url", "")).strip(),
                "source_title": str(r.get("source_title", "")).strip(),
                "notes": str(r.get("notes", "")).strip(),
            }
        )
    return rows


def sparkline_svg(values: list[float], color: str) -> str:
    if not values:
        return ""
    def darken_hex(hex_color: str, ratio: float = 0.28) -> str:
        s = str(hex_color or "").strip().lstrip("#")
        if len(s) != 6:
            return "#385887"
        try:
            r = int(s[0:2], 16)
            g = int(s[2:4], 16)
            b = int(s[4:6], 16)
        except ValueError:
            return "#385887"
        r = max(0, min(255, int(r * (1.0 - ratio))))
        g = max(0, min(255, int(g * (1.0 - ratio))))
        b = max(0, min(255, int(b * (1.0 - ratio))))
        return f"#{r:02X}{g:02X}{b:02X}"

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
    stroke = darken_hex(color)
    return (
        f"<svg viewBox='0 0 {w} {h}' width='{w}' height='{h}' aria-hidden='true'>"
        f"<polyline fill='none' stroke='{stroke}' stroke-width='2.9' stroke-linecap='round' points='{poly}' />"
        "</svg>"
    )


def build_party_payload(
    blended: pd.DataFrame, forecast: pd.DataFrame, as_of_kst: datetime | None = None
) -> tuple[list[dict], list[dict], list[dict], dict]:
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

    now_ref = as_of_kst or datetime.now(tz=ZoneInfo("Asia/Seoul"))
    latest_ts = pd.to_datetime(df["date_end"]).max()
    if latest_ts.tzinfo is None:
        latest_ts = latest_ts.tz_localize("Asia/Seoul")
    else:
        latest_ts = latest_ts.tz_convert("Asia/Seoul")
    days_elapsed = max(0.0, (now_ref - latest_ts.to_pydatetime()).total_seconds() / 86400.0)
    alpha = min(1.0, days_elapsed / 7.0)

    pred_date = (pd.to_datetime(df["date_end"]).max() + pd.Timedelta(days=7)).strftime("%Y-%m-%d")
    traces: list[dict] = []
    ranking_rows: list[dict] = []
    nowcast_rows: list[dict] = []

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
                "display_party": party_display_name(party, as_of_kst),
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
                "display_party": party_display_name(party, as_of_kst),
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
        now_pred_lo = pred_lo_80 if pred_lo_80 is not None else pred
        now_pred_hi = pred_hi_80 if pred_hi_80 is not None else pred
        nowcast = last_actual + alpha * (pred - last_actual)
        nowcast_lo = last_actual + alpha * (now_pred_lo - last_actual)
        nowcast_hi = last_actual + alpha * (now_pred_hi - last_actual)
        nowcast_rows.append(
            {
                "party": party,
                "display_party": party_display_name(party, as_of_kst),
                "color": color,
                "nowcast": nowcast,
                "nowcast_lo_80": nowcast_lo,
                "nowcast_hi_80": nowcast_hi,
                "delta": nowcast - last_actual,
                "spark_svg": sparkline_svg(spark_vals, color),
            }
        )

    ranking_rows = sorted(ranking_rows, key=lambda x: x["pred"], reverse=True)
    nowcast_rows = sorted(nowcast_rows, key=lambda x: x["nowcast"], reverse=True)
    nowcast_meta = {
        "as_of": now_ref.strftime("%Y-%m-%d %H:%M KST"),
        "latest_observation": latest_ts.strftime("%Y-%m-%d"),
        "alpha": alpha,
    }
    return traces, ranking_rows, nowcast_rows, nowcast_meta


def load_latest_poll_results(outputs: Path, max_rows: int = 6) -> list[dict]:
    files = sorted(outputs.glob("weekly_public_points_*.csv"))
    if not files:
        return []
    latest = max(files, key=lambda p: p.stat().st_mtime)
    try:
        df = pd.read_csv(latest)
    except Exception:
        return []
    required = {"pollster", "date_end", "source_type", "source_url"}
    if not required.issubset(set(df.columns)):
        return []
    df["source_type"] = df["source_type"].astype(str)
    df = df[df["source_type"] == "observed_web"].copy()
    if df.empty:
        return []
    if "has_local_election_context" in df.columns:
        local = df["has_local_election_context"].astype(str).str.lower().map({"true": True, "false": False})
        df = df[~local.fillna(False)]
    if df.empty:
        return []
    df["date_end"] = pd.to_datetime(df["date_end"], errors="coerce")
    df = df.dropna(subset=["date_end"]).sort_values("date_end", ascending=False).head(max_rows)
    meta_cols = {"pollster", "date_end", "source_type", "source_url", "is_national_party_poll", "has_local_election_context"}

    rows: list[dict] = []
    for _, r in df.iterrows():
        party_rows = []
        for c in df.columns:
            if c in meta_cols:
                continue
            v = pd.to_numeric(r.get(c), errors="coerce")
            if pd.notna(v):
                canonical = canonical_party_name(str(c))
                party_rows.append(
                    {
                        "party": canonical,
                        "display_party": party_display_name(canonical),
                        "value": float(v),
                    }
                )
        party_rows = sorted(party_rows, key=lambda x: x["value"], reverse=True)
        rows.append(
            {
                "pollster": str(r.get("pollster", "")).strip(),
                "date_end": pd.to_datetime(r["date_end"]).strftime("%Y-%m-%d"),
                "source_url": str(r.get("source_url", "")).strip(),
                "parties": party_rows,
            }
        )
    return rows


def render_html(
    docs_dir: Path,
    traces: list[dict],
    ranking_rows: list[dict],
    nowcast_rows: list[dict],
    nowcast_meta: dict,
    weights_df: pd.DataFrame,
    articles_df: pd.DataFrame,
    latest_date: str,
    backtest_overall: dict,
    president_overall: dict,
    president_raw_series: dict,
    president_table_rows: list[dict],
    latest_poll_results: list[dict],
) -> None:
    now_kst = datetime.now(tz=ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S KST")
    cache_bust = datetime.now(tz=ZoneInfo("Asia/Seoul")).strftime("%Y%m%d%H%M%S")

    cards = []
    if len(nowcast_rows) >= 2:
        lead = nowcast_rows[0]
        second = nowcast_rows[1]
        cards.append(
            {
                "label": "현재 추정 1위 / 격차",
                "value": f"{lead.get('display_party', lead['party'])}",
                "sub": f"{(lead['nowcast'] - second['nowcast']):.2f}%p · {nowcast_meta.get('as_of', '-')}",
                "featured": True,
                "hero": True,
                "textual": True,
            }
        )
    swing = sum(abs(float(r["delta"])) for r in ranking_rows) / len(ranking_rows) if ranking_rows else 0.0
    cards.append(
        {"label": "이번주 평균 변동폭", "value": f"{swing:.2f}%p", "sub": "예측치-직전실측", "featured": True, "hero": False}
    )
    rmse_vals = [r["rmse"] for r in ranking_rows if r["rmse"] is not None]
    rmse_avg = sum(rmse_vals) / len(rmse_vals) if rmse_vals else 0.0
    cards.append(
        {
            "label": "평균 예측 오차 (RMSE)",
            "value": f"{rmse_avg:.2f}",
            "sub": "정당 평균",
            "featured": True,
            "hero": False,
            "tooltip": "RMSE는 예측값과 실제값 차이의 평균적인 크기를 뜻하며 낮을수록 정확합니다.",
        }
    )
    if president_overall:
        approve = president_overall.get("approve")
        disapprove = president_overall.get("disapprove")
        delta = president_overall.get("approve_delta")
        if approve is not None:
            if delta is None:
                sub = f"국정수행 긍정 (주차 {president_overall.get('week_monday', '-')})"
            else:
                sign = "+" if float(delta) >= 0 else ""
                sub = f"전주 대비 {sign}{float(delta):.2f}%p (주차 {president_overall.get('week_monday', '-')})"
            value = f"{float(approve):.2f}%"
            if disapprove is not None:
                value += f" <small>(부정 {float(disapprove):.2f}%)</small>"
            cards.append(
                {
                    "label": "대통령 국정수행 긍정",
                    "value": value,
                    "sub": sub,
                    "featured": False,
                    "hero": False,
                    "allow_html_value": True,
                }
            )
    else:
        cards.append({"label": "대통령 국정수행 긍정", "value": "-", "sub": "집계 데이터 없음", "featured": False, "hero": False})
    cards_html_rows = []
    for c in cards:
        tooltip_html = ""
        if c.get("tooltip"):
            tip = str(c.get("tooltip", "")).replace('"', "&quot;")
            tooltip_html = (
                f' <span class="metric-tooltip" tabindex="0" aria-label="RMSE 설명" data-tip="{tip}">ⓘ</span>'
            )
        cards_html_rows.append(
            f"""
            <article class=\"insight-card {'featured' if c.get('featured') else ''} {'hero' if c.get('hero') else ''}\">
              <div class=\"insight-label\">{c['label']}{tooltip_html}</div>
              <div class=\"insight-value {'textual' if c.get('textual') else ''}\">{c['value']}</div>
              <div class=\"insight-sub\">{c['sub']}</div>
            </article>
            """
        )
    cards_html = "".join(cards_html_rows)

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
                <div class=\"rank-party\">{r.get('display_party', r['party'])}</div>
              </div>
              <div class=\"rank-main\">
                <span class=\"rank-pred\">{r['pred']:.2f}<small>%</small></span>
                <span class=\"rank-delta\">{delta_txt}</span>
              </div>
              <div class=\"rank-sub\">RMSE {rmse_txt} <span class=\"metric-tooltip\" tabindex=\"0\" aria-label=\"RMSE 설명\" data-tip=\"RMSE는 예측값과 실제값 차이의 평균적인 크기를 뜻하며 낮을수록 정확합니다.\">ⓘ</span></div>
              <div class=\"rank-band\">{band_txt}</div>
              <div class=\"spark\">{r['spark_svg']}</div>
            </article>
            """
        )
    if not ranking_html:
        ranking_html.append(
            """
            <article class=\"rank-card muted\">
              <div class=\"rank-head\">
                <div class=\"rank-party\">예측 랭킹 데이터 준비 중</div>
              </div>
              <div class=\"rank-sub\">예측 산출물이 갱신되면 자동으로 표시됩니다.</div>
            </article>
            """
        )

    article_cards = []
    for _, a in articles_df.iterrows():
        d = pd.to_datetime(a.get("published_at", a["date"]), errors="coerce")
        dtxt = d.strftime("%Y-%m-%d %H:%M") if pd.notna(d) else pd.to_datetime(a["date"]).strftime("%Y-%m-%d")
        source = str(a.get("source", "")).strip() or "출처"
        title = str(a.get("title", "")).strip()
        url = str(a.get("url", "")).strip()
        article_cards.append(
            f"""
            <a class=\"news-card link-out\" href=\"{url}\" target=\"_blank\" rel=\"noopener noreferrer\">
              <div class=\"news-date\">{dtxt}</div>
              <div class=\"news-title\">{title}</div>
              <div class=\"news-source\">{source}</div>
            </a>
            """
        )

    pres_rows_html = []
    for r in president_table_rows:
        publisher = str(r["publisher"])
        p_color = pollster_color(publisher)
        src = "-"
        if r["source_url"]:
            label = r["source_title"] if r["source_title"] else "링크"
            src = f'<a class="ext-link" href="{r["source_url"]}" target="_blank" rel="noopener noreferrer">{label}</a>'
        period = f'{r["week_start"]} ~ {r["week_end"]}' if r["week_end"] else r["week_start"]
        pres_rows_html.append(
            f"""
            <tr>
              <td>{period}</td>
              <td>{r['approve']:.1f}</td>
              <td>{r['disapprove']:.1f}</td>
              <td><span class="pollster-chip" style="background:{p_color};"></span>{publisher}</td>
              <td>{src}</td>
            </tr>
            """
        )
    if not pres_rows_html:
        pres_rows_html.append("<tr><td colspan='5'>대통령 주간 데이터가 없습니다.</td></tr>")

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

    payload_json = json.dumps(
        {
            "traces": traces,
            "president_raw": president_raw_series,
            "latest_poll_results": latest_poll_results,
            "pollster_color_map": POLLSTER_COLOR_MAP,
        },
        ensure_ascii=False,
    )
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
    if backtest_overall.get("ssm_exog_mae") is not None:
        ssm_exog_mae = backtest_overall.get("ssm_exog_mae")
        improve_exog = backtest_overall.get("improvement_exog_pct")
        if ssm_exog_mae is not None and improve_exog is not None:
            backtest_note += (
                f" 외생변수(대통령 긍정지표) 포함 시 MAE는 {ssm_exog_mae:.3f}, "
                f"ssm 대비 개선율은 {improve_exog:+.2f}%입니다."
            )
    pres_method_note = (
        "대통령 국정수행 평가는 NESDC 공개 XLSX에서 문항(대통령/국정/직무/수행/평가)을 자동 탐지해 "
        "긍정·부정·유보를 추출하고, 표본수 가중 주간 집계로 반영합니다. 데이터가 없는 주차는 보간하지 않습니다."
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
  <div class=\"app-bg\">
  <div class=\"wrap container\">
    <header class=\"top section-tight\">
      <div class=\"brand\"><div class=\"logo\" aria-hidden=\"true\"></div><div class=\"title\">Weekly Korean Poll Tracker</div></div>
      <div class=\"top-meta\">
        <div id=\"freshness-badge\" class=\"freshness-badge stale\" aria-live=\"polite\">최신성 계산 중...</div>
        <div class=\"theme-toggle\" role=\"group\" aria-label=\"테마 선택\">
          <button class=\"theme-btn\" type=\"button\" data-theme=\"light\" aria-pressed=\"false\">라이트</button>
          <button class=\"theme-btn\" type=\"button\" data-theme=\"dark\" aria-pressed=\"false\">다크</button>
          <button class=\"theme-btn\" type=\"button\" data-theme=\"system\" aria-pressed=\"false\">시스템</button>
        </div>
      </div>
      <div class=\"time-banner-row\">
        <div id=\"stamp\" class=\"time-banner\" data-latest-date=\"{latest_date}\" data-updated-at=\"{datetime.now(tz=ZoneInfo('Asia/Seoul')).isoformat()}\">최신 조사 반영일 {latest_date} · 페이지 갱신 {now_kst}</div>
      </div>
    </header>

    <section class=\"insights section-tight\">
      <div class=\"panel-title\">핵심 지표 <small>Key Metrics</small></div>
      <div class=\"insights-cards\">{cards_html}</div>
    </section>

    <section class=\"main-grid section-tight\">
      <article class=\"panel chart-panel\">
        <div class=\"accent-line\" aria-hidden=\"true\"></div>
        <div class=\"panel-h\">
          <div class=\"panel-title-wrap\">
            <div class=\"panel-title\">정당 지지율 추세 + 다음주 예측치 <small>Party Trend & Next-Week Forecast</small></div>
            <button class=\"panel-help\" type=\"button\" title=\"실선은 최근 추세, 점선은 다음주 예측, 다이아는 최신 실측값입니다.\" aria-label=\"차트 도움말\">i</button>
          </div>
          <div class=\"filters\">
            <div class=\"range-group\" role=\"group\" aria-label=\"시간 범위\">
              <button class=\"btn btn-sm ghost fbtn active\" data-range=\"3m\" aria-pressed=\"true\">3M</button>
              <button class=\"btn btn-sm ghost fbtn\" data-range=\"6m\" aria-pressed=\"false\">6M</button>
              <button class=\"btn btn-sm ghost fbtn\" data-range=\"1y\" aria-pressed=\"false\">1Y</button>
              <button class=\"btn btn-sm ghost fbtn\" data-range=\"all\" aria-pressed=\"false\">All</button>
            </div>
            <div class=\"toggle-group\" role=\"group\" aria-label=\"보조 컨트롤\">
              <button class=\"btn btn-sm soft fbtn active\" id=\"toggle-band\" type=\"button\" aria-pressed=\"true\">오차 범위 표시: 켜짐</button>
              <button class=\"btn btn-sm ghost fbtn\" data-range=\"reset\" type=\"button\">정당 강조 해제</button>
            </div>
          </div>
        </div>
        <div class=\"chart-legend-note chart-legend-top\">
          <span class=\"legend-chip\"><span class=\"dot-open\" aria-hidden=\"true\"></span>예측치(빈 원)</span>
          <span class=\"legend-chip\"><span class=\"dot-diamond\" aria-hidden=\"true\"></span>최신 조사(다이아)</span>
          <span class=\"legend-chip\">색상 + 도형으로 구분 (색맹친화 보강)</span>
        </div>
        <div id=\"chart\"></div>
        <div class=\"chart-caption\"><strong>해석 안내:</strong> 각 선에는 스무딩 중심선과 적응형 오차폭 기반 반투명 밴드가 함께 표시됩니다(기준 오차폭 약 ±3%). 대통령 긍정/부정은 보정되지 않은 raw 값입니다.</div>
        <div class=\"disclosure-note\">선거여론조사 관련 세부사항은 중앙선거여론조사심의위원회 홈페이지(nesdc.go.kr) 참조.</div>
      </article>
      <aside class=\"panel\"><div class=\"panel-title card-header\">예측 랭킹 <small>Forecast Ranking</small></div><div class=\"rank-wrap card-body\">{''.join(ranking_html)}</div></aside>
    </section>

    <section id=\"section-news\" class=\"panel section-tight\">
      <div class=\"section-title-row card-header\">
        <div class=\"panel-title\" style=\"margin: 0;\">최근 여론조사 기사 링크 <small>Recent Coverage</small></div>
        <div id=\"news-status\" class=\"status-badge stale\" aria-live=\"polite\">대기 중...</div>
      </div>
      <div id=\"news-grid\" class=\"news-grid card-body\">{''.join(article_cards)}</div>
    </section>

    <section id=\"latest-poll-section\" class=\"latest-poll section-tight\">
      <div class=\"panel-title card-header\">최신 여론조사 결과 <small>Latest Poll Snapshot</small></div>
      <div class=\"latest-poll-grid\">
        <article class=\"panel\"><div id=\"latest-poll-chart\"></div></article>
        <article class=\"panel\"><div id=\"latest-poll-list\" class=\"latest-poll-list\"></div></article>
      </div>
    </section>

    <section id=\"poll-compare-section\" class=\"poll-compare section-tight\">
      <div class=\"panel-title card-header\">예측치 대비 최신 여론조사 차이 <small>Forecast vs Latest Poll</small></div>
      <div class=\"poll-compare-grid\">
        <article class=\"panel\"><div id=\"poll-compare-chart\"></div></article>
        <article class=\"panel\"><div id=\"poll-compare-list\" class=\"poll-compare-list\"></div></article>
      </div>
    </section>

    <section class=\"results-grid section\">
      <article class=\"panel\">
        <div class=\"panel-title card-header\">대통령 국정수행 주간 표 <small>Weekly Presidential Approval Table</small></div>
        <div class=\"table-scroll\">
          <table class=\"table\">
            <thead>
              <tr><th>조사기간(주차)</th><th>긍정(%)</th><th>부정(%)</th><th>조사기관</th><th>출처</th></tr>
            </thead>
            <tbody>{''.join(pres_rows_html)}</tbody>
          </table>
        </div>
      </article>
    </section>

    <section class=\"method\">
      <details>
        <summary>방법론 (클릭하여 펼치기)</summary>
        <p class=\"method-p\">2023년부터 2025년 6월 선거까지, 여론조사기관의 정당지지율과 실제 선거결과를 비교해 정확도(MAE)를 산출했습니다. 이후 정확도 상위 클러스터(9개 기관)만 사용해 합성 시계열을 만들고, 기관별 가중치는 1/MAE를 정규화해 적용합니다. 주간 업데이트에서는 Huber 손실 기반으로 가중치 안정성을 유지하도록 설계했습니다.</p>
        <p class=\"method-p\">{pres_method_note}</p>
        <p class=\"method-p\">{backtest_note}</p>
        <table class=\"table\"><thead><tr><th>조사기관</th><th>MAE</th><th>가중치(%)</th></tr></thead><tbody>{''.join(weight_rows)}</tbody></table>
      </details>
    </section>
  </div>
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
        published_at = pd.to_datetime(a.get("published_at"), errors="coerce")
        if pd.isna(published_at):
            dt_fallback = pd.to_datetime(a.get("date"), errors="coerce")
            published_str = dt_fallback.strftime("%Y-%m-%dT00:00:00+09:00") if pd.notna(dt_fallback) else ""
        else:
            published_str = published_at.isoformat()
        news_payload.append(
            {
                "date": pd.to_datetime(a["date"]).strftime("%Y-%m-%d"),
                "source": str(a.get("source", "")),
                "title": str(a.get("title", "")),
                "url": str(a.get("url", "")),
                "published_at": published_str,
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
    president_overall = load_president_approval_overall(outputs)
    president_raw_series = load_president_approval_raw_series(outputs)
    president_table_rows = load_president_approval_table_rows(outputs)
    latest_poll_results = load_latest_poll_results(outputs)
    traces, ranking_rows, nowcast_rows, nowcast_meta = build_party_payload(
        blended, forecast, as_of_kst=datetime.now(tz=ZoneInfo("Asia/Seoul"))
    )

    latest_date = str(pd.to_datetime(blended["date_end"]).max().date())
    render_html(
        docs,
        traces,
        ranking_rows,
        nowcast_rows,
        nowcast_meta,
        weights,
        articles,
        latest_date=latest_date,
        backtest_overall=backtest_overall,
        president_overall=president_overall,
        president_raw_series=president_raw_series,
        president_table_rows=president_table_rows,
        latest_poll_results=latest_poll_results,
    )
    print(f"News source: {news_source}, rows={len(articles)}")
    print("Wrote docs/index.html, docs/style.css, docs/app.js")


if __name__ == "__main__":
    main()
