from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib.pyplot as plt
from matplotlib import font_manager
import pandas as pd

PARTY_STYLES = {
    "더불어민주당": {"color": "#6EC1E4", "aliases": ["더불어민주당"]},
    "국민의힘": {"color": "#E6002D", "aliases": ["국민의힘", "국민의 힘"]},
    "지지정당 없음": {"color": "#7A7A7A", "aliases": ["지지정당\n없음", "지지정당 없음", "무당층"]},
    "개혁신당": {"color": "#F18D00", "aliases": ["개혁신당"]},
    "조국혁신당": {"color": "#003A8C", "aliases": ["조국혁신당"]},
}
PARTY_ORDER = ["더불어민주당", "국민의힘", "지지정당 없음", "개혁신당", "조국혁신당"]


def setup_korean_font() -> None:
    # Keep deterministic order for CI and local environments.
    for font_name in ["NanumGothic", "AppleGothic", "Malgun Gothic", "Noto Sans CJK KR"]:
        try:
            font_manager.findfont(font_name, fallback_to_default=False)
            plt.rcParams["font.family"] = font_name
            break
        except Exception:
            continue
    plt.rcParams["axes.unicode_minus"] = False


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
        return pd.read_excel(p)

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


def draw_trend_with_forecast(blended: pd.DataFrame, forecast: pd.DataFrame, out_png: Path) -> pd.DataFrame:
    df = blended.copy()
    df["date_end"] = pd.to_datetime(df["date_end"])
    df = df.sort_values("date_end")
    df = df.rename(columns={c: canonical_party_name(c) for c in df.columns})

    fc = forecast.copy()
    fc["party"] = fc["party"].map(canonical_party_name)
    fc["next_week_pred"] = pd.to_numeric(fc["next_week_pred"], errors="coerce")
    fc = fc.dropna(subset=["next_week_pred"])

    setup_korean_font()
    plt.figure(figsize=(12, 6))
    pred_date = pd.to_datetime(df["date_end"]).max() + pd.Timedelta(days=7)
    rows = []
    for party in PARTY_ORDER:
        if party not in df.columns:
            continue
        color = PARTY_STYLES[party]["color"]
        s = pd.to_numeric(df[party], errors="coerce")
        plt.plot(df["date_end"], s, label=party, linewidth=2.4, color=color)

        last_idx = s.last_valid_index()
        if last_idx is None:
            continue
        last_date = pd.to_datetime(df.loc[last_idx, "date_end"])
        last_y = float(s.loc[last_idx])
        pred_row = fc[fc["party"] == party]
        if pred_row.empty:
            continue
        pred_y = float(pred_row.iloc[0]["next_week_pred"])
        rmse_v = pred_row.iloc[0].get("rmse")
        rmse_txt = f"{float(rmse_v):.2f}" if pd.notna(rmse_v) else "-"

        plt.plot([last_date, pred_date], [last_y, pred_y], linestyle="--", linewidth=1.8, color=color, alpha=0.9)
        plt.scatter([pred_date], [pred_y], color=color, s=70, marker="D", edgecolors="black", linewidths=0.5, zorder=5)
        plt.text(pred_date, pred_y, " 예측치", fontsize=9, color=color, va="center")
        rows.append({"party": party, "next_week_pred": pred_y, "rmse": rmse_txt})

    plt.title("주간 여론 합성 추세 + 다음주 예측치")
    plt.xlabel("조사 종료일")
    plt.ylabel("지지율(%)")
    plt.grid(alpha=0.2)
    plt.legend()
    plt.xlim(pd.to_datetime(df["date_end"]).min(), pred_date + pd.Timedelta(days=2))
    plt.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_png, dpi=160)
    plt.close()
    return pd.DataFrame(rows).sort_values("next_week_pred", ascending=False)


def render_html(docs_dir: Path, forecast_sorted: pd.DataFrame, latest_date: str) -> None:
    now_kst = datetime.now(tz=ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S %Z")
    rows = []
    for _, r in forecast_sorted.iterrows():
        party = str(r["party"])
        pred = float(r["next_week_pred"])
        rmse = r.get("rmse")
        rmse_txt = f"{float(rmse):.2f}" if pd.notna(rmse) else "-"
        rows.append(f"<tr><td>{party}</td><td>{pred:.2f}</td><td>{rmse_txt}</td></tr>")

    html = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Poll Forecast Dashboard</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 24px; color: #1e293b; }}
    .meta {{ color: #475569; margin-bottom: 16px; }}
    img {{ width: 100%; max-width: 1100px; border: 1px solid #e2e8f0; border-radius: 8px; margin: 12px 0 24px; }}
    table {{ border-collapse: collapse; min-width: 420px; }}
    th, td {{ border: 1px solid #cbd5e1; padding: 8px 10px; text-align: right; }}
    th:first-child, td:first-child {{ text-align: left; }}
  </style>
</head>
<body>
  <h1>주간 여론 합성/예측 대시보드</h1>
  <div class="meta">최근 조사 반영일: {latest_date} | 페이지 갱신: {now_kst}</div>

  <h2>합성 추세 + 다음주 예측치(우측 마커)</h2>
  <img src="assets/trend_top5.png" alt="Trend chart" />

  <h3>예측 표</h3>
  <table>
    <thead><tr><th>정당</th><th>예측치(%)</th><th>RMSE</th></tr></thead>
    <tbody>
      {''.join(rows)}
    </tbody>
  </table>

  <p class="meta">정책: Huber 가중치 업데이트, 텍스트 공개값만 수집</p>
</body>
</html>
"""
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / "index.html").write_text(html, encoding="utf-8")


def main():
    base = Path(".")
    outputs = base / "outputs"
    docs = base / "docs"
    assets = docs / "assets"

    blended = load_blended(outputs)
    forecast = load_forecast(outputs)

    sorted_fc = draw_trend_with_forecast(blended, forecast, assets / "trend_top5.png")

    latest_date = str(pd.to_datetime(blended["date_end"]).max().date())
    render_html(docs, sorted_fc, latest_date=latest_date)
    print("Wrote docs/index.html")


if __name__ == "__main__":
    main()
