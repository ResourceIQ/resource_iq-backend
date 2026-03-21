from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.profiles.team_model import Team
from app.api.profiles.team_schema import TeamCreate, TeamResponse, TeamUpdate
from app.api.profiles.team_service import TeamService
from app.api.user.user_model import Role
from app.utils.deps import RoleChecker, SessionDep

router = APIRouter(prefix="/teams", tags=["teams"])


@router.post(
    "/",
    response_model=TeamResponse,
    dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))],
)
def create_team(session: SessionDep, team_in: TeamCreate) -> Team:
    """Create a new team."""
    service = TeamService(session)
    return service.create_team(team_in)


@router.get("/", response_model=list[TeamResponse])
def list_teams(
    session: SessionDep,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[Team]:
    """List all teams."""
    service = TeamService(session)
    return service.list_teams(skip=skip, limit=limit)


@router.get("/{team_id}", response_model=TeamResponse)
def get_team(session: SessionDep, team_id: int) -> Team:
    """Get a team by ID."""
    service = TeamService(session)
    team = service.get_team(team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    return team


@router.patch(
    "/{team_id}",
    response_model=TeamResponse,
    dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))],
)
def update_team(session: SessionDep, team_id: int, team_in: TeamUpdate) -> Team:
    """Update a team."""
    service = TeamService(session)
    team = service.update_team(team_id, team_in)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    return team


@router.delete(
    "/{team_id}",
    dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))],
)
def delete_team(session: SessionDep, team_id: int) -> dict[str, str]:
    """Delete a team."""
    service = TeamService(session)
    success = service.delete_team(team_id)
    if not success:
        raise HTTPException(status_code=404, detail="Team not found")
    return {"message": "Team deleted successfully"}


@router.post(
    "/{team_id}/members/{profile_id}",
    dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))],
)
def add_team_member(
    session: SessionDep, team_id: int, profile_id: int
) -> dict[str, str]:
    """Add a resource profile to a team."""
    service = TeamService(session)
    success = service.add_member(team_id, profile_id)
    if not success:
        raise HTTPException(
            status_code=400, detail="Team or Resource Profile not found"
        )
    return {"message": "Member added to team successfully"}


@router.delete(
    "/{team_id}/members/{profile_id}",
    dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))],
)
def remove_team_member(
    session: SessionDep, team_id: int, profile_id: int
) -> dict[str, str]:
    """Remove a resource profile from a team."""
    service = TeamService(session)
    success = service.remove_member(team_id, profile_id)
    if not success:
        raise HTTPException(status_code=400, detail="Member not found in team")
    return {"message": "Member removed from team successfully"}
