from uuid import UUID

from pydantic import computed_field
from sqlmodel import Field, SQLModel


class BestFitInput(SQLModel):
    task_title: str
    task_description: str = ""
    max_results: int = Field(default=5, gt=0, le=100)


class PrScoreInfo(SQLModel):
    pr_id: int
    pr_title: str = ""
    pr_description: str = ""
    pr_url: str = ""
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
    issue_links: list[str] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_score(self) -> float:
        return (
            self.github_pr_score
            + self.knowledge_graph_score
            + self.jira_issue_score
            + self.availability_score
        )
