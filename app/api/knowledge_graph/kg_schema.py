from dataclasses import dataclass, field
from enum import Enum
from typing import TypedDict

from pydantic import BaseModel, Field, field_validator
from sqlmodel import SQLModel


class KGBuildResult(TypedDict):
    prs_processed: int
    profiles_updated: int
    errors: list[str]


@dataclass(frozen=True)
class KGResourceSnapshot:
    user_id: str
    id: int | None
    profile_id: int | None
    full_name: str | None
    email: str | None
    position_name: str | None
    github_id: int | None
    github_login: str | None


@dataclass(frozen=True)
class KGPRSnapshot:
    pr_id: int | str | None
    id: int | None
    pr_number: int
    pr_title: str
    pr_description: str | None
    pr_url: str
    repo_id: int
    repo_name: str
    metadata_json: dict[str, object] | None
    author_login: str
    author_id: int
    context: str | None


@dataclass
class KGExpertiseSummary:
    pr_count: int = 0
    languages: dict[str, int] = field(default_factory=dict)
    frameworks: dict[str, int] = field(default_factory=dict)
    domains: dict[str, int] = field(default_factory=dict)
    skills: dict[str, int] = field(default_factory=dict)
    tools: dict[str, int] = field(default_factory=dict)


class JiraIssueContent(TypedDict):
    key: str
    summary: str
    status: str
    epic_key: str | None
    epic_summary: str | None
    url: str
    components: list[str] | None


class KGLearningIntentRequest(SQLModel):
    intent: str = Field(min_length=10, max_length=5000)


class KGLearningIntentEntities(SQLModel):
    languages: list[str] = Field(default_factory=list)
    frameworks: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)


class KGLearningIntentResponse(SQLModel):
    user_id: str
    profile_id: int | None = None
    github_id: int | None
    github_login: str | None = None
    entities: KGLearningIntentEntities
    wants_to_work_in_domains: int = 0
    wants_to_learn_skills: int = 0
    wants_to_learn_languages: int = 0
    wants_to_learn_frameworks: int = 0
    wants_to_learn_tools: int = 0


class KGExperienceItem(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    experience_level: int = Field(ge=0, le=10)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Name must not be blank")
        return normalized


class KGExperienceCategory(str, Enum):
    """Valid categories for experience items."""

    languages = "languages"
    frameworks = "frameworks"
    tools = "tools"
    skills = "skills"
    domains = "domains"


class KGExperienceUpdateRequest(BaseModel):
    domains: list[KGExperienceItem] | None = None
    skills: list[KGExperienceItem] | None = None
    languages: list[KGExperienceItem] | None = None
    frameworks: list[KGExperienceItem] | None = None
    tools: list[KGExperienceItem] | None = None


class KGExperienceItemAddRequest(BaseModel):
    """Request to add a single item to an experience category."""

    name: str = Field(
        min_length=1, max_length=255, description="Taxonomy name of the item"
    )
    experience_level: int = Field(
        ge=0, le=10, description="Experience level 0-10", default=5
    )


class KGExperienceItemLevelUpdate(BaseModel):
    """Request to update the level of a single existing experience item."""

    experience_level: int = Field(ge=0, le=10, description="New experience level 0-10")


class KGExperienceProfileResponse(BaseModel):
    user_id: str | None = None
    profile_id: int | None = None
    github_id: int | None = None
    github_login: str | None = None
    domains: list[KGExperienceItem] = Field(default_factory=list)
    skills: list[KGExperienceItem] = Field(default_factory=list)
    languages: list[KGExperienceItem] = Field(default_factory=list)
    frameworks: list[KGExperienceItem] = Field(default_factory=list)
    tools: list[KGExperienceItem] = Field(default_factory=list)


class KGLearningIntentProfileResponse(BaseModel):
    user_id: str | None = None
    profile_id: int | None = None
    github_id: int | None = None
    github_login: str | None = None
    wants_to_work_in_domains: list[str] = Field(default_factory=list)
    wants_to_learn_skills: list[str] = Field(default_factory=list)
    wants_to_learn_languages: list[str] = Field(default_factory=list)
    wants_to_learn_frameworks: list[str] = Field(default_factory=list)
    wants_to_learn_tools: list[str] = Field(default_factory=list)


class KGPRItem(BaseModel):
    identifier: int
    number: int | None = None
    title: str | None = None
    url: str | None = None
    repo: str | None = None
    languages: list[str] = Field(default_factory=list)
    frameworks: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)


class KGPRInsightsResponse(BaseModel):
    user_id: str | None = None
    profile_id: int | None = None
    github_id: int | None = None
    github_login: str | None = None
    total_prs: int = 0
    prs: list[KGPRItem] = Field(default_factory=list)
    aggregated_languages: dict[str, int] = Field(default_factory=dict)
    aggregated_frameworks: dict[str, int] = Field(default_factory=dict)
    aggregated_domains: dict[str, int] = Field(default_factory=dict)
    aggregated_skills: dict[str, int] = Field(default_factory=dict)
    aggregated_tools: dict[str, int] = Field(default_factory=dict)


class KGTaxonomyResponse(BaseModel):
    domains: dict[str, list[str]]
    skills: dict[str, list[str]]
    languages: dict[str, list[str]]
    frameworks: dict[str, dict[str, list[str]]]
    tools: dict[str, list[str]]
