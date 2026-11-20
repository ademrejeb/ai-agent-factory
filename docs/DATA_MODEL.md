# Data model

Every tenant-owned row carries `organization_id`. Authorization resolves
membership from the database; client-supplied organization ids are ignored.

| Table | Purpose |
| --- | --- |
| `users` | Email/password or SSO-provisioned users |
| `organizations` | Tenants; optional `sso_domain` for domain-based join |
| `memberships` | User ↔ organization, role (`owner/admin/member/viewer`) |
| `workspaces` | Organization-scoped grouping |
| `provider_connections` | OpenAI-compatible endpoints; encrypted credentials |
| `agents` | Logical agent, lifecycle, `skill_ids`, provider link |
| `agent_versions` | Immutable publish snapshots, including the graph |
| `deployments` | Active/superseded deployment and health state |
| `local_graphs` | Editable draft graph (nodes, edges, revision) |
| `tools` | HTTP/MCP tools, encrypted headers, JSON input schema |
| `skills` | Reusable instruction blocks |
| `agent_secrets` | Encrypted `{{secrets.NAME}}` values |
| `api_credentials` | Customer keys: prefix, SHA-256 hash, scopes, revocation |
| `runs` | Execution record, bounded input/output previews, error category |
| `usage_events` | One request event per completed run |
| `audit_events` | Actor/action/resource trail |

## Graph storage

`local_graphs.nodes` is a dictionary keyed by node id:

```json
{
  "agent": {
    "id": "agent",
    "type": "agent",
    "name": "Choose technician",
    "position": {"x": 300, "y": 0},
    "config": {
      "prompt": "{{ message }}",
      "tool_ids": ["tool_..."],
      "skill_ids": ["skill_..."],
      "max_steps": 6,
      "output_key": "answer"
    }
  }
}
```

Edges use `sourceHandle` `null`, `true/false` for conditions, or `pass/fail` for
guardrails. Validation rejects unknown nodes, merges, cycles, unreachable nodes,
and branches that do not end at an output.

On publish, the graph is copied into `agent_versions.snapshot.graph`. The
gateway executes that snapshot; tests and draft runs execute `local_graphs`.

## Retention

Input/output previews are bounded by `GATEWAY_MAX_MESSAGE_CHARS` and
`GATEWAY_MAX_EXTENSION_BYTES`. Full transcripts and automatic pruning are not
implemented. Deleting a tenant cascades only through explicitly deleted rows;
the product has no destructive bulk delete UI.

## Migrations

Alembic is the source of truth in production:
`alembic upgrade head` runs in the API container before the process starts.
Development additionally creates missing tables for convenience.
