from typing import TypedDict


class KGBuildResult(TypedDict):
    prs_processed: int
    profiles_updated: int
    errors: list[str]


class JiraIssueContent(TypedDict):
    key: str
    summary: str
    status: str
    epic_key: str | None
    epic_summary: str | None
    url: str
    components: list[str] | None
