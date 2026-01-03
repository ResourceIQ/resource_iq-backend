"""
Import all SQLModel models here so that Alembic can pick them up.
"""

from app.api.user.user_model import User  # noqa
from app.api.integrations.GitHub.github_model import GithubOrgIntBaseModel  # noqa
from app.api.embedding.embedding_model import GitHubPRVector  # noqa

# Jira integration models
from app.api.integrations.Jira.jira_model import (  # noqa
    JiraOrgIntegration,
    JiraIssue,
    JiraIssueVector,
    DeveloperProfile,
    JiraOAuthToken,
)
