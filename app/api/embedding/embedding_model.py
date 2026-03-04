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
    repo_id: int = Field(index=True)
    repo_name: str
    pr_id: str = Field(unique=True, index=True)
    pr_number: int
    author_login: str = Field(index=True)
    author_id: int = Field(index=True)
    pr_title: str
    pr_url: str
    pr_description: str | None = Field(default=None)

    # Vector embedding for similarity search (HNSW index created in migration)
    embedding: Vector = Field(sa_column=Column(Vector(dim=1536)))

    # Original context text
    context: str = Field(sa_column=Column(Text))
    metadata_json: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))

    created_at: datetime | None = Field(default_factory=datetime.utcnow)
    updated_at: datetime | None = Field(default_factory=datetime.utcnow)


class JiraIssueVector(SQLModel, table=True):
    """Model for storing Jira issue embeddings for NLP/similarity search."""

    __tablename__ = "jira_issue_vectors"

    model_config = {"arbitrary_types_allowed": True}

    id: int | None = Field(default=None, primary_key=True)
    issue_id: str = Field(unique=True, index=True)
    issue_key: str = Field(index=True)
    project_key: str = Field(index=True)
    assignee_account_id: str | None = Field(default=None, index=True)

    # Vector embedding for similarity search
    embedding: Vector = Field(sa_column=Column(Vector(dim=1536)))

    # Original context text used for embedding
    context: str = Field(sa_column=Column(Text))
    metadata_json: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))

    created_at: datetime | None = Field(default_factory=datetime.utcnow)
    updated_at: datetime | None = Field(default_factory=datetime.utcnow)
