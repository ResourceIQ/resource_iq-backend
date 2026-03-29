import logging
from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from app.api.knowledge_graph.kg_build_service import KGBuildService
from app.api.knowledge_graph.kg_extractor import LLMEntityExtractor
from app.api.knowledge_graph.kg_schema import (
    KGExperienceCategory,
    KGExperienceItemAddRequest,
    KGExperienceItemLevelUpdate,
    KGExperienceProfileResponse,
    KGExperienceUpdateRequest,
    KGLearningIntentEntities,
    KGLearningIntentProfileResponse,
    KGLearningIntentRequest,
    KGLearningIntentResponse,
    KGPRInsightsResponse,
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
from app.api.user.user_model import Role, User
from app.db.session import engine
from app.utils.deps import CurrentUser, RoleChecker, SessionDep

router = APIRouter(prefix="/kg", tags=["knowledge_graph"])


# Request/response model for entity extraction
class KGExtractEntitiesRequest(BaseModel):
    title: str
    description: str = ""


class KGExtractEntitiesResponse(BaseModel):
    languages: list[str] = []
    frameworks: list[str] = []
    domains: list[str] = []
    skills: list[str] = []
    tools: list[str] = []


@router.post("/extract-entities", response_model=KGExtractEntitiesResponse)
async def extract_entities(
    request: KGExtractEntitiesRequest = Body(...),
) -> KGExtractEntitiesResponse:
    """
    Extract entities (skills, domains, tools, languages, frameworks) from a task title/description using LLMEntityExtractor.
    """
    extractor = LLMEntityExtractor()
    entities = extractor.extract(
        files=[],
        commit_messages=[],
        title=request.title,
        body=request.description,
        labels=[],
    )
    return KGExtractEntitiesResponse(
        languages=entities.languages,
        frameworks=entities.frameworks,
        domains=entities.domains,
        skills=entities.skills,
        tools=entities.tools,
    )


logger = logging.getLogger(__name__)


def _get_profile_by_current_user(
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
    return profile


def _run_kg_build(author_github_id: int | None, batch_size: int) -> None:
    """Background task: owns its own session so the HTTP connection is free."""
    with Session(engine) as session:
        graph_service = KnowledgeGraphService()
        builder = KGBuildService(session, graph_service)
        result = builder.build_from_stored_vectors(
            author_github_id=author_github_id,
            batch_size=batch_size,
        )
        logger.info("Background KG build complete: %s", result)


def _get_profile_by_github_id(session: SessionDep, github_id: int) -> ResourceProfile:
    profile = cast(
        ResourceProfile | None,
        session.query(ResourceProfile)
        .filter(cast(Any, ResourceProfile.github_id == github_id))
        .first(),
    )
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found for github_id")
    return profile


def _get_profile_by_user_id(session: SessionDep, user_id: UUID) -> ResourceProfile:
    profile = cast(
        ResourceProfile | None,
        session.query(ResourceProfile)
        .filter(cast(Any, ResourceProfile.user_id == user_id))
        .first(),
    )
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found for user_id")
    return profile


def _get_user_by_id(session: SessionDep, user_id: UUID) -> User:
    user = cast(User | None, session.get(User, user_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.post(
    "/graph/build", dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))]
)
async def build_knowledge_graph(
    background_tasks: BackgroundTasks,
    author_github_id: int | None = None,  # optional: rebuild for one author only
    batch_size: int = 50,
) -> dict[str, str | int]:
    """
    Build the knowledge graph from already-synced PR vectors.
    Run this after /sync/all has completed.
    Can be re-run safely — graph nodes are upserted not duplicated.
    The build runs in the background; this endpoint returns immediately.
    """
    background_tasks.add_task(_run_kg_build, author_github_id, batch_size)
    logger.info(
        "Queued background KG build author_github_id=%s batch_size=%d",
        author_github_id,
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
    "/experience/me",
    response_model=KGExperienceProfileResponse,
    dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR, Role.USER]))],
)
async def get_my_resource_experience(
    session: SessionDep,
    current_user: CurrentUser,
) -> KGExperienceProfileResponse:
    """Return has-experience edges for the current user (self-service)."""
    profile = _get_profile_by_current_user(session, current_user)
    graph_service = KnowledgeGraphService()
    return graph_service.get_resource_experience(
        github_id=profile.github_id,
        user_id=str(profile.user_id),
    )


