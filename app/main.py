import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI
from fastapi.routing import APIRoute
from neomodel import config as neomodel_config
from starlette.middleware.cors import CORSMiddleware

from app.api.main import api_router
from app.core.config import settings

logger = logging.getLogger(__name__)
logging.getLogger("neo4j.notifications").setLevel(logging.WARNING)


def custom_generate_unique_id(route: APIRoute) -> str:
    return f"{route.tags[0]}-{route.name}"


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup and shutdown events."""
    if settings.neo4j_enabled:
        neomodel_config.DATABASE_URL = settings.neo4j_dsn  # type: ignore[attr-defined]
        if settings.NEO4J_DATABASE:
            neomodel_config.DATABASE_NAME = settings.NEO4J_DATABASE  # type: ignore[attr-defined]

    # Startup: Initialize test profiles
    # logger.info("Starting up - initializing test profiles...")
    # try:
    #     from app.api.profiles.profile_init import init_test_profiles

    #     with Session(engine) as db:
    #         init_test_profiles(db)
    # except Exception as e:
    #     logger.warning(f"Could not initialize test profiles: {str(e)}")

    yield

    # Shutdown
    logger.info("Shutting down...")


if settings.SENTRY_DSN and settings.ENVIRONMENT != "local":
    sentry_sdk.init(dsn=str(settings.SENTRY_DSN), enable_tracing=True)

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    generate_unique_id_function=custom_generate_unique_id,
    lifespan=lifespan,
)

# Set all CORS enabled origins
if settings.all_cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.all_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(api_router, prefix=settings.API_V1_STR)
