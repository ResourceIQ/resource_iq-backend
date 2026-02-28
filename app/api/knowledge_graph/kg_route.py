from fastapi import APIRouter

from app.api.knowledge_graph.kg_build_service import KGBuildService
from app.api.knowledge_graph.kg_schema import KGBuildResult
from app.api.knowledge_graph.kg_service import KnowledgeGraphService
from app.utils.deps import SessionDep

router = APIRouter(prefix="/kg", tags=["knowledge_graph"])


@router.post("/graph/build")
async def build_knowledge_graph(
    session: SessionDep,
    author_login: str | None = None,  # optional: rebuild for one author only
) -> KGBuildResult:
    """
    Build the knowledge graph from already-synced PR vectors.
    Run this after /sync/all has completed.
    Can be re-run safely — graph nodes are upserted not duplicated.
    """
    graph_service = KnowledgeGraphService()
    builder = KGBuildService(session, graph_service)
    result = builder.build_from_stored_vectors(author_login=author_login)
    return result
