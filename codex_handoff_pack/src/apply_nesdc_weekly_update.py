from __future__ import annotations

import argparse
import hashlib
import subprocess
from pathlib import Path

import pandas as pd


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        while True:
            b = f.read(1024 * 1024)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def pick_latest_xlsx_from_manifest(manifest: Path) -> Path | None:
    if not manifest.exists():
        return None
    df = pd.read_csv(manifest)
    if df.empty:
        return None
    df = df[df['is_xlsx'] == True].copy()
    if df.empty:
        return None
    df['posted_date'] = pd.to_datetime(df['posted_date'], errors='coerce')
    df = df.sort_values(['posted_date', 'ntt_id'], ascending=[False, False])
    p = Path(str(df.iloc[0]['local_path']))
    return p if p.exists() else None


def run_cmd(cmd: list[str], cwd: Path) -> None:
    print('RUN:', ' '.join(cmd))
    subprocess.run(cmd, cwd=str(cwd), check=True)


def main() -> None:
    ap = argparse.ArgumentParser(description='Apply latest NESDC weekly xlsx and rebuild outputs')
    ap.add_argument('--manifest', default='outputs/nesdc_fetch_manifest.csv')
    ap.add_argument('--target-input', default='data/전국단위+선거여론조사결과의+주요+데이터(2023.10.30.~).xlsx')
    ap.add_argument('--rebuild', action='store_true', help='run pipeline/forecast/site after apply')
    args = ap.parse_args()

    base = Path(__file__).resolve().parents[1]
    manifest = base / args.manifest
    target_input = base / args.target_input

    src = pick_latest_xlsx_from_manifest(manifest)
    if src is None:
        print('No xlsx found in manifest. Nothing to apply.')
        return

    if not target_input.exists():
        target_input.parent.mkdir(parents=True, exist_ok=True)
        target_input.write_bytes(src.read_bytes())
        print(f'Applied new input xlsx: {src} -> {target_input}')
    else:
        old_hash = sha256(target_input)
        new_hash = sha256(src)
        if old_hash == new_hash:
            print('Latest NESDC xlsx is identical to current input. No file change.')
        else:
            backup = target_input.with_suffix(target_input.suffix + '.bak')
            backup.write_bytes(target_input.read_bytes())
            target_input.write_bytes(src.read_bytes())
            print(f'Updated input xlsx from NESDC attachment: {src} -> {target_input}')
            print(f'Backup written: {backup}')

    if args.rebuild:
        py = str(base / '.venv' / 'bin' / 'python')
        run_cmd([py, 'src/pipeline.py'], base)
        run_cmd([py, 'src/forecast.py'], base)
        run_cmd([py, 'src/generate_site.py'], base)
        print('Rebuild complete.')


if __name__ == '__main__':
    main()
