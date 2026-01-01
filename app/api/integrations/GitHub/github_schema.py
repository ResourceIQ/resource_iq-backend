from pydantic import BaseModel, Field, HttpUrl


class GitHubUser(BaseModel):
    login: str
    id: int
    avatar_url: HttpUrl | None = None
    html_url: HttpUrl | None = None


class PullRequestContent(BaseModel):
    id: int
    number: int
    title: str
    context: str | None = None
    html_url: HttpUrl

    # Author information
    author: GitHubUser = Field(..., description="The author of the pull request")

    class Config:
        populate_by_name = True
