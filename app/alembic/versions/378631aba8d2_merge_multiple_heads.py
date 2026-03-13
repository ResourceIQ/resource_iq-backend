"""merge multiple heads

Revision ID: 378631aba8d2
Revises: a1b2c3d4e5f6, c1ebee953b49
Create Date: 2026-03-14 00:55:28.488332

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = '378631aba8d2'
down_revision = ('a1b2c3d4e5f6', 'c1ebee953b49')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
