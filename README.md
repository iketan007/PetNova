# PetNova — Smarter Care. Happier Pets.

PetNova is an AI pet-care assistant with a responsive web interface, account-based pet profiles, health records, and care reminders.

## Project structure

```text
PetNova/
├── backend/
│   ├── app/main.py
│   ├── app/rate_limit.py
│   ├── app/rag.py
│   ├── app/petnova_data.py
│   ├── app/config.py
│   ├── scripts/             # Database backup and deployment smoke checks
│   ├── tests/
│   ├── data/knowledge_base/
│   ├── requirements.txt
│   └── Dockerfile
└── frontend/
    ├── index.html
    ├── css/style.css
    └── js/app.js
```

## Run locally

Use Python 3.10+ or another version supported by the pinned dependencies.

```bash
cd backend
python -m venv .venv
# Windows PowerShell: .venv\\Scripts\\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

Copy `backend/.env.example` to `backend/.env` and set a valid LLM provider API key. The default provider is OpenAI-compatible and the default base URL targets Groq. The default model is `openai/gpt-oss-20b`; verify availability with your provider and override `OPENAI_COMPATIBLE_MODEL` if needed. Never commit real API keys or secrets.

Generate a session-signing secret locally:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Set `PETNOVA_AUTH_SECRET` to the generated value (at least 32 characters). Then start the backend from the `backend` directory:

```bash
uvicorn app.main:app --reload --port 8000
```

In another terminal, serve the frontend:

```bash
cd frontend
python -m http.server 5500
```

Open http://localhost:5500. The frontend defaults to the deployed backend URL. To use your local backend, set `window.VETGPT_API_BASE_URL = 'http://localhost:8000'` before `js/app.js` loads, or change the default in `frontend/js/app.js`.

## AI chat and retrieval

The `POST /chat` route retrieves relevant text from `backend/data/knowledge_base/*.md` using BM25 keyword ranking, builds a prompt from retrieved passages, and calls the configured OpenAI-compatible LLM. It returns the generated answer and retrieved source passages. Chat input is capped at 4,000 characters and optional history at 20 messages. PetNova is not a substitute for a licensed veterinarian.

## Workspace API

- `POST /auth/register` — create an account (password 10–128 characters)
- `POST /auth/login`, `GET /auth/me` — authenticate and inspect the current session
- `GET/POST /pets`, `PATCH/DELETE /pets/{pet_id}` — manage pet profiles
- `GET/POST /health-records`, `DELETE /health-records/{record_id}` — manage health notes
- `GET/POST /reminders`, `PATCH/DELETE /reminders/{reminder_id}` — manage reminders
- `GET /health` — liveness check
- `POST /reindex` — refresh retrieval data; requires the `X-Reindex-Key` header and a configured secret of at least 32 characters

Workspace requests use `Authorization: Bearer <token>`. Passwords are hashed with PBKDF2-SHA256 and session tokens are signed. Keep secrets private and use HTTPS in deployed environments.

### Rate limiting

Per-process fixed-window limits apply to registration (5/minute), login (10/minute), chat (20/minute), and reindex (3/minute), per client address. A blocked request returns HTTP 429 and a `Retry-After` header. Counters reset on restart and are not shared across instances; use host/edge rate limiting for stronger production protection.

## Deployment operations

### Non-destructive smoke checks

From the `backend` directory:

```bash
python scripts/smoke_test_deployment.py
```

This checks the public backend health endpoint, API docs and frontend HTTP response. To include read-only workspace checks, use a dedicated smoke-test account:

```bash
# PowerShell
$env:PETNOVA_SMOKE_EMAIL = "your-test-account@example.com"
$env:PETNOVA_SMOKE_PASSWORD = "your-test-account-password"
python scripts/smoke_test_deployment.py
```

To test the AI provider, opt in to one chat request with `python scripts/smoke_test_deployment.py --check-chat`; this may consume provider quota. The script never prints the session token and does not create or modify workspace records.

### Database persistence and migration

The Render Free database path is ephemeral. Data can be lost when the service restarts or redeploys. Code changes alone do not make it persistent. Before switching storage, export and verify the actual production database from the running host; a local SQLite file may not contain production records. Do not point production at a new empty database. Configure a supported persistent disk or migrate to managed PostgreSQL only after a verified backup and a planned migration.

### Hosting checks

The Render blueprint currently restricts `ALLOWED_ORIGINS` to `https://vetgpt-ai-hxcr.vercel.app`; update it if the frontend domain changes. For local development, use `ALLOWED_ORIGINS=http://localhost:5500,http://127.0.0.1:5500`. Do not use `*` in production.

Vercel build-rate-limit failures are hosting/account limits, not application-code failures. Retry after the provider's limit window resets or review Vercel usage/plan. A passing backend CI run does not prove the deployed frontend works.

## Tests

From the `backend` directory:

```bash
python -m unittest discover -s tests -v
```

Run the deployment smoke checks after every production deploy. Test registration/login and the read-only workspace checks using a dedicated smoke-test account; verify pet create/update/delete only in a non-production test environment.
