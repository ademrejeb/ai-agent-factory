# ADR-0003: Platform tenancy must not map 1:1 onto Dify workspaces

## Status

Accepted

## Context

Dify’s license forbids using Community source to operate a multi-tenant Dify (one Dify workspace per tenant) without written authorization. Sim EE features need a paid subscription in production.

## Decision

- Our `organizations` are the customer tenants.
- Dify/Sim are **execution backends**, typically a small number of instances/workspaces we operate.
- Do not auto-provision Dify workspaces per customer.
- Do not turn on Sim `ENTERPRISE_ENABLED` in production without a subscription.
- Legal review before selling a hosted offering.

## Consequences

Isolation is enforced in our API/database. Provider-side isolation is a defense in depth, not the product tenancy model.
