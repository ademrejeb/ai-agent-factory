# API reference

All routes are versioned under `/api/v1` and return JSON. Browser routes use the
first-party session cookie; customer routes use `Authorization: Bearer aaf_...`.
The web app proxies `/backend-api/*` to this API.

## Auth and tenants

| Method | Path | Auth | Behaviour |
| --- | --- | --- | --- |
| POST | `/api/v1/auth/register` | public | Create user + organization + workspace |
| POST | `/api/v1/auth/login` | public | Password login; sets session and active-tenant cookies |
| POST | `/api/v1/auth/logout` | session | Clear both cookies |
| GET | `/api/v1/auth/me` | session | User, active organization, role, memberships, SSO availability |
| POST | `/api/v1/auth/organization` | session | Switch active tenant; membership enforced |
| GET | `/api/v1/auth/sso/config` | public | Whether the SSO button is enabled |
| GET | `/api/v1/auth/sso/start` | public | Redirect to the OIDC provider (PKCE) |
| GET | `/api/v1/auth/sso/callback` | public | Validate ID token, provision user/tenant, set first-party cookies |

SSO configuration: `SSO_ISSUER`, `SSO_CLIENT_ID`, `SSO_CLIENT_SECRET`,
`SSO_REDIRECT_URI` (optional), `SSO_ALLOWED_DOMAINS`, `SSO_ROLE_CLAIM`,
`SSO_DEFAULT_ROLE`, `SSO_AUTO_CREATE_ORG`, `SSO_DEFAULT_ORG_SLUG`.

## Models, tools, skills

| Method | Path | Behaviour |
| --- | --- | --- |
| GET | `/api/v1/providers` | Verified runtime catalog |
| GET/POST | `/api/v1/provider-connections` | List/create OpenAI-compatible model connections |
| POST | `/api/v1/provider-connections/{id}/check` | Real `GET /models` check |
| GET | `/api/v1/provider-connections/{id}/models` | Live model list |
| GET/POST | `/api/v1/tools` | List/create HTTP or MCP tools |
| PATCH/DELETE | `/api/v1/tools/{id}` | Update/delete a tool |
| POST | `/api/v1/tools/{id}/test` | Execute the exact tool path with arguments |
| POST | `/api/v1/tools/discover/mcp` | `tools/list` against an MCP server |
| GET/POST | `/api/v1/skills` | List/create reusable instructions |
| PATCH/DELETE | `/api/v1/skills/{id}` | Update/delete a skill |
| GET/POST | `/api/v1/knowledge-bases` | List/create RAG corpora |
| GET/PATCH/DELETE | `/api/v1/knowledge-bases/{id}` | Detail (with documents)/update/delete |
| POST | `/api/v1/knowledge-bases/{id}/documents` | Chunk + index text |
| DELETE | `/api/v1/knowledge-bases/{id}/documents/{doc_id}` | Remove a document and its chunks |
| POST | `/api/v1/knowledge-bases/{id}/search` | Same retrieval path as the graph node; returns scored chunks |

Tool headers are encrypted at rest; `{{secrets.NAME}}` resolves from agent secrets
at execution time. MCP uses Streamable HTTP JSON-RPC (`initialize`,
`notifications/initialized`, `tools/call`), including SSE responses.

## Agents and graphs

| Method | Path | Behaviour |
| --- | --- | --- |
| GET/POST | `/api/v1/agents` | Catalog/create |
| PATCH | `/api/v1/agents/{id}` | Metadata, tags, `skill_ids` |
| POST | `/api/v1/agents/{id}/link` | Verify and link a model connection |
| POST | `/api/v1/agents/from-template` | Create the ticketing dispatcher or RAG assistant graph |
| POST | `/api/v1/agents/{id}/test` | Blocking execution, recorded |
| POST | `/api/v1/agents/{id}/test/stream` | SSE: chunk/status/final/error |
| POST | `/api/v1/agents/{id}/test/async` | Returns `unsupported_capability` (no queue) |
| GET/PUT | `/api/v1/agents/{id}/graph` | Read/replace the saved draft graph |
| POST | `/api/v1/agents/{id}/graph/validate` | Lint without saving |
| POST | `/api/v1/agents/{id}/graph/dry_run` | Execute the saved draft |
| POST | `/api/v1/agents/{id}/publish` | Snapshot graph + deployment record |
| GET | `/api/v1/agents/{id}/runs`, `/versions`, `/deployments`, `/secrets` | Inspection |

Graph nodes: `input`, `agent`, `llm`, `tool`, `http`, `guardrail`, `condition`,
`output`. Exactly one input; no merges or cycles; condition uses `true/false`,
guardrail uses `pass/fail`; every branch reaches an output.

## Gateway

| Method | Path | Behaviour |
| --- | --- | --- |
| POST | `/api/v1/agents/{id}/runs` | Blocking run with published snapshot |
| POST | `/api/v1/agents/{id}/runs/stream` | SSE run |
| POST | `/api/v1/agents/{id}/runs/async` | `unsupported_capability` |
| GET | `/api/v1/runs/{id}` | Run detail, tenant-scoped |
| GET | `/api/v1/runs` | Filters: status, provider, source, agent |
| GET | `/api/v1/overview` | Metrics computed from persisted runs |

Customer keys are SHA-256 hashed at rest, scoped to `agents:run` and/or
`runs:read`, rate-limited per credential, and support `Idempotency-Key`.

## Error shape

```json
{
  "error": {
    "code": "graph_failed",
    "message": "Tool 'Dead probe' is unreachable.",
    "details": {
      "node_id": null,
      "steps": [
        {
          "node": "call",
          "type": "tool",
          "tool_id": "tool_...",
          "error": true,
          "output": "Tool 'Dead probe' is unreachable."
        }
      ],
      "run_id": "run_..."
    }
  }
}
```

The UI turns `code` into a plain-language cause and fix. Codes such as `E30`
that do not match a platform category are shown as references from the
connected business system, never guessed.
