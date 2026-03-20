import logging
from typing import Any, cast

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlmodel import Session

from app.api.knowledge_graph.kg_build_service import KGBuildService
from app.api.knowledge_graph.kg_extractor import LLMEntityExtractor
from app.api.knowledge_graph.kg_schema import (
    KGExperienceProfileResponse,
    KGExperienceUpdateRequest,
    KGLearningIntentEntities,
    KGLearningIntentRequest,
    KGLearningIntentResponse,
    KGTaxonomyResponse,
)
from app.api.knowledge_graph.kg_service import KnowledgeGraphService
from app.api.knowledge_graph.kg_taxonomy import (
    DOMAIN_TAXONOMY,
    FRAMEWORK_TAXONOMY,
    LANGUAGE_TAXONOMY,
    SKILL_TAXONOMY,
    TOOL_TAXONOMY,
)
from app.api.profiles.profile_model import ResourceProfile
from app.api.user.user_model import Role
from app.db.session import engine
from app.utils.deps import CurrentUser, RoleChecker, SessionDep

router = APIRouter(prefix="/kg", tags=["knowledge_graph"])

logger = logging.getLogger(__name__)


def _get_connected_github_profile(
    session: SessionDep,
    current_user: CurrentUser,
) -> ResourceProfile:
    profile = cast(
        ResourceProfile | None,
        session.query(ResourceProfile)
        .filter(cast(Any, ResourceProfile.user_id == current_user.id))
        .first(),
    )
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    if profile.github_id is None or not profile.github_login:
        raise HTTPException(
            status_code=400,
            detail="Connect your GitHub profile before ingesting learning intent",
        )
    return profile


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


@router.get("/taxonomy", response_model=KGTaxonomyResponse)
async def get_taxonomy() -> KGTaxonomyResponse:
    """
    Return the full KG taxonomy for frontend selectors.

    **Response Example:**
    ```json
    {
      "domains": {
        "security-and-identity": ["authentication", "authorisation", "oauth-oidc", "mfa"],
        "api-and-integrations": ["api-design", "graphql", "grpc"],
        "infrastructure-and-devops": ["cloud-infrastructure", "containerisation", "ci-cd"]
      },
      "skills": {
        "engineering-practices": ["tdd", "bdd", "pair-programming", "code-review"],
        "api-and-integration": ["rest-api-design", "graphql-schema-design", "oauth-implementation"]
      },
      "languages": {
        "backend-general": ["Python", "Java", "Kotlin", "Ruby"],
        "frontend": ["JavaScript", "TypeScript"]
      },
      "frameworks": {
        "Python": {"backend": ["FastAPI", "Django", "Flask"]},
        "JavaScript": {"frontend": ["React", "Vue", "Angular"]}
      },
      "tools": {
        "infra-tools": ["Docker", "Kubernetes", "Terraform"],
        "testing-tools": ["Jest", "Pytest", "JUnit"]
      }
    }
    ```
    """
    return KGTaxonomyResponse(
        domains=DOMAIN_TAXONOMY,
        skills=SKILL_TAXONOMY,
        languages=LANGUAGE_TAXONOMY,
        frameworks=FRAMEWORK_TAXONOMY,
        tools=TOOL_TAXONOMY,
    )


@router.get(
    "/experience/{github_id}",
    response_model=KGExperienceProfileResponse,
    dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))],
)
async def get_resource_experience(
    github_id: int,
) -> KGExperienceProfileResponse:
    """
    Return the experience profile for a resource (by GitHub ID). Admin/Moderator only.

    **Response Example:**
    ```json
    {
      "github_id": 12345,
      "github_login": "alice",
      "domains": [
        {"name": "api-design", "experience_level": 8},
        {"name": "microservices", "experience_level": 7}
      ],
      "skills": [
        {"name": "rest-api-design", "experience_level": 9},
        {"name": "database-migrations", "experience_level": 6}
      ],
      "languages": [
        {"name": "Python", "experience_level": 10},
        {"name": "JavaScript", "experience_level": 7}
      ],
      "frameworks": [
        {"name": "FastAPI", "experience_level": 9},
        {"name": "React", "experience_level": 8}
      ],
      "tools": [
        {"name": "Docker", "experience_level": 8},
        {"name": "Kubernetes", "experience_level": 6}
      ]
    }
    ```
    """
    graph_service = KnowledgeGraphService()
    return graph_service.get_resource_experience(github_id)


@router.patch(
    "/experience/{github_id}",
    response_model=KGExperienceProfileResponse,
    dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))],
)
async def update_resource_experience(
    github_id: int,
    request: KGExperienceUpdateRequest,
) -> KGExperienceProfileResponse:
    """
    Create or replace selected experience edges for a resource (by GitHub ID). Admin/Moderator only.

    Uses a partial update model: only categories specified in the request are modified;
    omitted categories remain unchanged. Experience levels must be 0-10 (inclusive).

    **Request Example:**
    ```json
    {
      "languages": [
        {"name": "Python", "experience_level": 10},
        {"name": "TypeScript", "experience_level": 8}
      ],
      "frameworks": [
        {"name": "FastAPI", "experience_level": 9}
      ],
      "tools": [
        {"name": "Docker", "experience_level": 8}
      ]
    }
    ```

    **Response Example:**
    ```json
    {
      "github_id": 12345,
      "github_login": "alice",
      "domains": [],
      "skills": [],
      "languages": [
        {"name": "Python", "experience_level": 10},
        {"name": "TypeScript", "experience_level": 8}
      ],
      "frameworks": [
        {"name": "FastAPI", "experience_level": 9}
      ],
      "tools": [
        {"name": "Docker", "experience_level": 8}
      ]
    }
    ```

    **Error Response (422 Unprocessable Entity):**
    ```json
    {"detail": "Unknown taxonomy value: made-up-language"}
    ```
    """
    graph_service = KnowledgeGraphService()
    try:
        response = graph_service.upsert_resource_experience(
            github_id=github_id,
            github_login=None,
            domains=request.domains,
            skills=request.skills,
            languages=request.languages,
            frameworks=request.frameworks,
            tools=request.tools,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    logger.info(
        "Updated KG experience for github_id=%s languages=%d frameworks=%d tools=%d",
        github_id,
        len(response.languages),
        len(response.frameworks),
        len(response.tools),
    )

    return response


@router.post("/intent/me", response_model=KGLearningIntentResponse)
async def ingest_my_learning_intent(
    session: SessionDep,
    current_user: CurrentUser,
    request: KGLearningIntentRequest,
) -> KGLearningIntentResponse:
    """Ingest current user's learning intent into the knowledge graph."""
    profile = _get_connected_github_profile(session, current_user)
    github_id = cast(int, profile.github_id)
    github_login = cast(str, profile.github_login)

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
        github_id=github_id,
        github_login=github_login,
        entities=entities,
    )

    logger.info(
        "Stored KG intent for user_id=%s github_id=%s domains=%d skills=%d",
        current_user.id,
        github_id,
        counts["wants_to_work_in_domains"],
        counts["wants_to_learn_skills"],
    )

    return KGLearningIntentResponse(
        github_id=github_id,
        github_login=github_login,
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
