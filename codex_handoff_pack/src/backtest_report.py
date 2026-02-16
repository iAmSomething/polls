from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from forecast import detect_regime_shift, forecast_next, forecast_next_ssm, to_weekly


def _clean_party_label(s: str) -> str:
    return str(s).replace("\n", " ").strip()


def run_backtest(
    weekly: pd.DataFrame,
    min_train_weeks: int = 20,
    window_weeks: int = 24,
    horizon_weeks: int = 1,
    regime_guard: bool = True,
    regime_q_scale: float = 2.0,
) -> pd.DataFrame:
    rows: list[dict] = []
    party_cols = [c for c in weekly.columns]
    if len(weekly) < min_train_weeks + horizon_weeks + 1:
        return pd.DataFrame(columns=["date", "party", "model", "actual", "pred", "error", "abs_error", "sq_error", "triggered"])

    for t in range(min_train_weeks, len(weekly) - horizon_weeks + 1):
        train = weekly.iloc[:t]
        actual_row = weekly.iloc[t + horizon_weeks - 1]
        regime = detect_regime_shift(train) if regime_guard else {"triggered": False}
        q_scale = regime_q_scale if regime.get("triggered", False) else 1.0
        dt = weekly.index[t + horizon_weeks - 1]

        for party in party_cols:
            actual = pd.to_numeric(actual_row.get(party), errors="coerce")
            if pd.isna(actual):
                continue
            s_train = pd.to_numeric(train[party], errors="coerce").dropna()
            if len(s_train) < 8:
                continue

            pred_legacy, _ = forecast_next(
                s_train, horizon_weeks=horizon_weeks, window_weeks=window_weeks
            )
            pred_ssm, _, _ = forecast_next_ssm(
                s_train,
                horizon_weeks=horizon_weeks,
                window_weeks=window_weeks,
                q_scale=q_scale,
            )
            for model, pred in [("legacy", pred_legacy), ("ssm", pred_ssm)]:
                err = float(actual - pred)
                rows.append(
                    {
                        "date": dt,
                        "party": _clean_party_label(party),
                        "model": model,
                        "actual": float(actual),
                        "pred": float(pred),
                        "error": err,
                        "abs_error": abs(err),
                        "sq_error": err * err,
                        "triggered": bool(regime.get("triggered", False)),
                    }
                )
    return pd.DataFrame(rows)


def build_summary(preds: pd.DataFrame) -> pd.DataFrame:
    if preds.empty:
        return pd.DataFrame(columns=["level", "party", "model", "n", "mae", "rmse", "hit_rate"])

    overall = (
        preds.groupby("model", as_index=False)
        .agg(
            n=("abs_error", "size"),
            mae=("abs_error", "mean"),
            rmse=("sq_error", lambda x: float(np.sqrt(np.mean(x)))),
            hit_rate=("error", lambda x: float(np.mean(np.sign(x) == np.sign(x.shift(1).fillna(0))))),
        )
        .assign(level="overall", party="ALL")
    )

    by_party = (
        preds.groupby(["party", "model"], as_index=False)
        .agg(
            n=("abs_error", "size"),
            mae=("abs_error", "mean"),
            rmse=("sq_error", lambda x: float(np.sqrt(np.mean(x)))),
            hit_rate=("error", lambda x: float(np.mean(np.sign(x) == np.sign(x.shift(1).fillna(0))))),
        )
        .assign(level="party")
    )
    return pd.concat([overall, by_party], ignore_index=True)[
        ["level", "party", "model", "n", "mae", "rmse", "hit_rate"]
    ]


def write_markdown(summary: pd.DataFrame, out_md: Path) -> None:
    lines = ["# Backtest Report", ""]
    if summary.empty:
        lines += ["No backtest rows generated.", ""]
        out_md.write_text("\n".join(lines), encoding="utf-8")
        return

    o = summary[(summary["level"] == "overall")].copy()
    if not o.empty and {"legacy", "ssm"}.issubset(set(o["model"])):
        legacy_mae = float(o[o["model"] == "legacy"]["mae"].iloc[0])
        ssm_mae = float(o[o["model"] == "ssm"]["mae"].iloc[0])
        improve = (legacy_mae - ssm_mae) / legacy_mae * 100.0 if legacy_mae > 0 else 0.0
        lines += [
            f"- Overall MAE legacy: **{legacy_mae:.3f}**",
            f"- Overall MAE ssm: **{ssm_mae:.3f}**",
            f"- Improvement (legacy -> ssm): **{improve:+.2f}%**",
            "",
        ]

    lines += ["## Overall", "", "| Model | N | MAE | RMSE | Hit Rate |", "|---|---:|---:|---:|---:|"]
    for _, r in o.sort_values("mae").iterrows():
        lines.append(
            f"| {r['model']} | {int(r['n'])} | {float(r['mae']):.3f} | {float(r['rmse']):.3f} | {float(r['hit_rate']):.3f} |"
        )

    p = summary[summary["level"] == "party"].copy()
    lines += ["", "## By Party", "", "| Party | Model | N | MAE | RMSE |", "|---|---|---:|---:|---:|"]
    for _, r in p.sort_values(["party", "mae"]).iterrows():
        lines.append(
            f"| {r['party']} | {r['model']} | {int(r['n'])} | {float(r['mae']):.3f} | {float(r['rmse']):.3f} |"
        )

    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description="Run rolling one-step backtest: legacy vs ssm forecast.")
    ap.add_argument("--blended-xlsx", default="outputs/weighted_time_series.xlsx")
    ap.add_argument("--min-train-weeks", type=int, default=20)
    ap.add_argument("--window-weeks", type=int, default=24)
    ap.add_argument("--horizon-weeks", type=int, default=1)
    ap.add_argument("--regime-guard", choices=["on", "off"], default="on")
    ap.add_argument("--regime-q-scale", type=float, default=2.0)
    ap.add_argument("--out-preds", default="outputs/backtest_predictions.csv")
    ap.add_argument("--out-summary", default="outputs/backtest_summary.csv")
    ap.add_argument("--out-report", default="outputs/backtest_report.md")
    args = ap.parse_args()

    blended_path = Path(args.blended_xlsx)
    if not blended_path.exists():
        raise FileNotFoundError(f"Blended file not found: {blended_path}")
    blended = pd.read_excel(blended_path)
    weekly = to_weekly(blended)

    preds = run_backtest(
        weekly=weekly,
        min_train_weeks=args.min_train_weeks,
        window_weeks=args.window_weeks,
        horizon_weeks=args.horizon_weeks,
        regime_guard=(args.regime_guard == "on"),
        regime_q_scale=args.regime_q_scale,
    )
    summary = build_summary(preds)

    out_preds = Path(args.out_preds)
    out_summary = Path(args.out_summary)
    out_report = Path(args.out_report)
    out_preds.parent.mkdir(parents=True, exist_ok=True)
    preds.to_csv(out_preds, index=False)
    summary.to_csv(out_summary, index=False)
    write_markdown(summary, out_report)

    print("Wrote:", out_preds)
    print("Wrote:", out_summary)
    print("Wrote:", out_report)
    if not summary.empty:
        print(summary[summary["level"] == "overall"].sort_values("mae").to_string(index=False))


if __name__ == "__main__":
    main()
