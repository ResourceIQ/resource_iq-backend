from dataclasses import dataclass, field
from typing import TypedDict

from pydantic import Field
from sqlmodel import SQLModel


class KGBuildResult(TypedDict):
    prs_processed: int
    profiles_updated: int
    errors: list[str]


@dataclass(frozen=True)
class KGResourceSnapshot:
    id: int | None
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
    github_id: int
    github_login: str | None = None
    entities: KGLearningIntentEntities
    wants_to_work_in_domains: int = 0
    wants_to_learn_skills: int = 0
    wants_to_learn_languages: int = 0
    wants_to_learn_frameworks: int = 0
    wants_to_learn_tools: int = 0
