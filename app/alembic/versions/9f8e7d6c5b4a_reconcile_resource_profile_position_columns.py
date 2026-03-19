"""Reconcile resource_profiles position schema

Revision ID: 9f8e7d6c5b4a
Revises: 33567aa9bd58
Create Date: 2026-03-19 12:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401


# revision identifiers, used by Alembic.
revision = "9f8e7d6c5b4a"
down_revision = "33567aa9bd58"
branch_labels = None
depends_on = None


def _get_column_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    return {col["name"] for col in inspector.get_columns(table_name)}


def _has_position_fk(inspector: sa.Inspector) -> bool:
    for fk in inspector.get_foreign_keys("resource_profiles"):
        if (
            fk.get("referred_table") == "job_positions"
            and fk.get("constrained_columns") == ["position_id"]
        ):
            return True
    return False


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    columns = _get_column_names(inspector, "resource_profiles")

    if "position_id" not in columns:
        op.add_column("resource_profiles", sa.Column("position_id", sa.Integer(), nullable=True))
        inspector = sa.inspect(bind)
        columns = _get_column_names(inspector, "resource_profiles")

    if "position" in columns:
        # Backfill position_id from legacy text column where names match.
        op.execute(
            sa.text(
                """
                UPDATE resource_profiles AS rp
                SET position_id = jp.id
                FROM job_positions AS jp
                WHERE rp.position_id IS NULL
                  AND rp.position IS NOT NULL
                  AND lower(trim(rp.position)) = lower(trim(jp.name))
                """
            )
        )

    inspector = sa.inspect(bind)
    if not _has_position_fk(inspector):
        op.create_foreign_key(
            "fk_resource_profiles_position_id_job_positions",
            "resource_profiles",
            "job_positions",
            ["position_id"],
            ["id"],
        )

    inspector = sa.inspect(bind)
    columns = _get_column_names(inspector, "resource_profiles")
    if "position" in columns:
        op.drop_column("resource_profiles", "position")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    columns = _get_column_names(inspector, "resource_profiles")

    if "position" not in columns:
        op.add_column(
            "resource_profiles",
            sa.Column("position", sa.String(), nullable=True),
        )

    # Backfill legacy text position from position_id when possible.
    op.execute(
        sa.text(
            """
            UPDATE resource_profiles AS rp
            SET position = jp.name
            FROM job_positions AS jp
            WHERE rp.position_id = jp.id
              AND rp.position IS NULL
            """
        )
    )

    inspector = sa.inspect(bind)
    for fk in inspector.get_foreign_keys("resource_profiles"):
        if (
            fk.get("name")
            and fk.get("referred_table") == "job_positions"
            and fk.get("constrained_columns") == ["position_id"]
        ):
            op.drop_constraint(fk["name"], "resource_profiles", type_="foreignkey")

    inspector = sa.inspect(bind)
    columns = _get_column_names(inspector, "resource_profiles")
    if "position_id" in columns:
        op.drop_column("resource_profiles", "position_id")
