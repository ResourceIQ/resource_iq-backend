"""Token schemas."""

from sqlmodel import SQLModel


# JSON payload containing access token
class Token(SQLModel):
    """Access token schema."""

    access_token: str
    token_type: str = "bearer"


# Contents of JWT token
class TokenPayload(SQLModel):
    """JWT token payload schema."""

    sub: str | None = None
