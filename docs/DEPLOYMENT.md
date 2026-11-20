# Deployment

No public or paid cloud resources are provisioned by this repository.

## Images

| Image | Dockerfile | Notes |
| --- | --- | --- |
| API | `infrastructure/docker/api.Dockerfile` | Runs `alembic upgrade head`, then uvicorn on `:8080` |
| Web | `infrastructure/docker/web.Dockerfile` | Multi-stage Next standalone build, `node server.js` on `:3100` |

Build both through Compose:

```powershell
docker compose build
docker compose up -d
```

The Compose file declares health checks for Postgres and the API; the web service waits
for a healthy API.

## Environment

Required in production:

| Variable | Notes |
| --- | --- |
| `DATABASE_URL` | Managed Postgres or a backed-up instance |
| `JWT_SECRET` | Long random value; rotating it invalidates all sessions |
| `PLATFORM_SECRETS_KEY` | Fernet key; **losing it makes stored provider credentials unreadable** |
| `WEB_ORIGIN` | Public web origin, used for CORS |
| `APP_ENV=production` | Disables `/docs` and the `create_all` safety net |
| `COOKIE_SECURE=true` | Required behind HTTPS |
| `API_ORIGIN` | Build arg for the web image; internal API URL |
| `ALLOW_PRIVATE_PROVIDER_URLS` | `true` only when Ollama or internal MCP/tool servers live on a trusted private network |
| `SSO_*` | In-app OIDC SSO; leave `SSO_ISSUER` empty to disable |
| `LOGIN_RATE_LIMIT_PER_MINUTE` / `REGISTER_RATE_LIMIT_PER_MINUTE` | Authentication throttles |
| `GATEWAY_MAX_MESSAGE_CHARS` / `GATEWAY_MAX_EXTENSION_BYTES` | Persisted output caps |

Inject secrets from the host or cloud secret store. Do not bake them into images or commit
them.

### API_ORIGIN is a build-time value

Next.js compiles rewrites into the build manifest. If the API moves, rebuild the web
image with the new `API_ORIGIN`:

```powershell
docker compose build web
```

## Topology

1. One VM or container platform (cost-conscious: a single-region VM first).
2. Managed PostgreSQL, or Postgres on the same VM with tested backups.
3. HTTPS reverse proxy in front of the web app; the API does not need to be public.
4. Ollama or an OpenAI-compatible gateway on a private network; only the platform web app is exposed.
5. MCP/tool servers reachable from the API only.

## Migrations

The API container applies `alembic upgrade head` before serving. In development the app
additionally guards `create_all` for a fresh database; that path is disabled when
`APP_ENV=production`.

Migrations `0003` and `0004` add hot-path indexes, durable idempotency, agent secrets,
tools, skills, agent `skill_ids`, and organization SSO domains. Run
`alembic upgrade head` before starting the API.

## Idempotency and rate limiting

Idempotency is stored on the `runs` row and survives restarts/replicas. Rate limiting is
still an in-process window; a single API replica is the supported topology today. Scaling
out requires a shared store (for example Redis) before relying on limits across instances.

## Backups

Dump Postgres **and** store `PLATFORM_SECRETS_KEY` with the dump. Without the key,
encrypted provider credentials cannot be recovered. The restore procedure has not been
validated in production.

## Provider upgrades

Follow upstream upgrade guides. Never use `latest` in production Compose. After upgrading,
re-run the manual smoke checklist in [`TESTING.md`](TESTING.md) against the new version.

## Optional later

Object storage, Redis, APM/OpenTelemetry, multi-instance gateway, billing provider.
