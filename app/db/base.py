"""
Import all SQLModel models here so that Alembic can pick them up.
"""

from app.api.user.user_model import User  # noqa
from app.api.integrations.GitHub.github_model import GithubOrgIntBaseModel  # noqa
