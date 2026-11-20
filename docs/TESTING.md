# Testing

## Backend

```powershell
cd services/api
python -m pytest -q
python -m ruff check app tests
```

Current verified state: **47 tests pass**, `ruff` is clean.

| File | Focus |
| --- | --- |
| `tests/test_platform.py` | Registration, tenants, SSO config, isolation, gateway lifecycle, correlation |
| `tests/test_control_plane.py` | Catalog, overview, tools/skills CRUD, run filters, republish, cross-org |
| `tests/test_langgraph_runtime.py` | Real `StateGraph`, templates, conditions, HTTP, agent loop, tools, guardrails, failure traces |
| `tests/test_langchain_provider.py` | Connectivity, model requirement, graph execution/streaming, async refusal |
| `tests/test_langchain_api.py` | Graph CRUD, validation, dry-run, publish snapshot, isolation |
| `tests/test_tools.py` | HTTP tool rendering, MCP initialize/session/SSE, MCP discovery |
| `tests/test_dispatch_template.py` | Ticketing template validation and output contract |
| `tests/test_streaming.py` | Platform stream persistence, disconnect cancellation, SSE wrapper |

Tests use an isolated SQLite database and generated Fernet/JWT keys. They enable
`PRAGMA foreign_keys=ON`. Runtime tests inject fake chat models and
`httpx.MockTransport`, so they do not require a model endpoint or network.

## Live smoke performed

The real `LangGraphRuntime` was exercised against local Ollama
`qwen2.5-coder:7b` (`http://localhost:11434/v1`) through the API:

- Provider connection verified with live `GET /models` (7 models returned).
- Agent + guardrail graph saved, run draft, returned `final`.
- Tool-node failure produced a failed run with the failing step preserved in
  `provider_extension.langchain.steps`.
- UI checked in a real browser: login, overview, providers, Ollama preset, tools,
  skills, agent creation, link, graph editor, run detail, and error references.

## Frontend

```powershell
cd apps/web
npm run typecheck
npm run build
```

Both pass. The UI was additionally exercised in a browser against the smoke API.

## Manual smoke checklist

1. Register or sign in. Confirm the overview has honest empty states.
2. Connect local Ollama or another OpenAI-compatible endpoint. `List models` must
   show real model ids.
3. Create a tool and **Test** it. Authorization headers must not appear in list
   responses beyond their names.
4. Create a skill and attach it to an agent.
5. Build a graph: input → agent(tool + skill) → guardrail(pass/fail) → outputs.
   Validate, save, run draft.
6. Force a failure (unreachable tool). The run must be failed, show a plain-language
   error reference, and include the failing step in the provider extension.
7. Publish, create a customer key, call the gateway, and stream a run.
8. Switch tenant in the shell when the user has more than one membership.
9. If SSO is configured, the login page shows the SSO button and the callback
   returns to `/overview` with first-party cookies.

## Remaining unverified

- A live OIDC provider (discovery, token exchange, JWKS) was not available here;
  the flow is implemented and unit-shaped, but needs your IdP registration.
- A live MCP server beyond `httpx.MockTransport` wire tests.
- Postgres migration execution for `0004` (Alembic syntax checked; SQLite tests do
  not run migrations).
- Multi-instance idempotency/rate limiting (in-process today).
- Browser-level automated tests.
