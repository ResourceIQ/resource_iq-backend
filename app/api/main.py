from fastapi import APIRouter

from app.api.routes import private, utils
from app.api.v1.api import api_router as api_v1_router
from app.core.config import settings

api_router = APIRouter()
api_router.include_router(api_v1_router)
api_router.include_router(utils.router)


if settings.ENVIRONMENT == "local":
    api_router.include_router(private.router)
