PYTHON ?= python3
VENV ?= .venv
VENV_PY := $(VENV)/bin/python
VENV_PIP := $(VENV)/bin/pip

.PHONY: setup smoke run-forecast run-backtest run-pipeline run-president run-pres-approval run-weekly run-issues build-site fetch-nesdc apply-nesdc run-tuesday issue-intake clean

setup:
	$(PYTHON) -m venv $(VENV)
	$(VENV_PIP) install --upgrade pip
	$(VENV_PIP) install -r requirements.txt

smoke:
	$(VENV_PY) -c "import numpy, pandas, openpyxl, matplotlib; print('smoke ok')"

run-pipeline:
	$(VENV_PY) src/pipeline.py

run-president:
	$(VENV_PY) src/president_approval_pipeline.py

run-pres-approval:
	$(VENV_PY) src/president_approval_scrape_weekly.py

run-forecast:
	$(VENV_PY) src/forecast.py --model ssm --regime-guard on --exog-approval on

run-backtest:
	$(VENV_PY) src/backtest_report.py --regime-guard on --exog-approval on

run-weekly:
	$(VENV_PY) src/weekly_run.py

run-issues:
	$(VENV_PY) src/issues.py

issue-intake:
	$(VENV_PY) src/issue_intake.py --mode llm --week-start 2026-02-09 --week-end 2026-02-15 --keywords "정당 지지율,여론조사,민주당,국민의힘"

fetch-nesdc:
	$(VENV_PY) src/fetch_nesdc_weekly.py

apply-nesdc:
	$(VENV_PY) src/apply_nesdc_weekly_update.py --rebuild

run-tuesday:
	$(VENV_PY) src/tuesday_18kst_runner.py

build-site:
	$(VENV_PY) src/generate_site.py

clean:
	rm -rf $(VENV)
