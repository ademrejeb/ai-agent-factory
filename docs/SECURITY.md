# Security

## Trust boundaries

See [`ARCHITECTURE.md`](ARCHITECTURE.md). Model keys, tool headers, and agent
secrets never reach the browser after save. Logs must not include `Authorization`,
`X-API-Key`, or decrypted secrets.

## Authentication

- **Operator:** email/password or in-app OIDC SSO; signed JWT in the httpOnly
  `factory_session` cookie. `SameSite=Lax`; `Secure` when `COOKIE_SECURE=true`.
- **Active tenant:** signed `factory_org` cookie; every request re-checks membership.
- **Customer:** API token `aaf_...`, SHA-256 hashed at rest, prefix stored for display.

### SSO

- Authorization-code flow with PKCE. The verifier and nonce live in a signed,
  httpOnly state cookie; only a random state id is sent to the provider.
- ID token signature is checked against the provider JWKS, plus issuer, audience,
  expiry, and nonce. Userinfo is used only when no ID token is returned.
- Allowed email domains, default role, and tenant mapping are explicit settings.
- The callback is on the web origin (`/backend-api/...`) so cookies remain
  first-party. Password login remains available.

## Authorization

RBAC: `owner` / `admin` / `member` / `viewer`. Resource access always includes
`organization_id` from membership, never from request parameters. Tests cover
cross-org agent and run access.

| Action | Owner | Admin | Member |
| --- | --- | --- | --- |
| Read agents, runs, provider state | yes | yes | yes |
| Create/edit agents, link, test | yes | yes | yes |
| Create workspaces, connections, tools, skills, API keys | yes | yes | no |
| Publish / deactivate | yes | yes | no |

## Secrets

- Fernet encrypts provider credentials, tool headers, and agent secrets
  (`PLATFORM_SECRETS_KEY`).
- Rotating `PLATFORM_SECRETS_KEY` requires a planned re-encrypt; no automated tool exists.
- Production: inject secrets from a secret store; do not bake them into images.
- The web proxy keeps credentials off the browser and the API host out of bundles.

## Execution safety

- Streaming body cap (`GATEWAY_MAX_BODY_BYTES`), outbound timeouts, per-credential
  rate limit, login/register throttles, durable idempotency keys.
- Outbound URL policy for model roots, tools, MCP servers, and graph HTTP nodes:
  loopback/private targets need `ALLOW_PRIVATE_PROVIDER_URLS=true`;
  link-local/metadata addresses are always denied.
- Tool headers are encrypted at rest and rendered into `{{secrets.NAME}}` only at
  execution. Values are never returned by the API.
- HTTP and MCP responses are size-capped; stored run output is bounded.
- Model output is stored as an untrusted preview.
- Agent tool loops are bounded by `max_steps` (max 12).

## Known gaps

- Rate limiting is in-memory; a restart clears it and multiple API replicas do not
  share state. Idempotency is durable in Postgres.
- DNS is validated before an outbound request, but the connection resolves the name
  again (a narrow rebinding window). Pin egress at the network layer for hostile
  tenants.
- Provider credentials cannot be rotated in place yet.
- No automated dependency scanning, SBOM, or image signing.
- No retention job; run previews persist indefinitely.
- No MFA, password reset, or email verification beyond the IdP.

## Production checklist (not claimed complete)

- TLS at the edge; `COOKIE_SECURE=true`.
- Configure `SSO_ALLOWED_DOMAINS` before enabling auto-provisioning.
- Back up Postgres **and** the Fernet key.
- Restrict Ollama and MCP/tool servers to private networks.
- Dependency scanning, image pinning, incident contacts, log retention, restore drill.

This document does not claim SOC 2, ISO 27001, GDPR certification, or similar.
