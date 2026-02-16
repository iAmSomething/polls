# GitHub Web Deployment Options

## Option 1 (Recommended): GitHub Pages + GitHub Actions (Static Dashboard)

When to choose:
- You want low cost (free), simple ops, and public sharing.
- You can publish charts/tables as static files (CSV/JSON/PNG/HTML).

Architecture:
1. Weekly/manual GitHub Action runs pipeline.
2. Action commits updated artifacts into `docs/` (or uploads + deploy branch).
3. GitHub Pages serves `docs/index.html`.

Pros:
- Free and stable
- Easy to version output history via Git
- No server maintenance

Cons:
- No backend API runtime
- Secrets/network scraping may need careful workflow setup

## Option 2: Streamlit Cloud / Render

When to choose:
- You need interactive filters and python-side rendering.

Pros:
- Fast to build interactive UI

Cons:
- Hosting limits/cost may apply
- More runtime dependency management

## Option 3: FastAPI + Frontend (Vercel/Netlify + API host)

When to choose:
- You need multi-user API, auth, or advanced productization.

Pros:
- Most flexible

Cons:
- Highest complexity and maintenance

## Recommended rollout

1. Start with Option 1 (Pages) now.
2. If interaction needs grow, migrate to Option 2.
3. Move to Option 3 only when product requirements justify backend complexity.

## What to publish on web (suggested)

- Latest blended time series chart
- Next-week forecast table
- Last run timestamp (Asia/Seoul)
- Data source policy note (text-only full-party breakdown)

