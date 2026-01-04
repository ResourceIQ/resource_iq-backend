"""drop jira_issues table

Revision ID: e3f4g5h6i7j8
Revises: d8e9f0a1b2c3
Create Date: 2026-01-04 12:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = "e3f4g5h6i7j8"
down_revision = "d8e9f0a1b2c3"
branch_labels = None
depends_on = None


def upgrade():
    # Drop the jira_issues table as we only need vectors now
    op.drop_index("ix_jira_issues_assignee_account_id", table_name="jira_issues")
    op.drop_index("ix_jira_issues_issue_id", table_name="jira_issues")
    op.drop_index("ix_jira_issues_issue_key", table_name="jira_issues")
    op.drop_index("ix_jira_issues_project_key", table_name="jira_issues")
    op.drop_index("ix_jira_issues_status", table_name="jira_issues")
    op.drop_table("jira_issues")


def downgrade():
    # Recreate jira_issues table if needed
    op.create_table(
        "jira_issues",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("issue_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("issue_key", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("project_key", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("summary", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("issue_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("priority", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("labels", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column(
            "assignee_account_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True
        ),
        sa.Column(
            "assignee_display_name", sqlmodel.sql.sqltypes.AutoString(), nullable=True
        ),
        sa.Column("assignee_email", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column(
            "reporter_account_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True
        ),
        sa.Column(
            "reporter_display_name", sqlmodel.sql.sqltypes.AutoString(), nullable=True
        ),
        sa.Column("issue_url", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("jira_created_at", sa.DateTime(), nullable=True),
        sa.Column("jira_updated_at", sa.DateTime(), nullable=True),
        sa.Column("jira_resolved_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("comments_json", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_jira_issues_status"), "jira_issues", ["status"], unique=False
    )
    op.create_index(
        op.f("ix_jira_issues_project_key"), "jira_issues", ["project_key"], unique=False
    )
    op.create_index(
        op.f("ix_jira_issues_issue_key"), "jira_issues", ["issue_key"], unique=False
    )
    op.create_index(
        op.f("ix_jira_issues_issue_id"), "jira_issues", ["issue_id"], unique=True
    )
    op.create_index(
        op.f("ix_jira_issues_assignee_account_id"),
        "jira_issues",
        ["assignee_account_id"],
        unique=False,
    )

