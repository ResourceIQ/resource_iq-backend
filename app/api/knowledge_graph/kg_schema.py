from dataclasses import dataclass, field
from typing import TypedDict


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
