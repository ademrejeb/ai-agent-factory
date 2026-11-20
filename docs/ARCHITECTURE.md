# Architecture

## Decision summary

The product is a **modular monolith**: one FastAPI process, one Next.js app, one
PostgreSQL database, and one platform-owned LangGraph runtime. Dify and Sim were removed:
their APIs could not be configured end to end from this control plane, so keeping the
screens would have meant keeping dead controls.

```text
[Browser]
   │  httpOnly first-party cookies
   ▼
Next.js (apps/web :3100)
   │  /backend-api/* rewrite (server-side)
   ▼
FastAPI control plane (services/api :8080)
   │
   ├── PostgreSQL :5433
   └── LangGraph runtime ──▶ OpenAI-compatible model endpoint
                          ├──▶ HTTP tools
                          └──▶ MCP servers (JSON-RPC over HTTP)
```

## Components

| Component | Responsibility |
| --- | --- |
| `apps/web` | Operator UI: overview, agents, graph editor, tools, skills, runs, providers, keys, tenant switcher, SSO login. |
| `services/api` | AuthN/AuthZ, tenancy, lifecycle, graph validation, execution, tools/MCP, guardrails, gateway, runs. |
| PostgreSQL | Source of truth for metadata, graph drafts, encrypted credentials, and runs. |
| Model endpoint | Ollama, LM Studio, vLLM, LiteLLM, OpenAI, or any compatible gateway. Not hosted here. |
| Tools/MCP | Operator-owned outbound integrations. Credentials encrypted at rest. |

## Why the Next.js proxy

The browser calls `/backend-api/*` on the web origin. `next.config.ts` rewrites that
prefix to `API_ORIGIN`. This keeps session cookies first-party, avoids a credentialed
CORS exchange, and keeps the API host out of client bundles. `API_ORIGIN` is a build-time
value for the Docker image.

## Trust boundaries

1. **Browser** — session cookie only. Sees metadata, never model keys, tool headers, or
   the raw customer secret after creation.
2. **Control plane** — decrypts credentials in process memory only for outbound calls.
3. **Customer gateway** — `Authorization: Bearer aaf_...`, SHA-256 hashed at rest.
4. **Tools** — outbound URLs are validated; private targets require an explicit setting.

## Tenant and SSO model

Every tenant-owned row has `organization_id`. Authorization resolves membership from the
database and an optional signed active-tenant cookie; client-supplied organization ids are
never trusted alone. Cross-org access is covered by tests.

OIDC SSO is implemented in-app (`/api/v1/auth/sso/start` and `/callback`). It validates
the discovery document, authorization-code flow with PKCE, ID-token signature, issuer,
audience, and nonce, then provisions a user and tenant membership. It issues this app's
own cookies; password login remains available.

## Graph runtime

- Exactly one `input`; `agent`, `llm`, `tool`, `http`, `condition`, `guardrail`; one or
  more terminal `output`.
- Acyclic, no merges. Conditions and guardrails have exactly two labeled branches and each
  branch must reach an output, so rejected answers stay visible.
- `agent` nodes attach tools and skills and run a bounded tool-calling loop
  (`max_steps`, max 12). Plain `llm` nodes are single-shot.
- `tool` nodes call a registered HTTP/MCP tool. `http` nodes call a URL directly.
- Guardrails inspect length, blocked/required terms, and regex, then route pass/fail.

## Unified execution contract

Applications call the platform, not a provider:
`POST /api/v1/agents/{agent_id}/runs`. Run input/output are stored as bounded previews
(`bytes`, `preview`, `truncated`). Blocking and SSE streaming are real. Async returns
`unsupported_capability` because there is no external queue.

Publishing snapshots the draft graph into an immutable version. The gateway executes only
that snapshot; draft runs execute the saved draft.
