"""Add contact info columns manually

Revision ID: c1ebee953b49
Revises: ac132f3139d2
Create Date: 2026-03-10 21:42:34.233663

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = 'c1ebee953b49'
down_revision = 'ac132f3139d2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('resource_profiles', sa.Column('phone_number', sa.String(), nullable=True))
    op.add_column('resource_profiles', sa.Column('address', sa.String(), nullable=True))
    


def downgrade()-> None:
    op.drop_column('resource_profiles','phone_number')
    op.drop_column('resource_profiles','address')
    
