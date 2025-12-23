"""User schemas for data validation."""

import uuid

from pydantic import EmailStr
from sqlmodel import Field, SQLModel


# Properties to receive via API on creation
class UserCreate(SQLModel):
    """User creation schema."""

    email: EmailStr = Field(unique=True, index=True, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    is_active: bool = True
    is_superuser: bool = False
    full_name: str | None = Field(default=None, max_length=255)


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
