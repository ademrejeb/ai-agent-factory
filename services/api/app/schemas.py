import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class RegisterRequest(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(min_length=10, max_length=72)
    organization_name: str = Field(min_length=2, max_length=200)

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not EMAIL_RE.match(value):
            raise ValueError("Enter a valid email address.")
        return value

    @field_validator("password")
    @classmethod
    def bcrypt_length(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must be at most 72 bytes.")
        return value


class LoginRequest(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(min_length=1, max_length=72)

    @field_validator("password")
    @classmethod
    def bcrypt_length(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must be at most 72 bytes.")
        return value


class WorkspaceCreate(BaseModel):
    name: str
    kind: str = "experiment"


class ProviderConnectionCreate(BaseModel):
    provider: str
    name: str
    base_url: str
    api_key: str
    workspace_id: str | None = None
    model: str | None = Field(default=None, max_length=200)


class ProviderConnectionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    base_url: str | None = Field(default=None, min_length=8, max_length=500)
    api_key: str | None = Field(default=None, min_length=1, max_length=4000)
    workspace_id: str | None = Field(default=None, max_length=200)
    model: str | None = Field(default=None, max_length=200)


class AgentCreate(BaseModel):
    workspace_id: str
    name: str
    description: str = ""
    purpose: str = ""
    tags: list[str] = Field(default_factory=list)


class AgentLinkRequest(BaseModel):
    provider_connection_id: str
    provider_resource_id: str | None = None


class AgentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    purpose: str | None = Field(default=None, max_length=4000)
    tags: list[str] | None = Field(default=None, max_length=20)
    skill_ids: list[str] | None = Field(default=None, max_length=50)
    workspace_id: str | None = None


class ToolCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    kind: Literal["http", "mcp"]
    description: str = Field(default="", max_length=4000)
    config: dict[str, Any] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    input_schema: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class ToolUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    kind: Literal["http", "mcp"] | None = None
    description: str | None = Field(default=None, max_length=4000)
    config: dict[str, Any] | None = None
    headers: dict[str, str] | None = None
    input_schema: dict[str, Any] | None = None
    enabled: bool | None = None


class ToolTestRequest(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict)


class McpDiscoverRequest(BaseModel):
    server_url: str = Field(min_length=8, max_length=500)
    headers: dict[str, str] = Field(default_factory=dict)


class SkillCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=4000)
    instructions: str = Field(min_length=1, max_length=20000)


class SkillUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=4000)
    instructions: str | None = Field(default=None, min_length=1, max_length=20000)


class KnowledgeBaseCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    description: str = Field(default="", max_length=4000)
    mode: str = Field(default="lexical", pattern="^(lexical|vector)$")
    embedding_connection_id: str | None = None
    embedding_model: str | None = Field(default=None, max_length=200)
    chunk_size: int = Field(default=1200, ge=200, le=8000)
    chunk_overlap: int = Field(default=200, ge=0, le=2000)


class KnowledgeBaseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    mode: str | None = Field(default=None, pattern="^(lexical|vector)$")
    embedding_connection_id: str | None = None
    embedding_model: str | None = Field(default=None, max_length=200)
    chunk_size: int | None = Field(default=None, ge=200, le=8000)
    chunk_overlap: int | None = Field(default=None, ge=0, le=2000)


class KnowledgeDocumentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=240)
    text: str = Field(min_length=1, max_length=2_000_000)
    mime_type: str = Field(default="text/plain", max_length=120)


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    top_k: int = Field(default=5, ge=1, le=20)


class OrganizationSwitch(BaseModel):
    organization_id: str


class RunRequest(BaseModel):
    input: dict[str, Any] = Field(default_factory=dict)
    conversation_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkflowStateRequest(BaseModel):
    blocks: dict[str, Any]
    edges: list[dict[str, Any]]
    variables: dict[str, Any] | None = None


class WorkflowDeployRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=50000)


class LocalGraphRequest(BaseModel):
    nodes: dict[str, Any]
    edges: list[dict[str, Any]]


class LocalGraphDryRunRequest(BaseModel):
    input: dict[str, Any] = Field(default_factory=dict)


ALLOWED_CREDENTIAL_SCOPES = {"agents:run", "runs:read"}


class CredentialCreate(BaseModel):
    name: str
    scopes: list[str] = Field(default_factory=lambda: ["agents:run"])

    @field_validator("scopes")
    @classmethod
    def valid_scopes(cls, value: list[str]) -> list[str]:
        unknown = set(value) - ALLOWED_CREDENTIAL_SCOPES
        if unknown:
            raise ValueError(f"Unknown scopes: {sorted(unknown)}")
        if not value:
            raise ValueError("At least one scope is required.")
        return sorted(set(value))


class AgentSecretUpsert(BaseModel):
    value: str = Field(min_length=1, max_length=4000)


class AgentFromTemplate(BaseModel):
    workspace_id: str
    name: str = Field(min_length=2, max_length=200)
    template: Literal["ticketing_dispatch", "rag_assistant"]
    provider_connection_id: str
    ticketing_base_url: str = Field(default="", max_length=500)
    ticketing_agent_key: str = Field(default="", max_length=500)
    knowledge_base_id: str | None = None
    model: str | None = Field(default=None, max_length=200)
    description: str = Field(default="", max_length=4000)
    purpose: str = Field(default="", max_length=4000)
