from pydantic import BaseModel, Field, HttpUrl


class GitHubUser(BaseModel):
    login: str
    id: int
    email: str | None = None
    name: str | None = None
    avatar_url: HttpUrl | None = None
    html_url: HttpUrl | None = None


class PullRequestContent(BaseModel):
    id: int
    number: int
    title: str
    body: str | None = None
    context: str | None = None
    repo_id: int
    repo_name: str | None = None
    labels: list[str] = []
    changed_files: list[str] = Field(default_factory=list, description="List of changed file paths", nullable=True)
    html_url: HttpUrl

    # Author information
    author: GitHubUser = Field(..., description="The author of the pull request")

    class Config:
        populate_by_name = True
