# PetNova — Smarter Care. Happier Pets.

PetNova combines an AI pet-care chat assistant with private pet profiles, health records, and care reminders. The FastAPI backend preserves the existing `POST /chat` endpoint and adds authenticated, user-scoped APIs for saved care data. The responsive frontend is a standalone HTML app.


```
vetgpt-project/
├── backend/
│   ├── app/
│   │   ├── main.py        # FastAPI app (/chat, /health, /reindex)
│   │   ├── rag.py         # embeddings, FAISS index, prompt, LLM call
│   │   └── config.py      # all settings, via environment variables
│   ├── data/
│   │   ├── knowledge_base/    # curated .md vet-care docs (edit/add freely)
│   │   └── faiss_index/       # generated on first run (git-ignored)
│   ├── scripts/build_index.py # rebuild the FAISS index manually
│   ├── requirements.txt
│   ├── .env.example
│   └── Dockerfile
└── frontend/
    └── index.html          # chat UI, calls the backend's /chat endpoint
```

## 1. Run the backend locally

```bash
cd backend
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

You need a Llama 2 model to generate answers. Pick ONE of these in `.env`:

- **Local GGUF model (default, `LLM_PROVIDER=llama_cpp`)** — download a
  quantized Llama 2 chat model (e.g. `llama-2-7b-chat.Q4_K_M.gguf` from
  TheBloke on Hugging Face), place it at the path in `LLAMA_MODEL_PATH`
  (default `./models/llama-2-7b-chat.Q4_K_M.gguf`).
- **Ollama** — `ollama pull llama2`, then set `LLM_PROVIDER=openai_compatible`
  and leave `OPENAI_COMPATIBLE_BASE_URL=http://localhost:11434/v1`.
- **Hosted HF Inference Endpoint** — set `LLM_PROVIDER=hf_endpoint` and fill
  in `HF_ENDPOINT_URL` / `HF_API_TOKEN`.

Then start the API:

```bash
uvicorn app.main:app --reload --port 8000
```

The first request builds the FAISS index automatically from
`data/knowledge_base/*.md` (takes a few seconds). To rebuild it manually
after editing the knowledge base:

```bash
python scripts/build_index.py
```

Test it:

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "How often should I feed my puppy?"}'
```

## 2. Run the frontend

`frontend/index.html` is a single self-contained file — just open it in a
browser, or serve it:

```bash
cd frontend
python -m http.server 5500
```

The frontend currently calls the deployed backend at `https://vetgpt-backend.onrender.com`. For local development, add this before the closing `</body>` tag:

```html
<script>window.VETGPT_API_BASE_URL = 'https://your-deployed-backend.com';</script>
```

## 3. Deploying for a public link

The backend needs a host that can run a Python process (and ideally a GPU
or enough RAM for the quantized model):

- **Render / Railway / Fly.io** — deploy the `backend/Dockerfile`, mount or
  bake in your GGUF model file, set env vars from `.env.example`.
- **Hugging Face Spaces (Docker SDK)** — good free option for demos.
- **Any VM (EC2, DigitalOcean, etc.)** — clone the repo, follow step 1.

Once the backend has a public URL, deploy `frontend/index.html` anywhere
static (GitHub Pages, Netlify, Vercel, S3) with `VETGPT_API_BASE_URL` set
to that URL — then that static link is your public, shareable chatbot.

## Extending the knowledge base

Drop more `.md` (or adjust the loader glob for `.txt`/`.pdf`) files into
`backend/data/knowledge_base/`, then call `POST /reindex` or re-run
`scripts/build_index.py`.


## PetNova saved care workspace

The UI includes **My pets**, **Health records**, and **Reminders**. These features use a SQLite database and require a signing secret for account sessions. The existing `POST /chat` endpoint does not require an account and remains separate.

### Configure account features

In `backend/.env`, set a unique secret with at least 32 characters:

```env
PETNOVA_AUTH_SECRET=your_unique_long_random_secret_here
PETNOVA_DB_PATH=./data/petnova.sqlite3
```

Generate a suitable secret locally with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Do not commit your real `PETNOVA_AUTH_SECRET` or any API keys. Registration and login return a signed session token that expires after seven days. Passwords are stored as PBKDF2-SHA256 hashes, not plaintext. The API scopes pet profiles, records, and reminders to the authenticated account.

### Workspace API

- `POST /auth/register` — create an account (password 10–128 characters)
- `POST /auth/login` and `GET /auth/me` — sign in and check the current session
- `GET/POST /pets`, `PATCH/DELETE /pets/{pet_id}` — manage pet profiles
- `GET/POST /health-records`, `DELETE /health-records/{record_id}` — manage health notes
- `GET/POST /reminders`, `PATCH/DELETE /reminders/{reminder_id}` — manage reminders

Authenticated requests use `Authorization: Bearer <token>`. The backend validates ownership on pet, health-record, and reminder operations.

### Database persistence on deployment

SQLite is appropriate for a small demo. The Render Free configuration uses an ephemeral path, so saved workspace data can be lost when the service is restarted or redeployed. For reliable production persistence, configure `PETNOVA_DB_PATH` to a mounted persistent disk or migrate the data module to a managed PostgreSQL database. Back up the database and use HTTPS in production. Account features return a configuration error until `PETNOVA_AUTH_SECRET` is set in the hosting environment.


### Run the workspace tests

From the `backend` directory, run:

```bash
python -m unittest discover -s tests
```
