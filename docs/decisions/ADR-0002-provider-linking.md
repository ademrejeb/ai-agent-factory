# ADR-0002: Link existing provider resources; do not fake authoring APIs

## Status

Accepted

## Context

Dify’s documented Service API is **per app key**. Creating apps is a Studio/OpenAPI concern (`/openapi/v1` disabled by default, catalog-fingerprinted). Sim can create an empty workflow via API but graph editing remains in Sim.

## Decision

First release **registers** existing Dify apps and Sim workflows. We verify connectivity with documented endpoints. We do not call Dify `/console/api`. We do not claim programmatic Dify app creation until `/openapi/v1` is enabled and proven in a PoC.

## Consequences

- Users create/publish in Dify or Sim, then paste URL + key (and Sim workflow id).
- Studio UX is “open provider” rather than an embedded fake editor.
- OpenAPI/difyctl is a later optional adapter, not a blocker for the gateway.
