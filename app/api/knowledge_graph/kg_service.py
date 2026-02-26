import re

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


class KnowledgeGraphService:
    def upsert_pr(self, pr: PullRequestContent, repo_name: str):
        # 1. Upsert PR node (create_or_update returns a list, so we grab the first element)
        pr_node = PR.create_or_update(
            {
                "identifier": pr.id,
                "number": pr.number,
                "title": pr.title,
                "url": str(pr.html_url),
                "author_login": pr.author.login,
                "repo": repo_name,
            }
        )[0]

        # 2. Upsert Author & Connect
        author_node = Resource.create_or_update({"login": pr.author.login})[0]
        pr_node.author.connect(author_node)

        # 3. Upsert Component (repo) & Connect
        component_node = Component.create_or_update({"name": repo_name})[0]
        pr_node.repo_component.connect(component_node)

        # 4. Upsert Files & Connect
        for file_path in pr.changed_files or []:
            file_node = File.create_or_update({"path": file_path})[0]
            pr_node.modified_files.connect(file_node)

        # 5. Upsert Labels & Connect
        labels = pr.labels or self._extract_labels_from_context(pr.context or "")
        for label_name in labels:
            label_node = Label.create_or_update({"name": label_name})[0]
            pr_node.labels.connect(label_node)

    def upsert_jira_issue(self, issue: JiraIssue):
        # 1. Upsert Issue node
        issue_node = JiraIssue.create_or_update(
            {
                "key": issue.key,
                "summary": issue.summary,
                "status": issue.status,
                "epic_key": issue.epic_key or "",
                "url": issue.url,
            }
        )[0]

        # 2. Upsert Epic & Connect (if exists)
        if issue.epic_key:
            epic_node = Epic.create_or_update(
                {"key": issue.epic_key, "summary": issue.epic_summary or ""}
            )[0]
            issue_node.epic.connect(epic_node)

        # 3. Upsert Components & Connect
        for component_name in issue.components or []:
            comp_node = Component.create_or_update({"name": component_name})[0]
            issue_node.components.connect(comp_node)

    def link_pr_to_jira(self, pr_id: int, issue_key: str):
        """Call this when a Jira issue key is detected in a PR branch/title/commits."""
        # nodes.get() fetches the node based on its unique index
        pr_node = PR.nodes.get(identifier=pr_id)
        issue_node = JiraIssue.nodes.get(key=issue_key)

        pr_node.resolves.connect(issue_node)

    def add_similar_pr_edges(self, pairs: list[tuple[int, int, float]]):
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
