import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.api.profiles.position_model import JobPosition
    from app.api.profiles.team_model import Team


class ResourceProfile(SQLModel, table=True):
    """
    Profile for mapping ResourceIQ users to external integrations (Jira, GitHub, etc.).
    Has a 1-to-1 relationship with the User table.
    Supports Jira-only, GitHub-only, or both integrations.
    """

    __tablename__ = "resource_profiles"

    id: int | None = Field(default=None, primary_key=True)

    # 1-to-1 relationship with User table (required)
    user_id: uuid.UUID = Field(
        unique=True,
        index=True,
        foreign_key="user.id",
        description="ResourceIQ user UUID (1-to-1 relationship)",
    )
    phone_number: str | None = Field(default=None, description="Contact phone number")
    address: str | None = Field(
        default=None, description="Residentaial or work address"
    )

    position_id: int | None = Field(
        default=None,
        foreign_key="job_positions.id",
        description="Job position ID of the resource",
    )
    position: Optional["JobPosition"] = Relationship(back_populates="profiles")

    # === Team (optional) ===
    team_id: int | None = Field(
        default=None,
        foreign_key="teams.id",
        description="ID of the team this profile belongs to",
    )
    team: Optional["Team"] = Relationship(back_populates="profiles")

    # === Jira Integration (optional) ===
    jira_account_id: str | None = Field(
        default=None,
        unique=True,
        index=True,
        description="Jira account ID (from Atlassian)",
    )
    jira_display_name: str | None = Field(
        default=None, description="Display name from Jira"
    )
    jira_email: str | None = Field(default=None, description="Email from Jira")
    jira_avatar_url: str | None = Field(
        default=None, description="Avatar URL from Jira"
    )
    jira_connected_at: datetime | None = Field(
        default=None, description="When Jira was connected"
    )

    # === GitHub Integration (optional) ===
    github_id: int | None = Field(
        default=None,
        unique=True,
        index=True,
        description="GitHub user ID",
    )
    github_login: str | None = Field(
        default=None,
        unique=True,
        index=True,
        description="GitHub username",
    )
    github_display_name: str | None = Field(
        default=None, description="Display name from GitHub"
    )
    github_email: str | None = Field(default=None, description="Email from GitHub")
    github_avatar_url: str | None = Field(
        default=None, description="Avatar URL from GitHub"
    )
    github_connected_at: datetime | None = Field(
        default=None, description="When GitHub was connected"
    )

    # === Burnout Level ===
    burnout_level: float = Field(
        default=0.0,
        ge=0.0,
        le=10.0,
        description="User self-reported burnout level (0-10, higher means more burnout)",
        nullable=True,
    )

    # === Timestamps ===
    created_at: datetime | None = Field(default_factory=datetime.utcnow)
    updated_at: datetime | None = Field(default_factory=datetime.utcnow)

    # === Helper Properties ===
    @property
    def has_jira(self) -> bool:
        """Check if Jira is connected."""
        return self.jira_account_id is not None

    @property
    def has_github(self) -> bool:
        """Check if GitHub is connected."""
        return self.github_id is not None or self.github_login is not None
