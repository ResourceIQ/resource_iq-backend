import re
from collections import Counter
from typing import Any, cast

from neomodel import db  # type: ignore[attr-defined]

from app.api.integrations.GitHub.github_schema import PullRequestContent
from app.api.knowledge_graph.kg_extractor import ExtractedEntities
from app.api.knowledge_graph.kg_model import (
    PR,
    Component,
    Domain,
    Epic,
    File,
    Framework,
    JiraIssue,
    Label,
    Language,
    Resource,
    Skill,
    Tool,
)
from app.api.knowledge_graph.kg_schema import JiraIssueContent, KGExpertiseSummary


class KnowledgeGraphService:
    @staticmethod
    def _count_entity_values(values: list[Any]) -> dict[str, int]:
        counts: Counter[str] = Counter()
        for value in values:
            if not isinstance(value, str):
                continue
            normalized = value.strip().lower()
            if not normalized:
                continue
            counts[normalized] += 1
        return dict(counts)

    @staticmethod
    def _create_or_update_node(model: Any, properties: dict[str, Any]) -> Any:
        return model.create_or_update(properties)[0]

    @staticmethod
    def _connect_if_missing(
        relationship_manager: Any,
        target_node: Any,
        properties: dict[str, Any] | None = None,
    ) -> None:
        """Create relationship only if it does not already exist."""
        if relationship_manager.is_connected(target_node):
            return
        if properties:
            relationship_manager.connect(target_node, properties)
            return
        relationship_manager.connect(target_node)

    def pr_exists(self, pr_id: int) -> bool:
        try:
            PR.nodes.get(identifier=pr_id)
            return True
        except PR.DoesNotExist:
            return False

    def pr_has_entity_links(self, pr_id: int) -> bool:
        """True when PR already has any extracted entity relationship."""
        pr_node = PR.nodes.get(identifier=pr_id)
        return any(
            [
                bool(pr_node.uses_language.all()),
                bool(pr_node.uses_framework.all()),
                bool(pr_node.touches_domain.all()),
                bool(pr_node.demonstrates_skill.all()),
                bool(pr_node.uses_tool.all()),
            ]
        )

    def pr_has_context(self, pr_id: int) -> bool:
        pr_node = PR.nodes.get(identifier=pr_id)
        return bool((pr_node.context or "").strip())

    def get_resource_expertise_summary(self, github_id: int) -> KGExpertiseSummary:
        rows, _ = db.cypher_query(
            """
            MATCH (r:Resource {github_id: $github_id})
            CALL {
                WITH r
                OPTIONAL MATCH (r)<-[:AUTHORED_BY]-(pr:PR)
                RETURN count(DISTINCT pr) AS pr_count
            }
            CALL {
                WITH r
                OPTIONAL MATCH (r)<-[:AUTHORED_BY]-(pr:PR)-[:USES_LANGUAGE]->(node:Language)
                WITH [value IN collect(node.name) WHERE value IS NOT NULL] AS values
                RETURN values AS languages
            }
            CALL {
                WITH r
                OPTIONAL MATCH (r)<-[:AUTHORED_BY]-(pr:PR)-[:USES_FRAMEWORK]->(node:Framework)
                WITH [value IN collect(node.name) WHERE value IS NOT NULL] AS values
                RETURN values AS frameworks
            }
            CALL {
                WITH r
                OPTIONAL MATCH (r)<-[:AUTHORED_BY]-(pr:PR)-[:TOUCHES_DOMAIN]->(node:Domain)
                WITH [value IN collect(node.slug) WHERE value IS NOT NULL] AS values
                RETURN values AS domains
            }
            CALL {
                WITH r
                OPTIONAL MATCH (r)<-[:AUTHORED_BY]-(pr:PR)-[:DEMONSTRATES_SKILL]->(node:Skill)
                WITH [value IN collect(node.slug) WHERE value IS NOT NULL] AS values
                RETURN values AS skills
            }
            CALL {
                WITH r
                OPTIONAL MATCH (r)<-[:AUTHORED_BY]-(pr:PR)-[:USES_TOOL]->(node:Tool)
                WITH [value IN collect(node.name) WHERE value IS NOT NULL] AS values
                RETURN values AS tools
            }
            RETURN pr_count, languages, frameworks, domains, skills, tools
            """,
            {"github_id": github_id},
        )

        if not rows:
            return KGExpertiseSummary()

        row = cast(list[Any], rows[0])
        return KGExpertiseSummary(
            pr_count=int(row[0] or 0),
            languages=self._count_entity_values(cast(list[Any], row[1] or [])),
            frameworks=self._count_entity_values(cast(list[Any], row[2] or [])),
            domains=self._count_entity_values(cast(list[Any], row[3] or [])),
            skills=self._count_entity_values(cast(list[Any], row[4] or [])),
            tools=self._count_entity_values(cast(list[Any], row[5] or [])),
        )

    def upsert_pr(self, pr: PullRequestContent, repo_name: str) -> None:
        # 1. Upsert PR node (create_or_update returns a list, so we grab the first element)
        pr_node = self._create_or_update_node(
            PR,
            {
                "identifier": pr.id,
                "number": pr.number,
                "title": pr.title,
                "context": pr.context or "",
                "url": str(pr.html_url),
                "author_login": pr.author.login,
                "repo": repo_name,
            },
        )

        # 2. Upsert Author & Connect (keyed on GitHub ID)
        author_node = self._create_or_update_node(
            Resource, {"github_id": pr.author.id, "login": pr.author.login}
        )
        self._connect_if_missing(pr_node.author, author_node)

        # 3. Upsert Component (repo) & Connect
        component_node = self._create_or_update_node(Component, {"name": repo_name})
        self._connect_if_missing(pr_node.repo_component, component_node)

        # 4. Upsert Files & Connect
        for file_path in pr.changed_files or []:
            file_node = self._create_or_update_node(File, {"path": file_path})
            self._connect_if_missing(pr_node.modified_files, file_node)

        # 5. Upsert Labels & Connect
        labels = pr.labels or self._extract_labels_from_context(pr.context or "")
        for label_name in labels:
            label_node = self._create_or_update_node(Label, {"name": label_name})
            self._connect_if_missing(pr_node.pr_labels, label_node)

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
            self._connect_if_missing(issue_node.epic, epic_node)

        # 3. Upsert Components & Connect
        for component_name in issue["components"] or []:
            comp_node = self._create_or_update_node(Component, {"name": component_name})
            self._connect_if_missing(issue_node.components, comp_node)

    def link_pr_to_jira(self, pr_id: int, issue_key: str) -> None:
        """Call this when a Jira issue key is detected in a PR branch/title/commits."""
        # nodes.get() fetches the node based on its unique index
        pr_node = PR.nodes.get(identifier=pr_id)
        issue_node = JiraIssue.nodes.get(key=issue_key)

        self._connect_if_missing(pr_node.resolves, issue_node)

    def add_similar_pr_edges(self, pairs: list[tuple[int, int, float]]) -> None:
        """Add SIMILAR_TO edges from embedding clustering."""
        for pr_id_a, pr_id_b, score in pairs:
            pr_a = PR.nodes.get(identifier=pr_id_a)
            pr_b = PR.nodes.get(identifier=pr_id_b)

            # Connect and pass the relationship property
            self._connect_if_missing(pr_a.similar_to, pr_b, {"score": score})

    def _extract_labels_from_context(self, context: str) -> list[str]:
        match = re.search(r"LABELS: (.+)", context)
        if match:
            return [l.strip() for l in match.group(1).split(",") if l.strip()]  # noqa: E741
        return []

    def upsert_pr_entities(
        self,
        pr_id: int,
        author_id: int,
        entities: ExtractedEntities,
    ) -> None:
        """Connect extracted entity nodes to the PR and author in the KG."""
        if entities.is_empty():
            return

        pr_node = PR.nodes.get(identifier=pr_id)

        for lang_name in entities.languages:
            node = self._create_or_update_node(Language, {"name": lang_name})
            self._connect_if_missing(pr_node.uses_language, node)

        for fw_name in entities.frameworks:
            node = self._create_or_update_node(Framework, {"name": fw_name})
            self._connect_if_missing(pr_node.uses_framework, node)

        for domain_slug in entities.domains:
            node = self._create_or_update_node(Domain, {"slug": domain_slug})
            self._connect_if_missing(pr_node.touches_domain, node)

        for skill_slug in entities.skills:
            node = self._create_or_update_node(Skill, {"slug": skill_slug})
            self._connect_if_missing(pr_node.demonstrates_skill, node)

        for tool_name in entities.tools:
            node = self._create_or_update_node(Tool, {"name": tool_name})
            self._connect_if_missing(pr_node.uses_tool, node)
