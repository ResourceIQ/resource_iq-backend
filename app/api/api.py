"""V1 API endpoints."""

from fastapi import APIRouter

from app.api.auth import auth_route
from app.api.user import user_route
from app.api.integrations.GitHub import github_webhook
from app.api.integrations.GitHub import github_route

api_router = APIRouter()
api_router.include_router(auth_route.router)
api_router.include_router(user_route.router)
api_router.include_router(github_webhook.router)
api_router.include_router(github_route.router)
