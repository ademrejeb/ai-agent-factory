import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.body_limit import BodySizeLimitMiddleware
from app.config import Settings, get_settings
from app.db import SessionLocal, engine
from app.errors import AppError, app_error_handler
from app.ids import new_id
from app.logging import configure_logging
from app.models import Base, Membership, Organization, User, Workspace
from app.routers import (
    agents,
    auth,
    credentials,
    gateway,
    health,
    overview,
    provider_catalog,
    providers,
    runs,
    skills,
    sso,
    tools,
    workspaces,
)
from app.security import hash_password

settings = get_settings()
logger = logging.getLogger("app.bootstrap")


def _bootstrap_admin(config: Settings) -> None:
    """Create the first user/org/workspace when explicitly configured.

    This is a convenience for local and container bootstrapping. It is a no-op
    once any user exists and never overwrites credentials.
    """
    if not config.bootstrap_admin_email or not config.bootstrap_admin_password:
        return
    with SessionLocal() as db:
        if db.query(User).first():
            return
        now = datetime.now(UTC)
        email = config.bootstrap_admin_email.strip().lower()
        user = User(
            id=new_id("user"),
            email=email,
            password_hash=hash_password(config.bootstrap_admin_password),
            created_at=now,
        )
        org = Organization(
            id=new_id("org"),
            name="Default organization",
            slug=f"default-{new_id('s')[-8:]}",
            created_at=now,
        )
        db.add_all(
            [
                user,
                org,
                Membership(
                    id=new_id("mem"),
                    user_id=user.id,
                    organization_id=org.id,
                    role="owner",
                    created_at=now,
                ),
                Workspace(
                    id=new_id("ws"),
                    organization_id=org.id,
                    name="Experiments",
                    slug="experiments",
                    kind="experiment",
                    created_at=now,
                ),
            ]
        )
        db.commit()
        logger.info("bootstrap admin created")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    configure_logging()
    if settings.is_dev:
        if not settings.platform_secrets_key.strip():
            logger.warning(
                "PLATFORM_SECRETS_KEY is unset. A random development key is generated in "
                "memory, so provider connections created by this process cannot be decrypted "
                "after a restart. Set PLATFORM_SECRETS_KEY for persistent local data."
            )
        # Production deployments must run `alembic upgrade head` instead of
        # letting the application mutate the schema at startup.
        Base.metadata.create_all(bind=engine)
    _bootstrap_admin(settings)
    if settings.bootstrap_ticketing_base_url.strip():
        try:
            from app.db import SessionLocal as BootstrapSession
            from app.services.bootstrap import ensure_ticketing_agent

            with BootstrapSession() as db:
                ensure_ticketing_agent(settings, db)
        except Exception:  # noqa: BLE001 - startup must not fail on optional seeding
            logger.exception("Ticketing dispatcher bootstrap failed")
    yield


app = FastAPI(
    title=settings.platform_name,
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.is_dev else None,
)

app.add_middleware(
    BodySizeLimitMiddleware,
    max_bytes=settings.gateway_max_body_bytes,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.web_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)

app.add_exception_handler(AppError, app_error_handler)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    details = {"fields": [{"path": list(err["loc"]), "message": err["msg"]} for err in exc.errors()]}
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "invalid_request",
                "message": "Request validation failed.",
                "details": details,
            }
        },
    )


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid4())
    # Downstream handlers use this for run correlation so the value stored in
    # the run always matches the X-Request-ID header returned to the caller.
    request.state.request_id = request_id
    if request.method in {"POST", "PUT", "PATCH"}:
        content_length = request.headers.get("content-length")
        try:
            too_large = bool(content_length) and int(content_length) > settings.gateway_max_body_bytes
        except ValueError:
            too_large = True
        if too_large:
            return JSONResponse(
                status_code=413,
                content={
                    "error": {
                        "code": "payload_too_large",
                        "message": "Request body exceeds the configured limit.",
                        "details": {},
                    }
                },
                headers={"X-Request-ID": request_id},
            )
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


app.include_router(health.router)
app.include_router(auth.router)
app.include_router(sso.router)
app.include_router(workspaces.router)
app.include_router(provider_catalog.router)
app.include_router(providers.router)
app.include_router(agents.router)
app.include_router(tools.router)
app.include_router(skills.router)
app.include_router(runs.router)
app.include_router(credentials.router)
app.include_router(overview.router)
app.include_router(gateway.router)
