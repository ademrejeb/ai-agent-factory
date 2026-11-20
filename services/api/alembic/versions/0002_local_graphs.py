"""local LangGraph definitions

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-28
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "local_graphs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "organization_id", sa.String(64), sa.ForeignKey("organizations.id"), nullable=False
        ),
        sa.Column("agent_id", sa.String(64), sa.ForeignKey("agents.id"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("nodes", sa.JSON(), nullable=False),
        sa.Column("edges", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("agent_id", name="uq_local_graphs_agent_id"),
    )
    op.create_index("ix_local_graphs_organization_id", "local_graphs", ["organization_id"])
    op.create_index("ix_local_graphs_agent_id", "local_graphs", ["agent_id"])


def downgrade() -> None:
    op.drop_index("ix_local_graphs_agent_id", table_name="local_graphs")
    op.drop_index("ix_local_graphs_organization_id", table_name="local_graphs")
    op.drop_table("local_graphs")
