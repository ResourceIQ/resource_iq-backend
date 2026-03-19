import logging
from typing import Any, cast

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlmodel import Session

from app.api.knowledge_graph.kg_extractor import LLMEntityExtractor
from app.api.knowledge_graph.kg_build_service import KGBuildService
from app.api.knowledge_graph.kg_schema import (
    KGLearningIntentEntities,
    KGLearningIntentRequest,
    KGLearningIntentResponse,
)
from app.api.knowledge_graph.kg_service import KnowledgeGraphService
from app.api.profiles.profile_model import ResourceProfile
from app.api.user.user_model import Role
from app.db.session import engine
from app.utils.deps import CurrentUser, RoleChecker, SessionDep

router = APIRouter(prefix="/kg", tags=["knowledge_graph"])

logger = logging.getLogger(__name__)


def _run_kg_build(author_login: str | None, batch_size: int) -> None:
    """Background task: owns its own session so the HTTP connection is free."""
    with Session(engine) as session:
        graph_service = KnowledgeGraphService()
        builder = KGBuildService(session, graph_service)
        result = builder.build_from_stored_vectors(
            author_login=author_login,
            batch_size=batch_size,
        )
        logger.info("Background KG build complete: %s", result)


@router.post(
    "/graph/build", dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))]
)
async def build_knowledge_graph(
    background_tasks: BackgroundTasks,
    author_login: str | None = None,  # optional: rebuild for one author only
    batch_size: int = 50,
) -> dict[str, str | int]:
    """
    Build the knowledge graph from already-synced PR vectors.
    Run this after /sync/all has completed.
    Can be re-run safely — graph nodes are upserted not duplicated.
    The build runs in the background; this endpoint returns immediately.
    """
    background_tasks.add_task(_run_kg_build, author_login, batch_size)
    logger.info(
        "Queued background KG build author_login=%s batch_size=%d",
        author_login,
        batch_size,
    )
    return {
        "status": "started",
        "message": "KG build running in background. Check server logs for progress.",
        "batch_size": batch_size,
    }


@router.post("/intent/me", response_model=KGLearningIntentResponse)
async def ingest_my_learning_intent(
    session: SessionDep,
    current_user: CurrentUser,
    request: KGLearningIntentRequest,
) -> KGLearningIntentResponse:
    """Ingest current user's learning intent into the knowledge graph."""
    profile = (
        session.query(ResourceProfile)
        .filter(cast(Any, ResourceProfile.user_id == current_user.id))
        .first()
    )

    if not profile or profile.github_id is None:
        raise HTTPException(
            status_code=400,
            detail="Connect your GitHub profile before submitting learning intent.",
        )

    extractor = LLMEntityExtractor()
    entities = extractor.extract(
        files=[],
        commit_messages=[],
        title=request.intent,
        body=request.intent,
        labels=[],
    )

    if entities.is_empty():
        raise HTTPException(
            status_code=422,
            detail="Could not map intent to known domains/skills/tools. Try a more specific description.",
        )

    graph_service = KnowledgeGraphService()
    counts = graph_service.upsert_resource_learning_intent(
        github_id=profile.github_id,
        github_login=profile.github_login,
        entities=entities,
    )

    logger.info(
        "Stored KG intent for user_id=%s github_id=%s domains=%d skills=%d",
        current_user.id,
        profile.github_id,
        counts["wants_to_work_in_domains"],
        counts["wants_to_learn_skills"],
    )

    return KGLearningIntentResponse(
        github_id=profile.github_id,
        github_login=profile.github_login,
        entities=KGLearningIntentEntities(
            languages=entities.languages,
            frameworks=entities.frameworks,
            domains=entities.domains,
            skills=entities.skills,
            tools=entities.tools,
        ),
        wants_to_work_in_domains=counts["wants_to_work_in_domains"],
        wants_to_learn_skills=counts["wants_to_learn_skills"],
        wants_to_learn_languages=counts["wants_to_learn_languages"],
        wants_to_learn_frameworks=counts["wants_to_learn_frameworks"],
        wants_to_learn_tools=counts["wants_to_learn_tools"],
    )
