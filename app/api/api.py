"""V1 API endpoints."""

from fastapi import APIRouter

from app.api.auth import auth_route
from app.api.embedding import embedding_route
from app.api.integrations.GitHub import github_route, github_webhook
from app.api.integrations.Jira import jira_route, jira_webhook
from app.api.profiles import profile_route
from app.api.user import user_route

api_router = APIRouter()
api_router.include_router(auth_route.router)
api_router.include_router(user_route.router)
api_router.include_router(profile_route.router)
api_router.include_router(github_webhook.router)
api_router.include_router(github_route.router)
api_router.include_router(jira_route.router)
api_router.include_router(jira_webhook.router)
api_router.include_router(embedding_route.router)
