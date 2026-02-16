from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib.pyplot as plt
import pandas as pd

PLOT_LABEL_MAP = {
    "더불어민주당": "Democratic Party",
    "국민의힘": "People Power Party",
    "조국혁신당": "Rebuilding Korea Party",
    "개혁신당": "Reform Party",
    "진보당": "Progressive Party",
    "기타정당": "Other Parties",
    "지지정당\n없음": "No Party",
    "모름/\n무응답": "Undecided/No response",
}


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


def pick_top_parties(blended: pd.DataFrame, n: int = 5) -> list[str]:
    cols = [c for c in blended.columns if c not in {"date_end", "n_polls"}]
    last = blended.sort_values("date_end").iloc[-1]
    ranked = sorted(cols, key=lambda c: float(last.get(c, 0.0) if pd.notna(last.get(c, 0.0)) else 0.0), reverse=True)
    return ranked[:n]


def draw_trend(blended: pd.DataFrame, out_png: Path) -> None:
    df = blended.copy()
    df["date_end"] = pd.to_datetime(df["date_end"])
    df = df.sort_values("date_end")

    parties = pick_top_parties(df, n=5)
    plt.figure(figsize=(12, 6))
    for p in parties:
        plt.plot(df["date_end"], df[p], label=PLOT_LABEL_MAP.get(p, p), linewidth=2)

    plt.title("Weighted Poll Trend (Top 5 Parties)")
    plt.xlabel("Date")
    plt.ylabel("Support (%)")
    plt.grid(alpha=0.2)
    plt.legend()
    plt.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_png, dpi=160)
    plt.close()


def draw_forecast(forecast: pd.DataFrame, out_png: Path) -> pd.DataFrame:
    df = forecast.copy()
    df["next_week_pred"] = pd.to_numeric(df["next_week_pred"], errors="coerce")
    df = df.dropna(subset=["next_week_pred"]).sort_values("next_week_pred", ascending=False)

    plt.figure(figsize=(12, 6))
    labels = [PLOT_LABEL_MAP.get(str(p), str(p)) for p in df["party"]]
    plt.bar(labels, df["next_week_pred"])
    plt.title("Next Week Forecast")
    plt.xlabel("Party")
    plt.ylabel("Predicted Support (%)")
    plt.xticks(rotation=25, ha="right")
    plt.grid(axis="y", alpha=0.2)
    plt.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_png, dpi=160)
    plt.close()
    return df


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

  <h2>합성 추세 (상위 5개 정당)</h2>
  <img src="assets/trend_top5.png" alt="Trend chart" />

  <h2>다음 주 예측</h2>
  <img src="assets/forecast_next_week.png" alt="Forecast chart" />

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

    draw_trend(blended, assets / "trend_top5.png")
    sorted_fc = draw_forecast(forecast, assets / "forecast_next_week.png")

    latest_date = str(pd.to_datetime(blended["date_end"]).max().date())
    render_html(docs, sorted_fc, latest_date=latest_date)
    print("Wrote docs/index.html")


if __name__ == "__main__":
    main()
