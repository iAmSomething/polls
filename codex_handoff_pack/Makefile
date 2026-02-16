PYTHON ?= python3
VENV ?= .venv
VENV_PY := $(VENV)/bin/python
VENV_PIP := $(VENV)/bin/pip

.PHONY: setup smoke run-forecast run-pipeline run-weekly run-issues build-site fetch-nesdc apply-nesdc run-tuesday clean

setup:
	$(PYTHON) -m venv $(VENV)
	$(VENV_PIP) install --upgrade pip
	$(VENV_PIP) install -r requirements.txt

smoke:
	$(VENV_PY) -c "import numpy, pandas, openpyxl, matplotlib; print('smoke ok')"

run-pipeline:
	$(VENV_PY) src/pipeline.py

run-forecast:
	$(VENV_PY) src/forecast.py

run-weekly:
	$(VENV_PY) src/weekly_run.py

run-issues:
	$(VENV_PY) src/issues.py

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
