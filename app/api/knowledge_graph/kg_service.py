import re
from typing import Any, TypedDict

from app.api.integrations.GitHub.github_schema import PullRequestContent
from app.api.knowledge_graph.kg_model import (
    PR,
    Component,
    Epic,
    File,
    JiraIssue,
    Label,
    Resource,
)


class JiraIssueContent(TypedDict):
    key: str
    summary: str
    status: str
    epic_key: str | None
    epic_summary: str | None
    url: str
    components: list[str] | None


class KnowledgeGraphService:
    @staticmethod
    def _create_or_update_node(model: Any, properties: dict[str, Any]) -> Any:
        return model.create_or_update(properties)[0]

    def upsert_pr(self, pr: PullRequestContent, repo_name: str) -> None:
        # 1. Upsert PR node (create_or_update returns a list, so we grab the first element)
        pr_node = self._create_or_update_node(
            PR,
            {
                "identifier": pr.id,
                "number": pr.number,
                "title": pr.title,
                "url": str(pr.html_url),
                "author_login": pr.author.login,
                "repo": repo_name,
            },
        )

        # 2. Upsert Author & Connect
        author_node = self._create_or_update_node(Resource, {"login": pr.author.login})
        pr_node.author.connect(author_node)

        # 3. Upsert Component (repo) & Connect
        component_node = self._create_or_update_node(Component, {"name": repo_name})
        pr_node.repo_component.connect(component_node)

        # 4. Upsert Files & Connect
        for file_path in pr.changed_files or []:
            file_node = self._create_or_update_node(File, {"path": file_path})
            pr_node.modified_files.connect(file_node)

        # 5. Upsert Labels & Connect
        labels = pr.labels or self._extract_labels_from_context(pr.context or "")
        for label_name in labels:
            label_node = self._create_or_update_node(Label, {"name": label_name})
            pr_node.pr_labels.connect(label_node)

    def upsert_jira_issue(self, issue: JiraIssueContent) -> None:
        # 1. Upsert Issue node
        issue_node = self._create_or_update_node(
            JiraIssue,
            {
                "key": issue["key"],
                "summary": issue["summary"],
                "status": issue["status"],
                "epic_key": issue["epic_key"] or "",
                "url": issue["url"],
            },
        )

        # 2. Upsert Epic & Connect (if exists)
        if issue["epic_key"]:
            epic_node = self._create_or_update_node(
                Epic,
                {"key": issue["epic_key"], "summary": issue["epic_summary"] or ""},
            )
            issue_node.epic.connect(epic_node)

        # 3. Upsert Components & Connect
        for component_name in issue["components"] or []:
            comp_node = self._create_or_update_node(Component, {"name": component_name})
            issue_node.components.connect(comp_node)

    def link_pr_to_jira(self, pr_id: int, issue_key: str) -> None:
        """Call this when a Jira issue key is detected in a PR branch/title/commits."""
        # nodes.get() fetches the node based on its unique index
        pr_node = PR.nodes.get(identifier=pr_id)
        issue_node = JiraIssue.nodes.get(key=issue_key)

        pr_node.resolves.connect(issue_node)

    def add_similar_pr_edges(self, pairs: list[tuple[int, int, float]]) -> None:
        """Add SIMILAR_TO edges from embedding clustering."""
        for pr_id_a, pr_id_b, score in pairs:
            pr_a = PR.nodes.get(identifier=pr_id_a)
            pr_b = PR.nodes.get(identifier=pr_id_b)

            # Connect and pass the relationship property
            pr_a.similar_to.connect(pr_b, {"score": score})

    def _extract_labels_from_context(self, context: str) -> list[str]:
        match = re.search(r"LABELS: (.+)", context)
        if match:
            return [l.strip() for l in match.group(1).split(",") if l.strip()]  # noqa: E741
        return []
