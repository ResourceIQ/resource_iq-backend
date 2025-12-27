from collections.abc import Generator
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from pydantic import ValidationError
from sqlmodel import Session

from app.api.auth.auth_token import TokenPayload
from app.api.user.user_model import Role, User
from app.core import security
from app.core.config import settings
from app.db.session import engine

reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/login/access-token"
)


def get_db() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_db)]
TokenDep = Annotated[str, Depends(reusable_oauth2)]


def get_token_payload(token: TokenDep) -> TokenPayload:
    """
    Decode and return the token payload without DB lookup.
    Use this for fast, stateless authentication when you don't need
    the full user object from the database.
    """
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
        return TokenPayload(**payload)
    except (InvalidTokenError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials",
        )


def get_current_user(session: SessionDep, token: TokenDep) -> User:
    """
    Decode token and fetch user from database.
    This ensures you always have the latest user data (role, active status, etc.)
    """
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
        token_data = TokenPayload(**payload)
    except (InvalidTokenError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials",
        )
    user = session.get(User, token_data.sub)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return user


# Type alias for token payload (fast, no DB lookup)
TokenPayloadDep = Annotated[TokenPayload, Depends(get_token_payload)]

# Type alias for full user object (with DB lookup)
CurrentUser = Annotated[User, Depends(get_current_user)]


class RoleChecker:
    """
    Dependency class for role-based access control.

    Usage:
        @router.get("/admin-only", dependencies=[Depends(RoleChecker([Role.ADMIN]))])
        def admin_endpoint():
            ...

        @router.get("/mod-or-admin", dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))])
        def mod_endpoint():
            ...
    """

    def __init__(self, allowed_roles: list[Role]):
        self.allowed_roles = allowed_roles

    def __call__(self, current_user: CurrentUser) -> User:
        if current_user.role not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{current_user.role.value}' is not authorized. Required: {[r.value for r in self.allowed_roles]}",
            )
        return current_user


# Pre-defined role dependencies for convenience
def require_admin(current_user: CurrentUser) -> User:
    """Require ADMIN role."""
    if current_user.role != Role.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required"
        )
    return current_user


def require_moderator_or_admin(current_user: CurrentUser) -> User:
    """Require MODERATOR or ADMIN role."""
    if current_user.role not in [Role.ADMIN, Role.MODERATOR]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Moderator or admin access required",
        )
    return current_user


# Type aliases for cleaner endpoint signatures
AdminUser = Annotated[User, Depends(require_admin)]
ModeratorUser = Annotated[User, Depends(require_moderator_or_admin)]
