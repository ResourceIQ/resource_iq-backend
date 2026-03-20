"""User schemas for data validation."""

import uuid
from datetime import datetime

from pydantic import EmailStr
from sqlmodel import Field, SQLModel

from app.api.user.user_model import Role


# Properties to receive via API on creation
class UserCreate(SQLModel):
    """User creation schema."""

    email: EmailStr = Field(unique=True, index=True, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    is_active: bool = True
    is_superuser: bool = False
    full_name: str | None = Field(default=None, max_length=255)
    role: Role = Role.USER


class UserRegister(SQLModel):
    """User registration schema."""

    email: EmailStr = Field(max_length=255)
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)


# Properties to receive via API on update, all are optional
class UserUpdate(SQLModel):
    """User update schema."""

    email: EmailStr | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, min_length=8, max_length=128)
    is_active: bool | None = None
    is_superuser: bool | None = None
    full_name: str | None = Field(default=None, max_length=255)
    role: Role | None = None


class UserUpdateMe(SQLModel):
    """User self-update schema."""

    full_name: str | None = Field(default=None, max_length=255)
    email: EmailStr | None = Field(default=None, max_length=255)


class UpdatePassword(SQLModel):
    """Password update schema."""

    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


# Properties to return via API, id is always required
class UserPublic(SQLModel):
    """Public user schema."""

    id: uuid.UUID
    email: EmailStr
    is_active: bool = True
    is_superuser: bool = False
    full_name: str | None = None
    role: Role = Role.USER


class UsersPublic(SQLModel):
    """Multiple users public schema."""

    data: list[UserPublic]
    count: int


# Generic message
class Message(SQLModel):
    """Generic message schema."""

    message: str


class NewPassword(SQLModel):
    """New password reset schema."""

    token: str
    new_password: str = Field(min_length=8, max_length=128)


class UserRegisterWithProfile(SQLModel):
    """Admin registration schema: creates user + ResourceProfile with optional GitHub/Jira mapping."""

    email: EmailStr = Field(max_length=255)
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)
    role: Role = Role.USER
    is_active: bool = True

    # Optional GitHub mapping
    github_id: int | None = None
    github_login: str | None = None
    github_display_name: str | None = None
    github_email: str | None = None
    github_avatar_url: str | None = None

    # Optional Jira mapping
    jira_account_id: str | None = None
    jira_display_name: str | None = None
    jira_email: str | None = None
    jira_avatar_url: str | None = None


class UserRegistrationResponse(SQLModel):
    """Response for admin user registration with profile info."""

    id: uuid.UUID
    email: str
    full_name: str | None = None
    role: Role = Role.USER
    is_active: bool = True

    # Profile connection status
    has_github: bool = False
    github_login: str | None = None
    has_jira: bool = False
    jira_display_name: str | None = None