@router.get(
    "/experience/{github_id}",
    response_model=KGExperienceProfileResponse,
    dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR, Role.USER]))],
)
async def get_resource_experience(
    session: SessionDep,
    github_id: int,
) -> KGExperienceProfileResponse:
    """
    Return the experience profile (HAS_EXPERIENCE_WITH edges) for a resource (by GitHub ID).

    Authenticated users (same visibility as resource profiles).

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
    profile = _get_profile_by_github_id(session, github_id)
    graph_service = KnowledgeGraphService()
    return graph_service.get_resource_experience(
        github_id=profile.github_id,
        user_id=str(profile.user_id),
    )


@router.get(
    "/experience/user/{user_id}",
    response_model=KGExperienceProfileResponse,
    dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR, Role.USER]))],
)
async def get_resource_experience_by_user(
    session: SessionDep,
    user_id: UUID,
) -> KGExperienceProfileResponse:
    profile = _get_profile_by_user_id(session, user_id)
    graph_service = KnowledgeGraphService()
    return graph_service.get_resource_experience(
        github_id=profile.github_id,
        user_id=str(profile.user_id),
    )


@router.patch(
    "/experience/{github_id}",
    response_model=KGExperienceProfileResponse,
    dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))],
)
async def update_resource_experience(
    session: SessionDep,
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
    profile = _get_profile_by_github_id(session, github_id)
    user = _get_user_by_id(session, profile.user_id)
    graph_service = KnowledgeGraphService()
    try:
        response = graph_service.upsert_resource_experience(
            user_id=str(profile.user_id),
            profile_id=profile.id,
            github_id=profile.github_id,
            github_login=profile.github_login,
            full_name=user.full_name,
            email=user.email,
            position_name=profile.position.name if profile.position else None,
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


@router.patch(
    "/experience/user/{user_id}",
    response_model=KGExperienceProfileResponse,
    dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))],
)
async def update_resource_experience_by_user(
    session: SessionDep,
    user_id: UUID,
    request: KGExperienceUpdateRequest,
) -> KGExperienceProfileResponse:
    profile = _get_profile_by_user_id(session, user_id)
    user = _get_user_by_id(session, user_id)
    graph_service = KnowledgeGraphService()
    try:
        response = graph_service.upsert_resource_experience(
            user_id=str(profile.user_id),
            profile_id=profile.id,
            github_id=profile.github_id,
            github_login=profile.github_login,
            full_name=user.full_name,
            email=user.email,
            position_name=profile.position.name if profile.position else None,
            domains=request.domains,
            skills=request.skills,
            languages=request.languages,
            frameworks=request.frameworks,
            tools=request.tools,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    logger.info(
        "Updated KG experience for user_id=%s github_id=%s languages=%d frameworks=%d tools=%d",
        profile.user_id,
        profile.github_id,
        len(response.languages),
        len(response.frameworks),
        len(response.tools),
    )

    return response


@router.post(
    "/experience/user/{user_id}/{category}",
    response_model=KGExperienceProfileResponse,
    dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))],
    summary="Add a single experience item",
    description=(
        "Add one language / framework / tool / skill / domain entry to a user's experience profile.\n\n"
        "The `name` must be a valid taxonomy value; use `GET /kg/taxonomy` to discover valid names.\n"
        "If the item already exists, its `experience_level` is updated instead."
    ),
)
async def add_experience_item(
    session: SessionDep,
    user_id: UUID,
    category: KGExperienceCategory,
    request: KGExperienceItemAddRequest,
) -> KGExperienceProfileResponse:
    """**Admin / Moderator only.** Add (or upsert) one experience item."""
    profile = _get_profile_by_user_id(session, user_id)
    user = _get_user_by_id(session, user_id)
    graph_service = KnowledgeGraphService()
    try:
        response = graph_service.add_experience_item(
            user_id=str(profile.user_id),
            profile_id=profile.id,
            github_id=profile.github_id,
            github_login=profile.github_login,
            full_name=user.full_name,
            email=user.email,
            position_name=profile.position.name if profile.position else None,
            category=category.value,
            name=request.name,
            experience_level=request.experience_level,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    logger.info(
        "Added KG experience item user_id=%s category=%s name=%s level=%d",
        user_id,
        category.value,
        request.name,
        request.experience_level,
    )
    return response


@router.patch(
    "/experience/user/{user_id}/{category}/{item_name}",
    response_model=KGExperienceProfileResponse,
    dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))],
    summary="Update experience level of a single item",
    description=(
        "Change the `experience_level` (0–10) of one existing experience item.\n\n"
        "Returns 422 if `item_name` is not a valid taxonomy value or is not yet in the user's profile."
    ),
)
async def update_experience_item_level(
    session: SessionDep,
    user_id: UUID,
    category: KGExperienceCategory,
    item_name: str,
    request: KGExperienceItemLevelUpdate,
) -> KGExperienceProfileResponse:
    """**Admin / Moderator only.** Update the level of one experience item."""
    profile = _get_profile_by_user_id(session, user_id)
    graph_service = KnowledgeGraphService()
    try:
        response = graph_service.update_experience_item_level(
            user_id=str(profile.user_id),
            github_id=profile.github_id,
            category=category.value,
            name=item_name,
            experience_level=request.experience_level,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    logger.info(
        "Updated KG experience level user_id=%s category=%s name=%s level=%d",
        user_id,
        category.value,
        item_name,
        request.experience_level,
    )
    return response


@router.delete(
    "/experience/user/{user_id}/{category}/{item_name}",
    response_model=KGExperienceProfileResponse,
    dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))],
    summary="Delete a single experience item",
    description=(
        "Remove one language / framework / tool / skill / domain from a user's experience profile.\n\n"
        "Returns 422 if `item_name` is unknown or not in the user's profile."
    ),
)
async def delete_experience_item(
    session: SessionDep,
    user_id: UUID,
    category: KGExperienceCategory,
    item_name: str,
) -> KGExperienceProfileResponse:
    """**Admin / Moderator only.** Remove one experience item."""
    profile = _get_profile_by_user_id(session, user_id)
    graph_service = KnowledgeGraphService()
    try:
        response = graph_service.delete_experience_item(
            user_id=str(profile.user_id),
            github_id=profile.github_id,
            category=category.value,
            name=item_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    logger.info(
        "Deleted KG experience item user_id=%s category=%s name=%s",
        user_id,
        category.value,
        item_name,
    )
    return response


@router.get(
    "/learning-intent/me",
    response_model=KGLearningIntentProfileResponse,
    dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR, Role.USER]))],
)
async def get_my_resource_learning_intent(
    session: SessionDep,
    current_user: CurrentUser,
) -> KGLearningIntentProfileResponse:
    """Return wants-to-learn / learning-intent edges for the current user (self-service)."""
    profile = _get_profile_by_current_user(session, current_user)
    graph_service = KnowledgeGraphService()
    return graph_service.get_resource_learning_intent(
        github_id=profile.github_id,
        user_id=str(profile.user_id),
    )


@router.get(
    "/learning-intent/{github_id}",
    response_model=KGLearningIntentProfileResponse,
    dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR, Role.USER]))],
)
async def get_resource_learning_intent(
    session: SessionDep,
    github_id: int,
) -> KGLearningIntentProfileResponse:
    """
    Return the learning intent (WANTS_TO_LEARN / WANTS_TO_WORK_IN) edges for a resource (by GitHub ID).

    Authenticated users (same visibility as resource profiles).
    """
    profile = _get_profile_by_github_id(session, github_id)
    graph_service = KnowledgeGraphService()
    return graph_service.get_resource_learning_intent(
        github_id=profile.github_id,
        user_id=str(profile.user_id),
    )


@router.get(
    "/learning-intent/user/{user_id}",
    response_model=KGLearningIntentProfileResponse,
    dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR, Role.USER]))],
)
async def get_resource_learning_intent_by_user(
    session: SessionDep,
    user_id: UUID,
) -> KGLearningIntentProfileResponse:
    """Return the learning intent edges for a resource by user ID."""
    profile = _get_profile_by_user_id(session, user_id)
    graph_service = KnowledgeGraphService()
    return graph_service.get_resource_learning_intent(
        github_id=profile.github_id,
        user_id=str(profile.user_id),
    )


@router.get(
    "/prs/me",
    response_model=KGPRInsightsResponse,
    dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR, Role.USER]))],
)
async def get_my_resource_pr_insights(
    session: SessionDep,
    current_user: CurrentUser,
) -> KGPRInsightsResponse:
    """Return PR ingestion insights for the current user (self-service)."""
    profile = _get_profile_by_current_user(session, current_user)
    graph_service = KnowledgeGraphService()
    return graph_service.get_resource_prs(
        github_id=profile.github_id,
        user_id=str(profile.user_id),
    )


@router.get(
    "/prs/{github_id}",
    response_model=KGPRInsightsResponse,
    dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR, Role.USER]))],
)
async def get_resource_pr_insights(
    session: SessionDep,
    github_id: int,
) -> KGPRInsightsResponse:
    """
    Return PR ingestion data from the knowledge graph for a resource (by GitHub ID).
    Includes per-PR extracted entities and aggregated counts.

    Authenticated users (same visibility as resource profiles).
    """
    profile = _get_profile_by_github_id(session, github_id)
    graph_service = KnowledgeGraphService()
    return graph_service.get_resource_prs(
        github_id=profile.github_id,
        user_id=str(profile.user_id),
    )


@router.get(
    "/prs/user/{user_id}",
    response_model=KGPRInsightsResponse,
    dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR, Role.USER]))],
)
async def get_resource_pr_insights_by_user(
    session: SessionDep,
    user_id: UUID,
) -> KGPRInsightsResponse:
    """Return PR ingestion data from the knowledge graph by user ID."""
    profile = _get_profile_by_user_id(session, user_id)
    graph_service = KnowledgeGraphService()
    return graph_service.get_resource_prs(
        github_id=profile.github_id,
        user_id=str(profile.user_id),
    )


@router.post("/intent/me", response_model=KGLearningIntentResponse)
async def ingest_my_learning_intent(
    session: SessionDep,
    current_user: CurrentUser,
    request: KGLearningIntentRequest,
) -> KGLearningIntentResponse:
    """Ingest current user's learning intent into the knowledge graph."""
    profile = _get_profile_by_current_user(session, current_user)

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
        user_id=str(current_user.id),
        profile_id=profile.id,
        github_id=profile.github_id,
        github_login=profile.github_login,
        full_name=current_user.full_name,
        email=current_user.email,
        position_name=profile.position.name if profile.position else None,
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
        user_id=str(current_user.id),
        profile_id=profile.id,
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


@router.post(
    "/intent/user/{user_id}",
    response_model=KGLearningIntentResponse,
    dependencies=[Depends(RoleChecker([Role.ADMIN, Role.MODERATOR]))],
)
async def ingest_learning_intent_by_user(
    session: SessionDep,
    user_id: UUID,
    request: KGLearningIntentRequest,
) -> KGLearningIntentResponse:
    profile = _get_profile_by_user_id(session, user_id)
    user = _get_user_by_id(session, user_id)

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
        user_id=str(user.id),
        profile_id=profile.id,
        github_id=profile.github_id,
        github_login=profile.github_login,
        full_name=user.full_name,
        email=user.email,
        position_name=profile.position.name if profile.position else None,
        entities=entities,
    )

    logger.info(
        "Stored KG intent for target_user_id=%s github_id=%s domains=%d skills=%d",
        user.id,
        profile.github_id,
        counts["wants_to_work_in_domains"],
        counts["wants_to_learn_skills"],
    )

    return KGLearningIntentResponse(
        user_id=str(user.id),
        profile_id=profile.id,
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
