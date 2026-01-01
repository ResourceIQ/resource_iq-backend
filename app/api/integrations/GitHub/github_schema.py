from pydantic import BaseModel, Field, HttpUrl
from typing import Optional
from datetime import datetime

class GitHubUser(BaseModel):
    login: str
    id: int
    avatar_url: Optional[HttpUrl] = None
    html_url: Optional[HttpUrl] = None

class PullRequestContent(BaseModel):
    id: int
    number: int
    title: str
    context: Optional[str] = None
    html_url: HttpUrl
    
    # Author information
    author: GitHubUser = Field(..., description="The author of the pull request")

    class Config:
        populate_by_name = True
