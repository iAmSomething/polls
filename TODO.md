# Poll Project TODO

Updated: 2026-02-16

## Immediate
- [x] Review handoff docs and source skeleton in `codex_handoff_pack/`.
- [x] Build reproducible Python runtime (`.venv`, dependencies install).
- [x] Run smoke tests for `src/pipeline.py`, `src/forecast.py`, `src/weekly_run.py`.
- [x] Document exact run commands and expected inputs/outputs.

## Data/Inputs
- [ ] Place raw source Excel in `codex_handoff_pack/data/` (any `.xlsx` filename is allowed).
- [ ] Place pollster MAE file in `codex_handoff_pack/data/` (any `.xlsx` filename is allowed).
- [ ] Verify required sheets exist:
  - `정당지지도 (25.1.1~12.31.)`
  - `정당지지도 (26.1.1~)`

## Pipeline Completion
- [ ] Implement scraper in `src/weekly_run.py::scrape_latest_public_points`.
- [ ] Implement constrained optimizer in `src/weekly_run.py::update_weights`.
- [ ] Add logging and weekly report output.
- [ ] Add regression tests for date parsing and blending math.

## Decision Needed (User)
- [x] Decide weekly run schedule and timezone for automation. -> selected: Monday 09:00, Asia/Seoul
- [x] Decide whether to include PDF/table parsing (higher effort) or text-only scraping. -> selected: text-only scraping
- [x] Decide loss for weight updates (`MAE` vs `Huber`). -> selected: Huber
