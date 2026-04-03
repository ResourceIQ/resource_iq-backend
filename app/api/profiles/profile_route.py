"""API routes for resource profiles."""

import uuid
from datetime import datetime
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import selectinload

from app.api.integrations.Jira.jira_service import JiraIntegrationService
from app.api.profiles.profile_model import ResourceProfile
from app.api.profiles.profile_schema import (
    GitHubConnectionRequest,
    JiraConnectionRequest,
    ProfileMatchResponse,
    ProfileWorkload,
    ResourceProfileCreate,
    ResourceProfileResponse,
    UpdateMyProfileRequest,
    UpdateProfileRequest,
    UpdateSkillsRequest,
)
from app.api.profiles.profile_service import ProfileService
from app.api.user.user_model import Role
from app.utils.deps import CurrentUser, RoleChecker, SessionDep

router = APIRouter(prefix="/profiles", tags=["profiles"])


def _to_response(profile: ResourceProfile) -> ResourceProfileResponse:
    """Convert ResourceProfile model to response schema."""
    return ResourceProfileResponse(
        id=profile.id or 0,
        user_id=profile.user_id,
        phone_number=profile.phone_number,
        address=profile.address,
        position_id=profile.position_id,
        position=profile.position.name if profile.position else None,
        team_id=profile.team_id,
        jira_account_id=profile.jira_account_id,
        jira_display_name=profile.jira_display_name,
        jira_email=profile.jira_email,
        jira_avatar_url=profile.jira_avatar_url,
        jira_connected_at=profile.jira_connected_at,
        has_jira=profile.jira_account_id is not None,
        github_id=profile.github_id,
        github_login=profile.github_login,
        github_display_name=profile.github_display_name,
        github_email=profile.github_email,
        github_avatar_url=profile.github_avatar_url,
        github_connected_at=profile.github_connected_at,
        has_github=profile.github_id is not None or profile.github_login is not None,
        burnout_level=profile.burnout_level or 0.0,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


@router.get("/me", response_model=ResourceProfileResponse)
async def get_my_profile(
    session: SessionDep, current_user: CurrentUser
) -> ResourceProfileResponse:
    """Get the current user's resource profile."""
    profile = ProfileService(session).get_or_create_profile(current_user.id)
    return _to_response(profile)


@router.patch(
    "/me",
    response_model=ResourceProfileResponse,
    dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR, Role.USER]))],
)
async def update_my_profile(
    session: SessionDep,
    current_user: CurrentUser,
    request: UpdateMyProfileRequest,
) -> ResourceProfileResponse:
    """Partially update the current user's own profile."""
    profile = ProfileService(session).update_profile_for_user(
        current_user.id,
        request,
        allow_position_update=current_user.role in [Role.ADMIN, Role.MODERATOR],
        create_if_missing=True,
    )

    return _to_response(profile)


@router.patch(
    "/{user_id}",
    response_model=ResourceProfileResponse,
    dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))],
)
async def update_profile_by_user_id(
    session: SessionDep,
    user_id: uuid.UUID,
    request: UpdateProfileRequest,
) -> ResourceProfileResponse:
    """Partially update a target user's profile (admin/moderator only)."""
    profile = ProfileService(session).update_profile_for_user(
        user_id,
        request,
        allow_position_update=True,
        create_if_missing=True,
    )

    return _to_response(profile)


@router.post(
    "/",
    response_model=ResourceProfileResponse,
    dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))],
)
async def create_profile(
    session: SessionDep, request: ResourceProfileCreate
) -> ResourceProfileResponse:
    """Create a new resource profile for a user."""
    # Check if profile already exists
    existing = (
        session.query(ResourceProfile)
        .filter(cast(Any, ResourceProfile.user_id == request.user_id))
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=400, detail="Profile already exists for this user"
        )

    if request.position_id is not None:
        from app.api.profiles.position_model import JobPosition

        position = session.get(JobPosition, request.position_id)
        if not position:
            raise HTTPException(
                status_code=400, detail="Invalid position_id: Job position not found"
            )

    profile = ResourceProfile(
        user_id=request.user_id,
        position_id=request.position_id,
    )
    session.add(profile)
    session.commit()
    session.refresh(profile)

    return _to_response(profile)


@router.get(
    "/",
    response_model=list[ResourceProfileResponse],
    dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR, Role.USER]))],
)
async def list_profiles(
    session: SessionDep,
    has_jira: bool | None = Query(default=None, description="Filter by Jira connected"),
    has_github: bool | None = Query(
        default=None, description="Filter by GitHub connected"
    ),
    limit: int = Query(default=50, ge=1, le=500),
) -> list[ResourceProfileResponse]:
    """List all resource profiles with optional filters."""
    query = session.query(ResourceProfile).options(
        selectinload(cast(Any, ResourceProfile.position))
    )

    if has_jira is True:
        query = query.filter(cast(Any, ResourceProfile.jira_account_id).isnot(None))
    elif has_jira is False:
        query = query.filter(cast(Any, ResourceProfile.jira_account_id).is_(None))

    if has_github is True:
        query = query.filter(cast(Any, ResourceProfile.github_login).isnot(None))
    elif has_github is False:
        query = query.filter(cast(Any, ResourceProfile.github_login).is_(None))

    profiles = query.limit(limit).all()
    return [_to_response(p) for p in profiles]


