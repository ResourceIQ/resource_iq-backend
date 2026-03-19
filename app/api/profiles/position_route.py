"""API routes for Job Positions."""

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from sqlmodel import select

from app.api.profiles.position_model import JobPosition
from app.api.profiles.position_schema import (
    JobPositionCreate,
    JobPositionResponse,
    JobPositionUpdate,
)
from app.utils.deps import CurrentUser, SessionDep

router = APIRouter(prefix="/positions", tags=["Job Positions"])


@router.post("/", response_model=JobPositionResponse)
async def create_position(
    session: SessionDep, _current_user: CurrentUser, request: JobPositionCreate
) -> Any:
    """Create a new job position."""
    existing = session.exec(
        select(JobPosition).where(JobPosition.name == request.name)
    ).first()
    if existing:
        raise HTTPException(
            status_code=400, detail="Job position with this name already exists"
        )

    position = JobPosition(name=request.name, description=request.description)
    session.add(position)
    session.commit()
    session.refresh(position)
    return position


@router.get("/", response_model=list[JobPositionResponse])
async def list_positions(
    session: SessionDep,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
) -> Any:
    """List all job positions."""
    positions = session.exec(select(JobPosition).offset(skip).limit(limit)).all()
    return positions


@router.get("/{position_id}", response_model=JobPositionResponse)
async def get_position(session: SessionDep, position_id: int) -> Any:
    """Get a job position by ID."""
    position = session.get(JobPosition, position_id)
    if not position:
        raise HTTPException(status_code=404, detail="Job position not found")
    return position


@router.patch("/{position_id}", response_model=JobPositionResponse)
async def update_position(
    session: SessionDep,
    _current_user: CurrentUser,
    position_id: int,
    request: JobPositionUpdate,
) -> Any:
    """Update a job position."""
    position = session.get(JobPosition, position_id)
    if not position:
        raise HTTPException(status_code=404, detail="Job position not found")

    update_data = request.model_dump(exclude_unset=True)
    if "name" in update_data:
        existing = session.exec(
            select(JobPosition).where(JobPosition.name == update_data["name"])
        ).first()
        if existing and existing.id != position_id:
            raise HTTPException(
                status_code=400, detail="Job position with this name already exists"
            )

    for field, value in update_data.items():
        setattr(position, field, value)

    session.add(position)
    session.commit()
    session.refresh(position)
    return position


@router.delete("/{position_id}")
async def delete_position(
    session: SessionDep, _current_user: CurrentUser, position_id: int
) -> dict[str, str]:
    """Delete a job position."""
    position = session.get(JobPosition, position_id)
    if not position:
        raise HTTPException(status_code=404, detail="Job position not found")

    session.delete(position)
    session.commit()
    return {"message": "Job position deleted successfully"}
