
import logging

from fastapi import APIRouter, BackgroundTasks,Depends
from sqlmodel import Session

from app.api.knowledge_graph.kg_build_service import KGBuildService
from app.api.knowledge_graph.kg_service import KnowledgeGraphService
from app.utils.deps import SessionDep,RoleChecker
from app.api.user.user_model import Role
from app.db.session import engine

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


@router.post("/graph/build",dependencies=[Depends(RoleChecker([Role.ADMIN,Role.MODERATOR]))])
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
