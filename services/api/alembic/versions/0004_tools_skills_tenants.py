"""reusable tools, skills, and tenant SSO domains

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-16
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("sso_domain", sa.String(200), nullable=True))
    op.create_index(
        "ix_organizations_sso_domain", "organizations", ["sso_domain"], unique=True
    )
    op.add_column(
        "agents",
        sa.Column("skill_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )

    op.create_table(
        "tools",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "organization_id", sa.String(64), sa.ForeignKey("organizations.id"), nullable=False
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("headers_encrypted", sa.Text(), nullable=False),
        sa.Column("input_schema", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "name", name="uq_tools_org_name"),
    )
    op.create_index("ix_tools_organization_id", "tools", ["organization_id"])
    op.create_index("ix_tools_kind", "tools", ["kind"])

    op.create_table(
        "skills",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "organization_id", sa.String(64), sa.ForeignKey("organizations.id"), nullable=False
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "name", name="uq_skills_org_name"),
    )
    op.create_index("ix_skills_organization_id", "skills", ["organization_id"])


def downgrade() -> None:
    op.drop_index("ix_skills_organization_id", table_name="skills")
    op.drop_table("skills")
    op.drop_index("ix_tools_kind", table_name="tools")
    op.drop_index("ix_tools_organization_id", table_name="tools")
    op.drop_table("tools")
    op.drop_column("agents", "skill_ids")
    op.drop_index("ix_organizations_sso_domain", table_name="organizations")
    op.drop_column("organizations", "sso_domain")
