from functools import lru_cache
from urllib.parse import urlsplit

from cryptography.fernet import Fernet
from pydantic_settings import BaseSettings, SettingsConfigDict

ALLOWED_ENVS = {"development", "test", "staging", "production"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    platform_name: str = "AI Agent Factory"
    app_env: str = "development"
    api_public_url: str = "http://localhost:8080"
    web_origin: str = "http://localhost:3100"
    database_url: str = "sqlite+pysqlite:///:memory:"
    jwt_secret: str = "dev-only-change-me-32-characters-min"
    jwt_ttl_minutes: int = 720
    platform_secrets_key: str = ""
    bootstrap_admin_email: str = ""
    bootstrap_admin_password: str = ""
    # Optional: provision the ticketing dispatcher template once at startup.
    # Requires an existing OpenAI-compatible connection in the organization.
    bootstrap_ticketing_base_url: str = ""
    bootstrap_ticketing_agent_key: str = ""
    bootstrap_ticketing_model: str = ""
    bootstrap_ticketing_org_slug: str = ""
    gateway_max_body_bytes: int = 262144
    gateway_timeout_seconds: float = 60.0
    gateway_rate_limit_per_minute: int = 60
    login_rate_limit_per_minute: int = 10
    register_rate_limit_per_minute: int = 5
    gateway_max_message_chars: int = 8_000
    gateway_max_extension_bytes: int = 32_000
    http_node_max_response_bytes: int = 2_000_000
    # Retrieval scans at most this many chunks per knowledge base and run.
    # Bases are meant for policy/FAQ corpora, not a general search engine.
    knowledge_max_chunks_per_run: int = 5_000
    # None means "allow private targets only outside production". Set it
    # explicitly when a production deployment talks to Ollama or internal
    # MCP/tool servers.
    allow_private_provider_urls: bool | None = None
    # Only enable behind a reverse proxy that overwrites X-Forwarded-For.
    trust_forwarded_for: bool = False
    cookie_secure: bool = False
    # In-app OIDC SSO. Leave SSO_ISSUER empty to disable the SSO button.
    sso_issuer: str = ""
    sso_client_id: str = ""
    sso_client_secret: str = ""
    sso_button_label: str = "Continue with SSO"
    sso_scopes: str = "openid email profile"
    sso_redirect_uri: str = ""
    sso_allowed_domains: str = ""
    sso_role_claim: str = "role"
    sso_default_role: str = "member"
    sso_auto_create_org: bool = True
    sso_default_org_slug: str = ""

    @property
    def is_production(self) -> bool:
        return self.app_env in {"production", "staging"}

    @property
    def is_dev(self) -> bool:
        return not self.is_production

    @property
    def private_urls_allowed(self) -> bool:
        if self.allow_private_provider_urls is not None:
            return self.allow_private_provider_urls
        return not self.is_production

    @property
    def sso_enabled(self) -> bool:
        return bool(self.sso_issuer.strip() and self.sso_client_id.strip())

    @property
    def sso_callback_url(self) -> str:
        if self.sso_redirect_uri.strip():
            return self.sso_redirect_uri.strip()
        # The browser talks to Next.js, which proxies /backend-api to this API.
        # Keeping the callback on the web origin makes the session cookie
        # first-party, exactly like the password login route.
        return f"{self.web_origin.rstrip('/')}/backend-api/api/v1/auth/sso/callback"

    @property
    def sso_domains(self) -> list[str]:
        return [
            item.strip().lower()
            for item in self.sso_allowed_domains.split(",")
            if item.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if settings.app_env not in ALLOWED_ENVS:
        raise RuntimeError(
            f"APP_ENV must be one of {sorted(ALLOWED_ENVS)}, got {settings.app_env!r}."
        )
    if settings.is_production:
        if settings.jwt_secret == "dev-only-change-me-32-characters-min" or len(
            settings.jwt_secret
        ) < 32:
            raise RuntimeError("JWT_SECRET must be a generated secret of at least 32 characters.")
        try:
            Fernet(settings.platform_secrets_key.encode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("PLATFORM_SECRETS_KEY must be a valid Fernet key.") from exc
        if not settings.cookie_secure:
            raise RuntimeError("COOKIE_SECURE must be true outside local development.")
        if settings.database_url.startswith("sqlite"):
            raise RuntimeError("Production must use PostgreSQL, not SQLite.")
        for name in ("api_public_url", "web_origin"):
            value = getattr(settings, name)
            if urlsplit(value).scheme != "https":
                raise RuntimeError(f"{name.upper()} must use HTTPS in production.")
        if settings.bootstrap_admin_password and len(settings.bootstrap_admin_password) < 12:
            raise RuntimeError("BOOTSTRAP_ADMIN_PASSWORD must be at least 12 characters.")
    return settings