@router.get(
    "/workloads",
    response_model=list[ProfileWorkload],
    dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))],
)
async def get_all_workloads(
    session: SessionDep,
    sort_by: str = Query(default="total", description="Sort by: total, jira, github"),
) -> list[ProfileWorkload]:
    """Get workload metrics for all profiles, sorted by workload."""
    _ = sort_by
    profiles = session.query(ResourceProfile).all()

    jira_counts = JiraIntegrationService(session).get_live_assignee_workload_map(
        [p.jira_account_id for p in profiles if p.jira_account_id]
    )

    workloads = [
        ProfileWorkload(
            user_id=p.user_id,
            display_name=p.jira_display_name or p.github_display_name,
            jira_workload=(
                jira_counts.get(p.jira_account_id, 0) if p.jira_account_id else 0
            ),
            total_workload=(
                jira_counts.get(p.jira_account_id, 0) if p.jira_account_id else 0
            ),
            last_updated=None,
        )
        for p in profiles
    ]

    # Sort by specified field (ascending - least busy first)
    workloads.sort(key=lambda w: w.total_workload)

    return workloads


@router.get("/by-jira/{jira_account_id}", response_model=ResourceProfileResponse)
async def get_profile_by_jira(
    session: SessionDep, jira_account_id: str
) -> ResourceProfileResponse:
    """Get a resource profile by Jira account ID."""
    profile = (
        session.query(ResourceProfile)
        .filter(cast(Any, ResourceProfile.jira_account_id == jira_account_id))
        .first()
    )

    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    return _to_response(profile)


@router.get("/by-github/{github_login}", response_model=ResourceProfileResponse)
async def get_profile_by_github(
    session: SessionDep, github_login: str
) -> ResourceProfileResponse:
    """Get a resource profile by GitHub login."""
    profile = (
        session.query(ResourceProfile)
        .filter(cast(Any, ResourceProfile.github_login == github_login))
        .first()
    )

    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    return _to_response(profile)


@router.post("/me/connect/jira", response_model=ResourceProfileResponse)
async def connect_jira(
    session: SessionDep, current_user: CurrentUser, request: JiraConnectionRequest
) -> ResourceProfileResponse:
    """Connect Jira account to current user's profile."""
    profile = ProfileService(session).connect_jira_for_user(current_user.id, request)

    return _to_response(profile)


@router.post("/me/connect/github", response_model=ResourceProfileResponse)
async def connect_github(
    session: SessionDep, current_user: CurrentUser, request: GitHubConnectionRequest
) -> ResourceProfileResponse:
    """Connect GitHub account to current user's profile."""
    profile = ProfileService(session).connect_github_for_user(current_user.id, request)

    return _to_response(profile)


@router.delete("/me/disconnect/jira", response_model=ResourceProfileResponse)
async def disconnect_jira(
    session: SessionDep, current_user: CurrentUser
) -> ResourceProfileResponse:
    """Disconnect Jira account from current user's profile."""
    profile = (
        session.query(ResourceProfile)
        .filter(cast(Any, ResourceProfile.user_id == current_user.id))
        .first()
    )

    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    profile.jira_account_id = None
    profile.jira_display_name = None
    profile.jira_email = None
    profile.jira_avatar_url = None
    profile.jira_connected_at = None
    profile.updated_at = datetime.utcnow()

    session.commit()
    session.refresh(profile)

    return _to_response(profile)


@router.delete("/me/disconnect/github", response_model=ResourceProfileResponse)
async def disconnect_github(
    session: SessionDep, current_user: CurrentUser
) -> ResourceProfileResponse:
    """Disconnect GitHub account from current user's profile."""
    profile = (
        session.query(ResourceProfile)
        .filter(cast(Any, ResourceProfile.user_id == current_user.id))
        .first()
    )

    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    profile.github_id = None
    profile.github_login = None
    profile.github_display_name = None
    profile.github_email = None
    profile.github_avatar_url = None
    profile.github_connected_at = None
    profile.updated_at = datetime.utcnow()

    session.commit()
    session.refresh(profile)

    return _to_response(profile)


@router.put(
    "/me/skills",
    response_model=ResourceProfileResponse,
    dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))],
)
async def update_skills(
    session: SessionDep, current_user: CurrentUser, request: UpdateSkillsRequest
) -> ResourceProfileResponse:
    """Update profile metadata for current user's profile."""
    profile = ProfileService(session).update_position_for_user(
        current_user.id,
        request.position_id,
    )

    return _to_response(profile)


@router.get("/match-jira-github", response_model=list[ProfileMatchResponse])
async def match_jira_github_profiles(
    session: SessionDep,
    threshold: float = Query(
        default=75.0, ge=0.0, le=100.0, description="Matching threshold (0-100)"
    ),
) -> list[ProfileMatchResponse]:
    """Match Jira and GitHub accounts into unified resource profiles."""

    profile_service = ProfileService(session)
    matched_profiles = profile_service.match_jira_github(threshold=threshold)
    return matched_profiles


# Place the dynamic user_id route at the end to avoid shadowing static paths
@router.get("/{user_id}", response_model=ResourceProfileResponse)
async def get_profile(
    session: SessionDep, user_id: uuid.UUID
) -> ResourceProfileResponse:
    """Get a resource profile by user ID."""
    profile = (
        session.query(ResourceProfile)
        .filter(cast(Any, ResourceProfile.user_id == user_id))
        .first()
    )

    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    return _to_response(profile)
