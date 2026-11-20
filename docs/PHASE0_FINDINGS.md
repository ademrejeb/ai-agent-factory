# Phase 0 findings (historical)

> Historical discovery notes from the Dify/Sim evaluation. Dify and Sim were
> later removed because their APIs could not be configured end to end here.
> See [`ARCHITECTURE.md`](ARCHITECTURE.md) and [`ROADMAP.md`](ROADMAP.md) for the
> current product.

Evidence: `docs/PROVIDER_CAPABILITY_MATRIX.md`.

1. **Dify APIs** — Documented Service API: execute chat/workflow, `/v1/info`, workflow run detail and logs. App keys are per app. Publishing is Studio (OpenAPI/difyctl optional, default off). Console `/console/api` is not our integration surface. Agent apps need streaming.
2. **Sim APIs** — Documented v2: list/create/deploy/execute workflows, get/list runs, logs. `X-API-Key`. Async and stream supported. Create workflow ≠ finished agent.
3. **Needs web UI** — Visual graphs, Dify app creation (until OpenAPI PoC), Dify API key minting, Sim deploy unless we call deploy API later, most RAG UX.
4. **Must be ours** — Tenancy, catalog, lifecycle, customer keys, gateway, metering, product observability, evaluation.
5. **Overlap** — Execution and some logs. We still record platform runs for attribution.
6. **Simplest secure expose** — Our FastAPI gateway; adapters hold provider secrets; customers get `aaf_` keys.
7. **Local resources** — Dify min 4 GiB, Sim eval ~12 GiB + 8 GiB app cap. Do not default-start both. Platform stack is small.
8. **Licensing** — Dify: no Community multi-tenant Dify workspaces; keep logos. Sim: Apache core; EE production needs subscription.
9. **Smallest vertical slice** — This increment’s flow (connect → link → run → record → UI).
10. **Now vs later** — Now: adapters for verified execute APIs, tenancy, gateway. Later: OpenAPI authoring, streaming, eval, billing, cloud.
