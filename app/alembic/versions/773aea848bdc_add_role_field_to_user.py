"""Add role field to user

Revision ID: 773aea848bdc
Revises: c34a7cb4a394
Create Date: 2025-12-24 14:34:42.264953

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = '773aea848bdc'
down_revision = 'c34a7cb4a394'
branch_labels = None
depends_on = None


# Create enum type for PostgreSQL
role_enum = sa.Enum('ADMIN', 'MODERATOR', 'USER', 'GUEST', name='role')


def upgrade():
    # Create the enum type first
    role_enum.create(op.get_bind(), checkfirst=True)
    
    # Add the column with a default value for existing rows
    op.add_column('user', sa.Column('role', role_enum, nullable=False, server_default='USER'))
    
    # Update superusers to have ADMIN role
    op.execute("UPDATE \"user\" SET role = 'ADMIN' WHERE is_superuser = true")
    
    # Remove the server default after migration (optional - keeps it cleaner)
    op.alter_column('user', 'role', server_default=None)


def downgrade():
    op.drop_column('user', 'role')
    # Drop the enum type
    role_enum.drop(op.get_bind(), checkfirst=True)
