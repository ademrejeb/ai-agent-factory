# Roadmap

Nothing is claimed complete without a test or a verified run.

## Done

- **One runtime:** platform-owned LangGraph against an OpenAI-compatible endpoint.
  Dify and Sim adapters, routes, UI, and tests were removed.
- **Composable agents:** `agent`, `tool`, `http`, `guardrail`, `condition`, `llm`,
  `input`, and `output` nodes with server validation.
- **Tools and MCP:** organization-owned HTTP/MCP tools, encrypted headers, MCP discovery,
  agent tool-calling loop, per-tool test path.
- **Skills:** reusable instruction blocks attached to agents and nodes.
- **Guardrails:** pass/fail routing with visible reasons and a mandatory fail output.
- **Local models:** Ollama quick preset, live `GET /models`, model listing in the UI.
- **Tenants:** active-tenant cookie, in-app switching, membership enforcement.
- **SSO:** in-app OIDC authorization-code flow with PKCE and token validation.
- **Usability:** plain-language error references, human metric labels, explainable
  guardrail/agent nodes, ticketing template preserved and exercised end to end.
- **Gateway:** scoped keys, idempotency, rate limiting, blocking and SSE streaming.

## Partial

- **MCP transport:** HTTP JSON-RPC only. Stdio-only servers need a bridge.
- **Idempotency and rate limiting:** in-process only; one replica or a shared store.
- **Retention:** run previews are bounded but old runs are not pruned automatically.
- **Invitations:** memberships exist; an invitation UI does not.

## Later

1. Shared idempotency/rate-limit store and a background execution worker.
2. Invitation flow and per-tenant SSO domain administration in the UI.
3. Evaluation datasets and regression scoring for graph versions.
4. Retention policy and opt-in full-transcript object storage.
5. OpenTelemetry traces spanning gateway → graph → tool calls.

## Decision log

**Now:** one runtime, real tools, bounded agent loops, explicit guardrails, in-app tenant
switch and SSO, no fake provider screens.

**Later:** Redis, external queue, object storage, fine-tuning, payments.
