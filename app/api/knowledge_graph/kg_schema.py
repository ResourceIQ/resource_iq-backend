from dataclasses import dataclass, field
from typing import TypedDict


class KGBuildResult(TypedDict):
    prs_processed: int
    profiles_updated: int
    errors: list[str]


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
