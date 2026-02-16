# Poll Project

Automated weighted poll blending + weekly forecast dashboard.

## Local Run

```bash
cd codex_handoff_pack
make setup
python src/pipeline.py
python src/forecast.py
python src/generate_site.py
```

Generated site:
- `codex_handoff_pack/docs/index.html`

## GitHub Pages

Workflow file:
- `.github/workflows/pages.yml`

Schedule:
- Every Monday 09:00 Asia/Seoul (`0 0 * * 1` UTC)

Required repo setting:
1. Settings -> Pages -> Build and deployment
2. Source: `GitHub Actions`

