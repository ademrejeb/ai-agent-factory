# AI Agent Factory

A self-hosted control plane for real agent workflows: compose a graph, attach
tools, MCP servers, skills and guardrails, run it against an OpenAI-compatible
model (including local Ollama), publish an immutable version, and call it from
another app through a scoped gateway.

There is one execution engine — the platform-owned LangGraph runtime. Dify and
Sim were removed because their APIs could not be configured end to end here.
No screen claims a capability this repository does not implement.

## What is implemented

| Area | Status |
| --- | --- |
| Email/password auth and in-app OIDC SSO | Implemented |
| Organizations, memberships, active-tenant switching, roles | Implemented |
| OpenAI-compatible model connections (Ollama, LM Studio, vLLM, OpenAI) | Implemented |
| Live `GET /models` verification and model discovery | Implemented |
| Visual graph editor: input, agent, LLM, tool, HTTP, knowledge, guardrail, condition, output | Implemented |
| Bounded tool-calling agent loop with real tools | Implemented |
| Reusable HTTP tools and MCP server tools, encrypted headers | Implemented |
| Reusable skills appended to agent instructions | Implemented |
| Knowledge bases (RAG): text ingestion, chunking, lexical or embedding search | Implemented |
| Retrieval node with scored chunks and a context budget | Implemented |
| Guardrail presets (PII, prompt injection, JSON object) with explicit reasons | Implemented |
| Context engineering: history window, character budget, JSON output | Implemented |
| Ticketing dispatcher template with a real guardrail | Implemented |
| Lifecycle: draft → configured → tested → validated → published → monitored | Implemented |
| Blocking and SSE streaming execution; disconnect becomes `cancelled` | Implemented |
| Publish snapshots, deployments, health checks, run explorer | Implemented |
| Customer gateway: scoped keys, idempotency, rate limiting, streaming | Implemented |
| Human-readable error references and plain-language metrics | Implemented |
| Async execution | Not supported (no external queue; explicit error) |

## Stack

- **Web:** Next.js 16 (App Router, React 19, TypeScript)
- **API:** FastAPI (Python 3.13, SQLAlchemy, Alembic)
- **Database:** PostgreSQL 16
- **Runtime:** LangGraph + LangChain + an OpenAI-compatible chat endpoint

```text
Browser ──▶ Next.js :3100 ──▶ FastAPI :8080 ──▶ PostgreSQL :5433
                                   └──▶ LangGraph runtime ──▶ Ollama / OpenAI-compatible
                                                          ├──▶ HTTP tools
                                                          └──▶ MCP servers
```

## Quick start (Docker Compose)

```powershell
copy .env.example .env
# Generate the two secrets described in .env.example:
#   JWT_SECRET              python -c "import secrets; print(secrets.token_urlsafe(48))"
#   PLATFORM_SECRETS_KEY    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
docker compose up --build
```

Open <http://localhost:3100>, create an organization, then:

1. **Model providers → Use local Ollama** (or any OpenAI-compatible endpoint).
2. **Agents → New agent** or **Start from the ticketing template**.
3. Open **Graph editor** and attach tools, skills, and guardrails.
4. Test, publish, create an API key, call the gateway.

| Endpoint | URL |
| --- | --- |
| Web UI | <http://localhost:3100> |
| API | <http://localhost:8080> |
| OpenAPI (development only) | <http://localhost:8080/docs> |
| Health / readiness | <http://localhost:8080/health>, <http://localhost:8080/ready> |

## Local development

```powershell
docker compose up -d postgres

cd services/api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
$env:DATABASE_URL = "postgresql+psycopg://factory:factory@localhost:5433/factory"
$env:PLATFORM_SECRETS_KEY = "<fernet-key>"
alembic upgrade head
uvicorn app.main:app --reload --port 8080

cd apps\web
copy .env.example .env.local
npm install
npm run dev
```

## Ollama

```powershell
ollama serve
ollama pull qwen2.5:7b
```

In the UI: **Model providers → Use local Ollama**. Base URL
`http://localhost:11434/v1`, any API key value, model `qwen2.5:7b`. Click
**List models** to verify what the endpoint really has. The same path works for
LM Studio, vLLM, LiteLLM, OpenAI, or a compatible gateway.

## Knowledge (RAG)

Create a knowledge base in **Knowledge**, add text/Markdown/CSV/JSON documents,
and test retrieval before wiring it into a graph. Two modes:

- **Keyword** works with no extra service; it scores chunks by term coverage.
- **Embeddings** calls the selected connection's OpenAI-compatible
  `POST /embeddings` (Ollama, LM Studio, vLLM, OpenAI) and stores vectors as
  JSON. Search ranks by cosine similarity in-process, so it works on every
  managed Postgres without the `pgvector` extension.

A **Knowledge** node in the graph turns the user question into the top chunks
and writes two values: the formatted context and `<key>_results` with scores.
The RAG assistant template creates input → knowledge → grounded answer → output
in one step. Documents are capped per run by `KNOWLEDGE_MAX_CHUNKS_PER_RUN`
(default 5000); this is a policy/FAQ corpus, not a general search engine.

## Tools, MCP, skills, guardrails

- **Tools** are organization-owned. HTTP tools store method/URL/body; MCP tools
  store server URL and remote tool name. Header values are encrypted at rest and
  may reference agent secrets as `{{secrets.NAME}}`.
- **Agent nodes** attach selected tools and skills. The model can call those
  tools in a bounded loop (`max_steps`, capped at 12) and returns a final answer.
