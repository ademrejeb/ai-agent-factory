# Product vision

**Product name:** configurable via `PLATFORM_NAME` (default: AI Agent Factory).

This repository is the control plane for composing, running, governing, exposing,
and inspecting AI agents. It owns the runtime and the graph; it no longer pretends
to configure Dify or Sim.

## Users

- Platform operator: build internal agents and a commercial offering.
- Organization members: compose agents, attach tools/skills/guardrails, test, inspect.
- Customer applications: call published agents through the platform gateway only.

## What this product owns

- Identity, organizations, memberships, active-tenant switching, roles.
- In-app OIDC SSO and password login.
- OpenAI-compatible model connections and live verification.
- The agent graph, lifecycle, snapshots, and deployments.
- Reusable HTTP/MCP tools, skills, and guardrails.
- Customer gateway, API keys, runs, usage, and audit records.

## What it does not own

- The model endpoint (Ollama, LM Studio, vLLM, gateway, or hosted API).
- MCP/tool servers themselves.
- Foundation-model training or a GPU cluster.
- Payments (usage events exist; billing does not).

## Current product boundary

- Register / sign in; switch tenant when the user has multiple memberships.
- Connect a model endpoint; see the models it actually returns.
- Create tools (HTTP or MCP), skills, and agents.
- Compose a graph with input, agent, LLM, tool, HTTP, guardrail, condition, output.
- Test blocking or streaming; disconnect cancels cleanly.
- Publish an immutable version; call it with a scoped customer key.
- Inspect every run, including the failing node for failures.
- Provision the ticketing dispatcher template from the UI or env bootstrap.

Not in this increment: evaluation suites, billing, async queue, stdio MCP,
member invitations, retention jobs.

## Evidence rule

Documentation describes the repository as it exists. Claims about live providers
are limited to what was actually exercised. Unverified items are labeled as such.
