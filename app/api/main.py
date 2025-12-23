from fastapi import APIRouter

from app.api.api import api_router as api_v1_router
from app.core.config import settings
from app.utils import utils

api_router = APIRouter()
api_router.include_router(api_v1_router)
api_router.include_router(utils.router)

