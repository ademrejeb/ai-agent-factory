# Development

Windows + Docker Desktop. Keep Dify/Sim data on the WSL Linux filesystem if you
bind-mount their official trees.

## Full stack with Compose

```powershell
copy .env.example .env
# set JWT_SECRET and PLATFORM_SECRETS_KEY (generate commands are in .env.example)
docker compose up --build
```

- Web: <http://localhost:3100>
- API: <http://localhost:8080>
- OpenAPI (non-production): <http://localhost:8080/docs>
- Postgres: `localhost:5433`

Validate the Compose file without starting anything:

```powershell
docker compose config --quiet
```

Dify and Sim are **not** part of this Compose project.

## API-only development

Run Postgres in Compose and the API on the host:

```powershell
docker compose up -d postgres

cd services/api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
$env:DATABASE_URL = "postgresql+psycopg://factory:factory@localhost:5433/factory"
# Generate once and reuse: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
$env:PLATFORM_SECRETS_KEY = "<fernet-key>"
alembic upgrade head
uvicorn app.main:app --reload --port 8080
```

`PLATFORM_SECRETS_KEY` must stay stable for the life of the database. When it is unset in
development, the API generates a random in-memory key and logs a warning; provider
connections created by that process cannot be decrypted after a restart. Set the variable
in the shell or add a gitignored `services/api/.env` (the API loads `.env` from its working
directory).

In development (`APP_ENV != production`) the API calls `create_all` as a safety net for a
fresh database. Production must rely on `alembic upgrade head` only — the API container
runs it before starting uvicorn.

Optional bootstrap for an empty database (development/container only):

```powershell
$env:BOOTSTRAP_ADMIN_EMAIL = "admin@example.com"
$env:BOOTSTRAP_ADMIN_PASSWORD = "a-long-password"
```

It is a no-op once any user exists and never overwrites credentials.

## Web development

```powershell
cd apps\web
copy .env.example .env.local
npm install
npm run dev
```

`apps/web/.env.local`:

```dotenv
API_ORIGIN=http://localhost:8080
NEXT_PUBLIC_PLATFORM_NAME=AI Agent Factory
```

The browser calls `/backend-api/*`; Next rewrites it to `API_ORIGIN`. If you change
`API_ORIGIN` for the Compose web image, you must rebuild that image because rewrites are
baked into the build.

### Web scripts

| Command | Purpose |
| --- | --- |
| `npm run dev` | Dev server on port 3100 |
| `npm run typecheck` | `tsc --noEmit` |
| `npm run build` | Production build |
| `npm run start` | Serve the production build on port 3100 |

## Tests

```powershell
cd services/api
python -m pytest -q
python -m ruff check app tests
```

The runtime tests use fake chat models and `httpx.MockTransport`, so no network or paid
tokens are required. The live smoke in this repo was run against Ollama
(`qwen2.5-coder:7b`) through the real `LangGraphRuntime`. See
[`TESTING.md`](TESTING.md).

## Ollama

Ollama runs on the host, not in the platform Compose file.

```powershell
ollama serve
ollama pull qwen2.5-coder:7b
```

In **Model providers → Use local Ollama**, use `http://localhost:11434/v1`, any API key
value, and a model that **List models** actually returns. For a containerised API, use
`http://host.docker.internal:11434/v1` and set `ALLOW_PRIVATE_PROVIDER_URLS=true`.

8 GB VRAM: small models only. A 7B Q4 model is enough to prove the graph, tools, and
guardrails; it is not a production latency target.

## MCP and tools locally

Create an HTTP tool against a local endpoint, or point an MCP tool at an HTTP JSON-RPC
server. The Tools page **Test** button and agent tool calls use the same executor. MCP
over stdio is not supported; put a small HTTP bridge in front of it.
