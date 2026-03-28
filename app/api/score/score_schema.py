from uuid import UUID

from pydantic import computed_field
from sqlmodel import Field, SQLModel

from app.api.knowledge_graph.kg_taxonomy import (
    DOMAIN_SLUGS,
    FRAMEWORK_SLUGS,
    LANGUAGE_SLUGS,
    SKILL_SLUGS,
    TOOL_SLUGS,
)


class BestFitInput(SQLModel):
    task_title: str
    task_description: str = ""
    max_results: int = Field(default=5, gt=0, le=100)

    skills: list[str] = Field(default_factory=list, nullable=True)
    domains: list[str] = Field(default_factory=list, nullable=True)
    tools: list[str] = Field(default_factory=list, nullable=True)
    languages: list[str] = Field(default_factory=list, nullable=True)
    frameworks: list[str] = Field(default_factory=list, nullable=True)

    @staticmethod
    def _validate_taxonomy(
        values: list[str], allowed: set[str], field: str
    ) -> list[str]:
        invalid = [v for v in values if v not in allowed]
        if invalid:
            raise ValueError(f"Invalid {field}: {invalid}. Allowed: {sorted(allowed)}")
        return values

    def __init__(self, **data):
        super().__init__(**data)
        # Validate all taxonomy fields
        allowed_skills = set(SKILL_SLUGS)
        allowed_domains = set(DOMAIN_SLUGS)
        allowed_tools = set(TOOL_SLUGS)
        allowed_languages = set(LANGUAGE_SLUGS)
        allowed_frameworks = set(
            FRAMEWORK_SLUGS
        )  # Assuming you have a FRAMEWORK_SLUGS list
        if self.skills:
            self._validate_taxonomy(self.skills, allowed_skills, "skills")
        if self.domains:
            self._validate_taxonomy(self.domains, allowed_domains, "domains")
        if self.tools:
            self._validate_taxonomy(self.tools, allowed_tools, "tools")
        if self.languages:
            self._validate_taxonomy(self.languages, allowed_languages, "languages")
        if self.frameworks:
            self._validate_taxonomy(self.frameworks, allowed_frameworks, "frameworks")


class PrScoreInfo(SQLModel):
    pr_id: int
    pr_title: str = ""
    pr_description: str = ""
    pr_url: str = ""
    match_percentage: float = 0.0


class IssueScoreInfo(SQLModel):
    issue_key: str
    issue_summary: str = ""
    issue_url: str = ""
    match_percentage: float = 0.0


class KGMatchInfo(SQLModel):
    category: str
    value: str
    evidence_count: int = 0
    match_strength: float = 0.0


class ScoreProfile(SQLModel):
    user_id: UUID
    user_name: str | None = None
    position: str | None = None
    github_pr_score: float = 0.0
    knowledge_graph_score: float = 0.0
    jira_issue_score: float = 0.0
    availability_score: float = 0.0
    live_jira_workload: int = 0
    pr_info: list[PrScoreInfo] = Field(default_factory=list)
    kg_matches: list[KGMatchInfo] = Field(default_factory=list)
    issue_info: list[IssueScoreInfo] = Field(default_factory=list)
    issue_links: list[str] = Field(default_factory=list)
    kg_match_details: dict[str, object] = Field(
        default_factory=dict
    )  # New: frontend-friendly match details

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_score(self) -> float:
        return (
            self.github_pr_score
            + self.knowledge_graph_score
            + self.jira_issue_score
            + self.availability_score
        )
