"""production hardening: durable idempotency, indexes, agent secrets

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-15
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("idempotency_key", sa.String(200), nullable=True))
    op.create_unique_constraint(
        "uq_runs_credential_agent_idempotency",
        "runs",
        ["credential_id", "agent_id", "idempotency_key"],
    )
    op.create_index(
        "ix_runs_organization_started", "runs", ["organization_id", "started_at"]
    )
    op.create_index("ix_runs_agent_started", "runs", ["agent_id", "started_at"])
    op.create_index("ix_runs_status", "runs", ["status"])
    op.create_index("ix_runs_correlation_id", "runs", ["correlation_id"])
    op.create_index("ix_agents_lifecycle_status", "agents", ["lifecycle_status"])
    op.create_index(
        "ix_provider_connections_provider", "provider_connections", ["provider"]
    )
    op.create_unique_constraint(
        "uq_agent_versions_agent_version",
        "agent_versions",
        ["agent_id", "version"],
    )

    op.create_table(
        "agent_secrets",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(64),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column(
            "agent_id", sa.String(64), sa.ForeignKey("agents.id"), nullable=False
        ),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("value_encrypted", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("agent_id", "name"),
    )
    op.create_index(
        "ix_agent_secrets_organization_id", "agent_secrets", ["organization_id"]
    )
    op.create_index("ix_agent_secrets_agent_id", "agent_secrets", ["agent_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_secrets_agent_id", table_name="agent_secrets")
    op.drop_index("ix_agent_secrets_organization_id", table_name="agent_secrets")
    op.drop_table("agent_secrets")
    op.drop_constraint(
        "uq_agent_versions_agent_version", "agent_versions", type_="unique"
    )
    op.drop_index("ix_provider_connections_provider", table_name="provider_connections")
    op.drop_index("ix_agents_lifecycle_status", table_name="agents")
    op.drop_index("ix_runs_correlation_id", table_name="runs")
    op.drop_index("ix_runs_status", table_name="runs")
    op.drop_index("ix_runs_agent_started", table_name="runs")
    op.drop_index("ix_runs_organization_started", table_name="runs")
    op.drop_constraint(
        "uq_runs_credential_agent_idempotency", "runs", type_="unique"
    )
    op.drop_column("runs", "idempotency_key")
