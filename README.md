# PetNova — Smarter Care. Happier Pets.

PetNova is an AI pet-care assistant with a responsive web interface, account-based pet profiles, health records, and care reminders.

## Project structure

```text
PetNova/
├── backend/
│   ├── app/main.py          # FastAPI routes, validation, auth dependencies
│   ├── app/rate_limit.py    # Basic limits for sensitive endpoints
│   ├── app/rag.py           # BM25 retrieval and LLM prompt/generation
│   ├── app/petnova_data.py  # SQLite persistence, password hashing, sessions
│   ├── app/config.py        # Environment-based configuration
│   ├── tests/               # Backend unit and API regression tests
│   ├── data/knowledge_base/ # Curated pet-care Markdown documents
│   ├── requirements.txt
│   ├── .env.example
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

The `POST /chat` route retrieves relevant text from `backend/data/knowledge_base/*.md` using BM25 keyword ranking, builds a prompt from retrieved passages, and calls the configured OpenAI-compatible LLM. It returns the generated answer and retrieved source passages. Chat input is capped at 4,000 characters and an optional history is capped at 20 messages. Retrieval quality depends on the quality and coverage of the knowledge base; the assistant is not a substitute for a licensed veterinarian.

## Workspace API

- `POST /auth/register` — create an account (password 10–128 characters)
- `POST /auth/login`, `GET /auth/me` — authenticate and inspect the current session
- `GET/POST /pets`, `PATCH/DELETE /pets/{pet_id}` — manage pet profiles
- `GET/POST /health-records`, `DELETE /health-records/{record_id}` — manage health notes
- `GET/POST /reminders`, `PATCH/DELETE /reminders/{reminder_id}` — manage reminders
- `GET /health` — liveness check
- `POST /reindex` — refresh retrieval data; requires the `X-Reindex-Key` header and is disabled unless `REINDEX_API_KEY` is configured to a secret of at least 32 characters

Workspace requests use `Authorization: Bearer <token>`. Passwords are hashed with PBKDF2-SHA256 and session tokens are signed. Keep secrets private and use HTTPS in deployed environments.

### Rate limiting

The API applies per-process fixed-window limits to sensitive routes: registration (5/minute), login (10/minute), chat (20/minute), and reindex (3/minute), per client address. A blocked request returns HTTP 429 and a `Retry-After` header. These in-process counters reset when the service restarts and are not shared across workers or instances; use host/edge rate limiting for stronger production protection and verify proxy client-IP handling before relying on IP-based limits.

## Deployment and persistence

The backend can be deployed with the Dockerfile and `render.yaml`; deploy the static frontend from the `frontend` directory. Configure `OPENAI_COMPATIBLE_API_KEY`, `OPENAI_COMPATIBLE_MODEL`, and `PETNOVA_AUTH_SECRET` in the backend host's environment.

The Render Free database path is ephemeral. Data can be lost when the service restarts or redeploys. This is not fixed by the code changes: durable data requires a supported persistent disk or a managed database. Before switching paths, securely export and verify the current production database; a local SQLite file may not contain production records. Do not change the production DB path to a new empty file as a migration shortcut.

The Render blueprint restricts `ALLOWED_ORIGINS` to `https://vetgpt-ai-hxcr.vercel.app`; update that value if the Vercel domain changes. For local development, set `ALLOWED_ORIGINS=http://localhost:5500,http://127.0.0.1:5500`. Do not use `*` for a production deployment.

Vercel build-rate-limit failures are a hosting/account limit, not an application-code error. Retry after the provider's limit window resets or review the Vercel usage/plan; a successful CI test run does not itself verify a live frontend deployment.

## Tests

From the `backend` directory, run:

```bash
python -m unittest discover -s tests -v
```

The suite includes data-layer and API regression tests, including cross-account access and rate limiting. Verify CI results on the exact commit before merging, then perform a live smoke test of registration, login, pet records, health records, reminders, and AI chat.
