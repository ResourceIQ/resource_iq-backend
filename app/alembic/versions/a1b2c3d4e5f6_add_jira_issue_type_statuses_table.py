"""add jira_issue_type_statuses table

Revision ID: a1b2c3d4e5f6
Revises: bcbee6ff3c73
Create Date: 2026-03-11 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f6"
down_revision = "bcbee6ff3c73"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "jira_issue_type_statuses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "issue_type_id",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
        ),
        sa.Column(
            "issue_type_name",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
        ),
        sa.Column(
            "available_statuses",
            sa.JSON(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "selected_statuses",
            sa.JSON(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_jira_issue_type_statuses_issue_type_id"),
        "jira_issue_type_statuses",
        ["issue_type_id"],
        unique=True,
    )


def downgrade():
    op.drop_index(
        op.f("ix_jira_issue_type_statuses_issue_type_id"),
        table_name="jira_issue_type_statuses",
    )
    op.drop_table("jira_issue_type_statuses")
