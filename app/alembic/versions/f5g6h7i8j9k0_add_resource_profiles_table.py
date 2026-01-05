"""add resource_profiles table and drop developer_profiles

Revision ID: f5g6h7i8j9k0
Revises: e3f4g5h6i7j8
Create Date: 2026-01-04 14:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = "f5g6h7i8j9k0"
down_revision = "e3f4g5h6i7j8"
branch_labels = None
depends_on = None


def upgrade():
    # Create resource_profiles table
    op.create_table(
        "resource_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        # Jira fields
        sa.Column("jira_account_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column(
            "jira_display_name", sqlmodel.sql.sqltypes.AutoString(), nullable=True
        ),
        sa.Column("jira_email", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("jira_avatar_url", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("jira_connected_at", sa.DateTime(), nullable=True),
        # GitHub fields
        sa.Column("github_id", sa.Integer(), nullable=True),
        sa.Column("github_login", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column(
            "github_display_name", sqlmodel.sql.sqltypes.AutoString(), nullable=True
        ),
        sa.Column("github_email", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column(
            "github_avatar_url", sqlmodel.sql.sqltypes.AutoString(), nullable=True
        ),
        sa.Column("github_connected_at", sa.DateTime(), nullable=True),
        # Skills & domains
        sa.Column("skills", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("domains", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        # Workload
        sa.Column("jira_workload", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("github_workload", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_workload", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("workload_updated_at", sa.DateTime(), nullable=True),
        # Timestamps
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        # Constraints
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
    )

    # Create indexes
    op.create_index(
        op.f("ix_resource_profiles_user_id"),
        "resource_profiles",
        ["user_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_resource_profiles_jira_account_id"),
        "resource_profiles",
        ["jira_account_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_resource_profiles_github_id"),
        "resource_profiles",
        ["github_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_resource_profiles_github_login"),
        "resource_profiles",
        ["github_login"],
        unique=True,
    )

    # Drop old developer_profiles table
    op.drop_index("ix_developer_profiles_jira_account_id", table_name="developer_profiles")
    op.drop_index("ix_developer_profiles_github_login", table_name="developer_profiles")
    op.drop_index("ix_developer_profiles_internal_user_id", table_name="developer_profiles")
    op.drop_table("developer_profiles")


def downgrade():
    # Recreate developer_profiles table
    op.create_table(
        "developer_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "jira_account_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True
        ),
        sa.Column(
            "jira_display_name", sqlmodel.sql.sqltypes.AutoString(), nullable=True
        ),
        sa.Column("jira_email", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("github_login", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("github_id", sa.Integer(), nullable=True),
        sa.Column(
            "internal_user_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True
        ),
        sa.Column("skills", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("domains", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("current_workload", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("workload_updated_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_developer_profiles_internal_user_id",
        "developer_profiles",
        ["internal_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_developer_profiles_github_login",
        "developer_profiles",
        ["github_login"],
        unique=True,
    )
    op.create_index(
        "ix_developer_profiles_jira_account_id",
        "developer_profiles",
        ["jira_account_id"],
        unique=True,
    )

    # Drop resource_profiles
    op.drop_index(
        op.f("ix_resource_profiles_github_login"), table_name="resource_profiles"
    )
    op.drop_index(
        op.f("ix_resource_profiles_github_id"), table_name="resource_profiles"
    )
    op.drop_index(
        op.f("ix_resource_profiles_jira_account_id"), table_name="resource_profiles"
    )
    op.drop_index(op.f("ix_resource_profiles_user_id"), table_name="resource_profiles")
    op.drop_table("resource_profiles")

