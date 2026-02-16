from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from zoneinfo import ZoneInfo
from datetime import datetime

import pandas as pd


def run_cmd(cmd: list[str], cwd: Path) -> None:
    print('RUN:', ' '.join(cmd))
    subprocess.run(cmd, cwd=str(cwd), check=True)


def compute_feedback(base: Path, pre_forecast: pd.DataFrame | None, pre_last_date: pd.Timestamp | None) -> None:
    out_dir = base / 'outputs'
    wt = pd.read_excel(out_dir / 'weighted_time_series.xlsx', sheet_name='weighted_time_series')
    wt['date_end'] = pd.to_datetime(wt['date_end'])
    new_last = wt['date_end'].max()

    if pre_forecast is None or pre_last_date is None:
        msg = 'No pre-forecast snapshot found. Feedback skipped.'
        (out_dir / 'feedback_latest.md').write_text(msg + '\n', encoding='utf-8')
        print(msg)
        return

    target = pre_last_date + pd.Timedelta(days=7)
    if target.date() != new_last.date():
        msg = (
            f'Feedback skipped: expected actual date {target.date()} from prior forecast, '
            f'but latest actual date is {new_last.date()}.'
        )
        (out_dir / 'feedback_latest.md').write_text(msg + '\n', encoding='utf-8')
        print(msg)
        return

    row = wt[wt['date_end'] == new_last].iloc[-1]
    pre = pre_forecast.copy()
    pre['party'] = pre['party'].astype(str)
    pre['next_week_pred'] = pd.to_numeric(pre['next_week_pred'], errors='coerce')

    rows = []
    for _, r in pre.iterrows():
        p = r['party']
        if p in row.index and pd.notna(row[p]) and pd.notna(r['next_week_pred']):
            actual = float(row[p])
            pred = float(r['next_week_pred'])
            err = actual - pred
            rows.append({'party': p, 'pred': pred, 'actual': actual, 'error': err, 'abs_error': abs(err)})

    if not rows:
        msg = 'Feedback skipped: no overlapping party columns.'
        (out_dir / 'feedback_latest.md').write_text(msg + '\n', encoding='utf-8')
        print(msg)
        return

    fdf = pd.DataFrame(rows).sort_values('abs_error', ascending=False)
    fdf.to_csv(out_dir / 'feedback_latest.csv', index=False)

    mae = float(fdf['abs_error'].mean())
    lines = [
        f'# Feedback Report ({new_last.date()})',
        '',
        f'- Previous forecast target date: {target.date()}',
        f'- Actual available date: {new_last.date()}',
        f'- MAE: {mae:.3f}',
        '',
        '## Party-level error (actual - pred)',
    ]
    for _, r in fdf.iterrows():
        lines.append(f"- {r['party']}: pred {r['pred']:.2f}, actual {r['actual']:.2f}, error {r['error']:+.2f}")
    (out_dir / 'feedback_latest.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('Wrote feedback_latest.csv / feedback_latest.md')


def main() -> None:
    base = Path(__file__).resolve().parents[1]
    py = sys.executable

    now_kst = datetime.now(tz=ZoneInfo('Asia/Seoul'))
    today_kst = pd.Timestamp(now_kst.date())
    print('KST now:', now_kst.strftime('%Y-%m-%d %H:%M:%S %Z'))

    # Tuesday=1 in pandas weekday
    if today_kst.weekday() != 1:
        print('Not Tuesday KST. Skip NESDC Tuesday flow.')
        return

    pre_forecast = None
    pre_last_date = None
    fc_path = base / 'outputs' / 'forecast_next_week.xlsx'
    wt_path = base / 'outputs' / 'weighted_time_series.xlsx'
    if fc_path.exists() and wt_path.exists():
        pre_forecast = pd.read_excel(fc_path)
        pre_wt = pd.read_excel(wt_path, sheet_name='weighted_time_series')
        pre_wt['date_end'] = pd.to_datetime(pre_wt['date_end'])
        pre_last_date = pre_wt['date_end'].max()

    d = today_kst.strftime('%Y-%m-%d')
    run_cmd([py, 'src/fetch_nesdc_weekly.py', '--week-start', d, '--week-end', d, '--pages', '3'], base)

    manifest = base / 'outputs' / 'nesdc_fetch_manifest.csv'
    if not manifest.exists():
        print('Manifest not found. Stop.')
        return
    mf = pd.read_csv(manifest)
    if mf.empty:
        print('No attachments fetched for today. Retry next scheduled run.')
        return

    mf['posted_date'] = pd.to_datetime(mf['posted_date'], errors='coerce')
    has_today_post = (mf['posted_date'].dt.date == today_kst.date()).any()
    if not has_today_post:
        print('No today post found. Retry next scheduled run.')
        return

    has_xlsx = ((mf['posted_date'].dt.date == today_kst.date()) & (mf['is_xlsx'] == True)).any()
    if not has_xlsx:
        print('Today post exists but no xlsx attachment. Keep waiting for next run.')
        return

    run_cmd([py, 'src/apply_nesdc_weekly_update.py', '--rebuild'], base)
    compute_feedback(base, pre_forecast, pre_last_date)


if __name__ == '__main__':
    main()
