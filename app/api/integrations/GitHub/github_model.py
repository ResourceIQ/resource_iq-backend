from sqlmodel import Field, SQLModel


class GithubOrgIntBaseModel(SQLModel, table=True):
    """Base model for GitHub Organization Integration"""

    __tablename__ = "org_integrations_github"
    id: int | None = Field(default=None, primary_key=True)
    github_install_id: str = Field(..., description="GitHub Installation ID")
    org_name: str = Field(..., description="GitHub Organization Name")
