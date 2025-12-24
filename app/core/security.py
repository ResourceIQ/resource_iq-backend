from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


ALGORITHM = "HS256"


def create_access_token(
    subject: str | Any,
    expires_delta: timedelta,
    role: str | None = None,
) -> str:
    """
    Create a JWT access token with enhanced payload.
    
    Args:
        subject: User ID (stored as 'sub')
        expires_delta: Token expiration time
        role: User's role (e.g., 'admin', 'user')
    
    Returns:
        Encoded JWT token string
    
    Token payload includes:
        - sub: User ID
        - exp: Expiration timestamp
        - iat: Issued at timestamp
        - role: User's role
    """
    now = datetime.now(timezone.utc)
    expire = now + expires_delta
    
    to_encode = {
        "sub": str(subject),
        "exp": expire,
        "iat": now,
    }
    
    # Add role if provided
    if role:
        to_encode["role"] = role
    
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)
