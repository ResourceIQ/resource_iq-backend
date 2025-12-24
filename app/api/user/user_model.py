"""User model."""

import uuid
from enum import Enum

from sqlmodel import Field, SQLModel


class Role(str, Enum):
    """User roles for RBAC."""
    
    ADMIN = "admin"
    MODERATOR = "moderator"
    USER = "user"
    GUEST = "guest"


class UserBase(SQLModel):
    """Shared user properties."""

    email: str = Field(unique=True, index=True, max_length=255)
    is_active: bool = True
    is_superuser: bool = False
    full_name: str | None = Field(default=None, max_length=255)
    role: Role = Field(default=Role.USER)


class User(UserBase, table=True):
    """Database model, database table inferred from class name."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    hashed_password: str

class Message(SQLModel):
    message: str
