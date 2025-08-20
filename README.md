AI Research Assistant Backend

FastAPI backend for the AI Research Assistant Platform.
Provides REST and WebSocket endpoints, CORS, and environment-driven configuration.

Features:
- FastAPI app with health check (GET /health)
- CORS enabled (configurable via CORS_ORIGINS)
- WebSocket echo endpoint (/ws/echo) for realtime plumbing
- uv-based Python workflow with pyproject.toml

Requirements:
- Python 3.11+
- uv (https://docs.astral.sh/uv/)

Setup:
uv sync

Run (dev):
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

Env vars (.env example):
APP_ENV=development
API_PREFIX=/api
CORS_ORIGINS=http://localhost:5173
HOST=0.0.0.0
PORT=8000

---

## Database (Postgres via Docker Compose)
1. Copy `.env.example` to `.env` and adjust if needed.
2. Start Postgres:
   ```powershell
   ./scripts/db-up.ps1
   ```
3. Tail logs:
   ```powershell
   ./scripts/db-logs.ps1
   ```
4. Stop and remove:
   ```powershell
   ./scripts/db-down.ps1
   ```

FAISS will be used in-process for development; no additional service needed.
