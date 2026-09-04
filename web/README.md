# OrgTwin Web

Vite + React + React Flow. Язык UI — только русский.

## Dev

```bash
# из корня репо — API
.venv/bin/uvicorn apps.api.main:app --reload --app-dir . --port 8000

# UI
cd web && npm install && npm run dev
```

Прокси: `/api` → `http://127.0.0.1:8000`.

## Production

```bash
npm run build
# статика в dist/; FastAPI отдаёт её, если dist существует
# или docker compose из корня репо
```
