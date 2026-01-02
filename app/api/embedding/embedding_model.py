from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector  # type: ignore[import-untyped]
from sqlalchemy import JSON, Column, Text
from sqlmodel import Field, SQLModel


class GitHubPRVector(SQLModel, table=True):
    """Model for storing GitHub PR embeddings."""

    __tablename__ = "github_pr_vectors"

    model_config = {"arbitrary_types_allowed": True}

    id: int | None = Field(default=None, primary_key=True)
    pr_id: str = Field(unique=True, index=True)
    pr_number: int
    author_login: str = Field(index=True)
    author_id: int = Field(index=True)
    pr_title: str
    pr_url: str

    # Note: Vector index should be created separately using HNSW
    embedding: Vector = Field(sa_column=Column(Vector(dim=1536)))

    # Original context text
    context: str = Field(sa_column=Column(Text))
    metadata_json: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))

    created_at: datetime | None = Field(default_factory=datetime.utcnow)
    updated_at: datetime | None = Field(default_factory=datetime.utcnow)
