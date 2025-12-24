"""Token schemas."""

from datetime import datetime

from sqlmodel import SQLModel


# JSON payload containing access token
class Token(SQLModel):
    """Access token schema."""

    access_token: str
    token_type: str = "bearer"


# Contents of JWT token
class TokenPayload(SQLModel):
    """
    JWT token payload schema.
    
    Fields:
        sub: User ID (subject)
        exp: Expiration timestamp
        iat: Issued at timestamp
        role: User's role
    """

    sub: str | None = None
    exp: datetime | None = None
    iat: datetime | None = None
    role: str | None = None
