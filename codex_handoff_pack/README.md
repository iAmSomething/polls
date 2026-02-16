# Codex Handoff Pack

This folder contains:
- HANDOFF.md: full context, rules, decisions, and outputs
- src/: runnable skeleton code to reproduce the pipeline
- outputs/: latest artifacts copied here for convenience

## Quick Start

```bash
cd codex_handoff_pack
make setup
make smoke
```

## Run

```bash
cd codex_handoff_pack
make run-pipeline
make run-forecast
make run-weekly
make run-issues
```

`pipeline.py` input resolution:
- If no args are passed, it auto-selects `.xlsx` files under `data/` (newest first, prefers filename keywords `input` and `accuracy`).
- You can explicitly set files:

```bash
.venv/bin/python src/pipeline.py \
  --input-xlsx "your_raw_poll_file.xlsx" \
  --mae-xlsx "your_mae_file.xlsx"
```

## Weekly Policy (Selected)

- Schedule: Monday 09:00
- Timezone: `Asia/Seoul`
- Weight-update loss: `Huber`
- Scraping scope: text-only full party breakdown

## Midweek Issue Input

Use:
- `data/issues_input.csv`
- `config/issue_coefficients.csv`

Schema (`data/issues_input.csv`):
- `issue_date` (YYYY-MM-DD)
- `issue_type` (e.g., 경제/안보/사법/인사/부패/비리/정책성과/사고/참사)
- `intensity` (0~3)
- `direction`
- `persistence`
- `target_party`
- `note`

Quick check:

```bash
cd codex_handoff_pack
make run-issues
```

## Required Input Files

- `data/input.xlsx`
- `data/pollster_accuracy_clusters_2024_2025.xlsx`

## Issue Impact Policy

- Current mode: `collect-only` (no live forecast impact).
- Policy file: `config/issue_policy.json`
- Activation condition: apply issue impact only after enough evaluation history and measurable accuracy gain.

## AI Issue Assessment (LLM)

Use LLM mode for party advantage/disadvantage scoring from weekly news:

```bash
cd codex_handoff_pack
export OPENAI_API_KEY="<your-key>"
.venv/bin/python src/issue_intake.py \
  --mode llm \
  --week-start 2026-02-09 \
  --week-end 2026-02-15 \
  --keywords "정당 지지율,여론조사,민주당,국민의힘"
```

- If `OPENAI_API_KEY` is missing or API fails, it falls back to rule-based scoring.
- Current forecast policy remains `collect-only` until evaluation thresholds are met.

Perplexity API usage:

```bash
cd codex_handoff_pack
export PPLX_API_KEY="<your-key>"
.venv/bin/python src/issue_intake.py \
  --mode llm \
  --llm-provider perplexity \
  --llm-model sonar \
  --week-start 2026-02-09 \
  --week-end 2026-02-15 \
  --keywords "정당 지지율,여론조사,민주당,국민의힘"
```
