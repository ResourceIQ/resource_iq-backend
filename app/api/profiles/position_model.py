import uuid
from datetime import datetime

from sqlmodel import Field, Relationship, SQLModel


class JobPosition(SQLModel, table=True):
    """
    Model for holding pre-defined job positions.
    This ensures consistency when assigning job positions to resource profiles.
    """

    __tablename__ = "job_positions"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(
        unique=True,
        index=True,
        description="The name of the job position (e.g., 'Software Engineer')",
    )
    description: str | None = Field(
        default=None, description="Optional description of the position"
    )

    # === Timestamps ===
    created_at: datetime | None = Field(default_factory=datetime.utcnow)
    updated_at: datetime | None = Field(default_factory=datetime.utcnow)

    # === Relationships ===
    profiles: list["ResourceProfile"] = Relationship(back_populates="position")
