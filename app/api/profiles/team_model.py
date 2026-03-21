from datetime import datetime
from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.api.profiles.profile_model import ResourceProfile


class Team(SQLModel, table=True):
    """
    Model representing a team within ResourceIQ.
    Groups multiple ResourceProfiles together.
    """

    __tablename__ = "teams"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True, max_length=100)
    description: str | None = Field(default=None, max_length=500)

    # Relationship to ResourceProfiles
    profiles: list["ResourceProfile"] = Relationship(back_populates="team")

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
