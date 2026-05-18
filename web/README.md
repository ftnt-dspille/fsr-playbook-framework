# FSR Playbook Studio

Browser app for live LLM-driven FortiSOAR playbook authoring.

See `PLAN.md` for the design. See `../docs/archive/CHAT_APP_PLAN.md` for inherited LLM-context strategy.

## Layout

```
web/
  backend/    FastAPI, imports ../python/ in-process
  frontend/   SvelteKit (Svelte 5 runes) + Monaco + Tailwind
  data/       SQLite + .env (gitignored)
```

## Dev

Backend (from `web/`):
```
uv pip install -e .[web]      # or: pip install fastapi uvicorn sse-starlette anthropic
uvicorn backend.app:app --reload --port 47821
```

Frontend (from `web/frontend/`):
```
pnpm install
pnpm dev          # http://localhost:47822, proxies /api → :47821
```

Health check: open `http://localhost:47822` — the header pill should go green when both processes are up.
