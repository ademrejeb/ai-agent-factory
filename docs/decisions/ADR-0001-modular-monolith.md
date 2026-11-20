# ADR-0001: Modular monolith for the control plane

## Status

Accepted

## Context

The product needs a control plane plus two heavy external engines. Splitting our own code into many services would add operational cost before there is traffic.

## Decision

Ship one FastAPI app and one Next.js app. Isolate providers behind an adapter package. Split services only when a measured need appears (independent scaling, failure isolation, or a separate identity product).

## Consequences

- Simple local Compose: API + web + Postgres.
- Clear module boundaries still required (routers ≠ adapters ≠ persistence).
- Later extraction of the gateway is possible because execution already sits behind `/api/v1`.
