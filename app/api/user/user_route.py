"""User endpoints."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import func, select

from app.api.profiles.profile_model import ResourceProfile
from app.api.user import user_service
from app.api.user.user_model import Role, User
from app.api.user.user_schema import (
    Message,
    UpdatePassword,
    UserCreate,
    UserPublic,
    UserRegister,
    UserRegisterWithProfile,
    UserRegistrationResponse,
    UsersPublic,
    UserUpdate,
    UserUpdateMe,
)
from app.core.config import settings
from app.core.security import get_password_hash, verify_password
from app.utils import generate_new_account_email, send_email
from app.utils.deps import CurrentUser, RoleChecker, SessionDep

router = APIRouter(prefix="/users", tags=["users"])


@router.get(
    "/",
    dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))],
    response_model=UsersPublic,
)
def read_users(session: SessionDep, skip: int = 0, limit: int = 100) -> Any:
    """
    Retrieve users. (Admin only)
    """

    count_statement = select(func.count()).select_from(User)
    count = session.exec(count_statement).one()

    statement = select(User).offset(skip).limit(limit)
    users = session.exec(statement).all()

    return UsersPublic(data=users, count=count)


@router.post(
    "/",
    dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))],
    response_model=UserPublic,
)
def create_user(*, session: SessionDep, user_in: UserCreate) -> Any:
    """
    Create new user. (Admin only)
    """
    user = user_service.get_user_by_email(session=session, email=user_in.email)
    if user:
        raise HTTPException(
            status_code=400,
            detail="The user with this email already exists in the system.",
        )

    user = user_service.create_user(session=session, user_create=user_in)
    if settings.emails_enabled and user_in.email:
        email_data = generate_new_account_email(
            email_to=user_in.email, username=user_in.email, password=user_in.password
        )
        send_email(
            email_to=user_in.email,
            subject=email_data.subject,
            html_content=email_data.html_content,
        )
    return user


@router.patch(
    "/me",
    response_model=UserPublic,
    dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))],
)
def update_user_me(
    *, session: SessionDep, user_in: UserUpdateMe, current_user: CurrentUser
) -> Any:
    """
    Update own user.
    """

    if user_in.email:
        existing_user = user_service.get_user_by_email(
            session=session, email=user_in.email
        )
        if existing_user and existing_user.id != current_user.id:
            raise HTTPException(
                status_code=409, detail="User with this email already exists"
            )
    user_data = user_in.model_dump(exclude_unset=True)
    current_user.sqlmodel_update(user_data)
    session.add(current_user)
    session.commit()
    session.refresh(current_user)
    return current_user


@router.patch(
    "/me/password",
    response_model=Message,
    dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))],
)
def update_password_me(
    *, session: SessionDep, body: UpdatePassword, current_user: CurrentUser
) -> Any:
    """
    Update own password.
    """
    if not verify_password(body.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect password")
    if body.current_password == body.new_password:
        raise HTTPException(
            status_code=400, detail="New password cannot be the same as the current one"
        )
    hashed_password = get_password_hash(body.new_password)
    current_user.hashed_password = hashed_password
    session.add(current_user)
    session.commit()
    return Message(message="Password updated successfully")


@router.get(
    "/me",
    response_model=UserPublic,
    dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))],
)
def read_user_me(current_user: CurrentUser) -> Any:
    """
    Get current user.
    """
    return current_user


@router.delete(
    "/me",
    response_model=Message,
    dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))],
)
def delete_user_me(session: SessionDep, current_user: CurrentUser) -> Any:
    """
    Delete own user.
    """
    if current_user.role == Role.ADMIN:
        raise HTTPException(
            status_code=403, detail="Admins are not allowed to delete themselves"
        )
    session.delete(current_user)
    session.commit()
    return Message(message="User deleted successfully")


@router.post(
    "/signup",
    response_model=UserPublic,
    dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))],
)
def register_user(session: SessionDep, user_in: UserRegister) -> Any:
    """
    Create new user without the need to be logged in.
    """
    user = user_service.get_user_by_email(session=session, email=user_in.email)
    if user:
        raise HTTPException(
            status_code=400,
            detail="The user with this email already exists in the system",
        )
    user_create = UserCreate.model_validate(user_in)
    user = user_service.create_user(session=session, user_create=user_create)
    return user


@router.post(
    "/register-with-profile",
    response_model=UserRegistrationResponse,
    dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))],
)
def register_user_with_profile(
    session: SessionDep, user_in: UserRegisterWithProfile
) -> Any:
    """
    Admin endpoint: create a user, auto-create a ResourceProfile,
    and optionally map GitHub/Jira identities in one request.
    """
    existing = user_service.get_user_by_email(session=session, email=user_in.email)
    if existing:
        raise HTTPException(
            status_code=400,
            detail="The user with this email already exists in the system",
        )

    user_create = UserCreate(
        email=user_in.email,
        password=user_in.password,
        full_name=user_in.full_name,
        role=user_in.role,
        is_active=user_in.is_active,
    )
    user = user_service.create_user(session=session, user_create=user_create)

    from datetime import datetime

    profile = ResourceProfile(
        user_id=user.id,
        position_id=user_in.position_id,
        github_id=user_in.github_id,
        github_login=user_in.github_login,
        github_display_name=user_in.github_display_name,
        github_email=user_in.github_email,
        github_avatar_url=user_in.github_avatar_url,
        github_connected_at=datetime.utcnow() if user_in.github_login else None,
        jira_account_id=user_in.jira_account_id,
        jira_display_name=user_in.jira_display_name,
        jira_email=user_in.jira_email,
        jira_avatar_url=user_in.jira_avatar_url,
        jira_connected_at=datetime.utcnow() if user_in.jira_account_id else None,
    )
    session.add(profile)
    session.commit()
    session.refresh(profile)

    return UserRegistrationResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        has_github=profile.has_github,
        github_login=profile.github_login,
        has_jira=profile.has_jira,
        jira_display_name=profile.jira_display_name,
    )


@router.get(
    "/{user_id}",
    response_model=UserPublic,
    dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))],
)
def read_user_by_id(
    user_id: uuid.UUID, session: SessionDep, current_user: CurrentUser
) -> Any:
    """
    Get a specific user by id. (Admin/Moderator can view any user)
    """
    user = session.get(User, user_id)
    if user == current_user:
        return user
    if current_user.role not in [Role.ADMIN, Role.MODERATOR]:
        raise HTTPException(
            status_code=403,
            detail=f"Role '{current_user.role.value}' is not authorized. Required: ['admin', 'moderator']",
        )
    return user


@router.patch(
    "/{user_id}",
    dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))],
    response_model=UserPublic,
)
def update_user(
    *,
    session: SessionDep,
    user_id: uuid.UUID,
    user_in: UserUpdate,
) -> Any:
    """
    Update a user. (Admin only)
    """

    db_user = session.get(User, user_id)
    if not db_user:
        raise HTTPException(
            status_code=404,
            detail="The user with this id does not exist in the system",
        )
    if user_in.email:
        existing_user = user_service.get_user_by_email(
            session=session, email=user_in.email
        )
        if existing_user and existing_user.id != user_id:
            raise HTTPException(
                status_code=409, detail="User with this email already exists"
            )

    db_user = user_service.update_user(
        session=session, db_user=db_user, user_in=user_in
    )
    return db_user


@router.delete(
    "/{user_id}", dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))]
)
def delete_user(
    session: SessionDep, current_user: CurrentUser, user_id: uuid.UUID
) -> Message:
    """
    Delete a user and their associated resource profile. (Admin only)
    """
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user == current_user:
        raise HTTPException(
            status_code=403, detail="Admins are not allowed to delete themselves"
        )

    from typing import Any, cast

    profile = (
        session.query(ResourceProfile)
        .filter(cast(Any, ResourceProfile.user_id == user_id))
        .first()
    )
    if profile:
        session.delete(profile)
        session.flush()

    session.delete(user)
    session.commit()
    return Message(message="User deleted successfully")
