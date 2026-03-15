"""drop legacy github pr embedding btree index

Revision ID: h1a2b3c4d5e6
Revises: 378631aba8d2
Create Date: 2026-03-15 00:00:00.000000

"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "h1a2b3c4d5e6"
down_revision = "378631aba8d2"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("DROP INDEX IF EXISTS ix_github_pr_vectors_embedding")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS github_pr_vectors_embedding_hnsw_idx
        ON github_pr_vectors
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        """
    )


def downgrade():
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_github_pr_vectors_embedding ON github_pr_vectors (embedding)"
    )
