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


class ScoreProfile(SQLModel):
    user_id: UUID
    user_name: str = ""
    github_pr_score: float = 0.0
    jira_issue_score: float = 0.0
    pr_info: list[PrScoreInfo] = []
    issue_links: list[str] = []

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_score(self) -> float:
        return self.github_pr_score + self.jira_issue_score
