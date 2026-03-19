"""Schemas for Job Position."""

from datetime import datetime

from pydantic import BaseModel, Field


class JobPositionBase(BaseModel):
    name: str = Field(
        description="The name of the job position (e.g., 'Software Engineer')"
    )
    description: str | None = Field(
        default=None, description="Optional description of the position"
    )


class JobPositionCreate(JobPositionBase):
    pass


class JobPositionUpdate(BaseModel):
    name: str | None = Field(default=None, description="The name of the job position")
    description: str | None = Field(
        default=None, description="Optional description of the position"
    )


class JobPositionResponse(JobPositionBase):
    id: int
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}