- **Skills** are reusable instruction blocks appended to every agent node that
  uses them.
- **Guardrails** inspect a rendered value and route `pass` or `fail`. Presets
  cover PII (email/phone/card), prompt-injection phrases and valid JSON
  objects; custom length, blocked/required term and regex rules still apply.
  Both branches must end at an output, so a rejected answer stays visible in
  the run with the exact reasons.
- **Context** on LLM/agent nodes controls conversation history
  (`history_path`, last N messages) and a character budget that trims the
  oldest history before the current prompt. `response_format: json_object`
  asks OpenAI-compatible models for a JSON object.

MCP transport is JSON-RPC over HTTP (`tools/list` and `tools/call`). The Tools
page can discover a server's tools before you save one.

## Graph model

Exactly one `input`; any mix of `agent`, `llm`, `tool`, `http`, `retrieval`,
`condition`, `guardrail`; one or more terminal `output`. Graphs are acyclic and never merge.
A condition has `true`/`false`; a guardrail has `pass`/`fail`.

```text
input → agent(tools+skills) → guardrail(pass/fail) → output
                              ↘ tool / http / llm / condition
```

## Ticketing dispatcher

**Agents → New agent → Start from the ticketing template** creates a real graph:

```text
input(ticketId, tenantId)
  → POST {ticketing}/api/agents/dispatch-context  (Bearer secret)
  → agent chooses one technician from real metrics
  → guardrail requires recommended_technician_id + summary
  → pass: decision JSON   fail: explicit invalid_decision JSON
```

The ticketing app validates the returned id against its own eligible set,
creates the work order/assignment, and falls back to deterministic ranking if
the agent is unreachable or invalid. See the ticketing README for
`FACTORY_GATEWAY_URL`, `FACTORY_AGENT_ID`, `FACTORY_AGENT_KEY`, and
`AGENT_CONTEXT_SECRET`.

## Tenants and SSO

- Every API resource is resolved from the signed-in organization, never from a
  request-supplied tenant id.
- A user with several memberships switches tenants in the shell. The active
  tenant is a signed cookie checked against membership on every request.
- OIDC SSO is implemented inside this app: `/api/v1/auth/sso/start`,
  `/api/v1/auth/sso/callback`, `GET /api/v1/auth/sso/config`.
- Password login remains available. SSO provisions a user and tenant membership
  on first login, validates ID-token issuer/audience/signature/nonce, and issues
  this app's own first-party cookies. It does not redirect unauthenticated
  visitors to another product's login page.

Configure SSO with `SSO_ISSUER`, `SSO_CLIENT_ID`, `SSO_CLIENT_SECRET`,
`SSO_REDIRECT_URI` (optional), `SSO_ALLOWED_DOMAINS`, `SSO_DEFAULT_ROLE`, and
optionally `SSO_DEFAULT_ORG_SLUG` / `SSO_AUTO_CREATE_ORG`.

## Use an agent from another app

```bash
curl -X POST "$API_BASE/api/v1/agents/AGENT_ID/runs" \
  -H "Authorization: Bearer aaf_..." \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: ticket-42" \
  -d '{"input":{"message":"How do I reset my password?"}}'
```

Streaming: `POST /api/v1/agents/{id}/runs/stream` (`event: chunk/status/final/error`).
Async returns `unsupported_capability` because there is no external queue.

## Repository layout

```text
apps/web/                     Next.js control-plane UI
  app/                        Overview, agents, tools, skills, runs, providers, settings
  components/graph/           Visual graph editor
services/api/                 FastAPI control plane
  app/routers/                HTTP surface (auth, sso, agents, tools, skills, gateway)
  app/providers/              OpenAI-compatible adapter + catalog
  app/services/               Execution, LangGraph runtime, tools, templates
  alembic/                    Schema migrations
  tests/                      Pytest suite
docs/                         API, architecture, security, roadmap
docker-compose.yml            Postgres + API + web
```

## Quality checks

```powershell
cd services/api
python -m pytest -q
python -m ruff check app tests

cd ..\..\apps\web
npm run typecheck
npm run build
```

## Configuration

| Variable | Purpose |
| --- | --- |
| `PLATFORM_NAME` / `NEXT_PUBLIC_PLATFORM_NAME` | Product name |
| `DATABASE_URL` | Control-plane database |
| `JWT_SECRET` | Session token signing key |
| `PLATFORM_SECRETS_KEY` | Fernet key for provider credentials, tool headers, agent secrets |
| `WEB_ORIGIN` / `API_ORIGIN` | Origins and Next.js proxy target |
| `COOKIE_SECURE` | Required over HTTPS |
| `SSO_*` | In-app OIDC SSO |
| `GATEWAY_*` | Body cap, timeout, rate limit, message limits |
| `ALLOW_PRIVATE_PROVIDER_URLS` | Allow internal Ollama/tool URLs in production |
| `BOOTSTRAP_ADMIN_EMAIL` / `_PASSWORD` | Optional first user/org |

## Honest limitations

- **One runtime.** No Dify/Sim adapters. Their screens, routes, and tests were
  removed rather than kept as dead configuration.
- **Async is not supported.** No external queue exists; the route says so.
- **Graph model is intentionally small.** No merges, no arbitrary cycles. The
  agent node provides a bounded tool-calling loop instead of an unbounded graph
  loop.
- **MCP transport is HTTP JSON-RPC.** Stdio-only MCP servers need a bridge.
- **Rate limiting and idempotency are in-process.** Use one API replica or add a
  shared store before scaling out.
