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
from app.api.knowledge_graph.kg_schema import (
    JiraIssueContent,
    KGExperienceItem,
    KGExperienceProfileResponse,
    KGExpertiseSummary,
    KGResourceSnapshot,
)
from app.api.knowledge_graph.kg_taxonomy import (
    DOMAIN_SLUGS,
    FRAMEWORK_SLUGS,
    LANGUAGE_SLUGS,
    SKILL_SLUGS,
    TOOL_SLUGS,
)

DOMAIN_VALUE_MAP = {value.lower(): value for value in DOMAIN_SLUGS}
SKILL_VALUE_MAP = {value.lower(): value for value in SKILL_SLUGS}
LANGUAGE_VALUE_MAP = {value.lower(): value for value in LANGUAGE_SLUGS}
FRAMEWORK_VALUE_MAP = {value.lower(): value for value in FRAMEWORK_SLUGS}
TOOL_VALUE_MAP = {value.lower(): value for value in TOOL_SLUGS}


class KnowledgeGraphService:
    @staticmethod
    def _normalize_unique(values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            cleaned = value.strip()
            key = cleaned.lower()
            if not cleaned or key in seen:
                continue
            seen.add(key)
            normalized.append(cleaned)
        return normalized

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
    def _normalize_experience_items(
        items: list[KGExperienceItem],
        allowed_values: dict[str, str],
    ) -> list[KGExperienceItem]:
        normalized_items: dict[str, KGExperienceItem] = {}
        for item in items:
            canonical_name = allowed_values.get(item.name.strip().lower())
            if canonical_name is None:
                raise ValueError(f"Unknown taxonomy value: {item.name}")
            normalized_items[canonical_name.lower()] = KGExperienceItem(
                name=canonical_name,
                experience_level=item.experience_level,
            )
        return list(normalized_items.values())

    @staticmethod
    def _sort_experience_items(items: list[KGExperienceItem]) -> list[KGExperienceItem]:
        return sorted(items, key=lambda item: item.name.lower())

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

    @staticmethod
    def _build_resource_properties(
        *,
        user_id: str | None,
        profile_id: int | None = None,
        github_id: int | None = None,
        github_login: str | None = None,
        full_name: str | None = None,
        email: str | None = None,
        position_name: str | None = None,
    ) -> dict[str, Any]:
        if not user_id and github_id is None:
            raise ValueError("Either user_id or github_id is required")

        props: dict[str, Any] = {}
        if user_id:
            props["user_id"] = user_id
        if profile_id is not None:
            props["profile_id"] = profile_id
        if github_id is not None:
            props["github_id"] = github_id
        if github_login:
            props["login"] = github_login
        if full_name:
            props["full_name"] = full_name
        if email:
            props["email"] = email
        if position_name:
            props["position_name"] = position_name
        return props

    @staticmethod
    def _resource_match_prefix() -> str:
        return """
            MATCH (r:Resource)
            WHERE ($user_id IS NOT NULL AND r.user_id = $user_id)
               OR ($github_id IS NOT NULL AND r.github_id = $github_id)
            WITH r
            ORDER BY CASE WHEN $user_id IS NOT NULL AND r.user_id = $user_id THEN 0 ELSE 1 END
            LIMIT 1
        """

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

    def get_resource_expertise_summary(
        self,
        github_id: int | None = None,
        user_id: str | None = None,
    ) -> KGExpertiseSummary:
        if user_id is None and github_id is None:
            return KGExpertiseSummary()

        query = (
            self._resource_match_prefix()
            + """
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
            """
        )

        rows, _ = db.cypher_query(
            query,
            {"user_id": user_id, "github_id": github_id},
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

    def get_resource_experience(
        self,
        github_id: int | None = None,
        user_id: str | None = None,
    ) -> KGExperienceProfileResponse:
        if user_id is None and github_id is None:
            return KGExperienceProfileResponse()

        query = (
            self._resource_match_prefix()
            + """
            CALL {
                WITH r
                OPTIONAL MATCH (r)-[rel:HAS_EXPERIENCE_WITH]->(node:Domain)
                RETURN [item IN collect(
                    CASE
                        WHEN node IS NULL OR rel IS NULL THEN NULL
                        ELSE {name: node.slug, experience_level: rel.level}
                    END
                ) WHERE item IS NOT NULL] AS domains
            }
            CALL {
                WITH r
                OPTIONAL MATCH (r)-[rel:HAS_EXPERIENCE_WITH]->(node:Skill)
                RETURN [item IN collect(
                    CASE
                        WHEN node IS NULL OR rel IS NULL THEN NULL
                        ELSE {name: node.slug, experience_level: rel.level}
                    END
                ) WHERE item IS NOT NULL] AS skills
            }
            CALL {
                WITH r
                OPTIONAL MATCH (r)-[rel:HAS_EXPERIENCE_WITH]->(node:Language)
                RETURN [item IN collect(
                    CASE
                        WHEN node IS NULL OR rel IS NULL THEN NULL
                        ELSE {name: node.name, experience_level: rel.level}
                    END
                ) WHERE item IS NOT NULL] AS languages
            }
            CALL {
                WITH r
                OPTIONAL MATCH (r)-[rel:HAS_EXPERIENCE_WITH]->(node:Framework)
                RETURN [item IN collect(
                    CASE
                        WHEN node IS NULL OR rel IS NULL THEN NULL
                        ELSE {name: node.name, experience_level: rel.level}
                    END
                ) WHERE item IS NOT NULL] AS frameworks
            }
            CALL {
                WITH r
                OPTIONAL MATCH (r)-[rel:HAS_EXPERIENCE_WITH]->(node:Tool)
                RETURN [item IN collect(
                    CASE
                        WHEN node IS NULL OR rel IS NULL THEN NULL
                        ELSE {name: node.name, experience_level: rel.level}
                    END
                ) WHERE item IS NOT NULL] AS tools
            }
            RETURN r.user_id, r.profile_id, r.github_id, r.login, domains, skills, languages, frameworks, tools
            """
        )

        rows, _ = db.cypher_query(
            query,
            {"user_id": user_id, "github_id": github_id},
        )

        if not rows:
            return KGExperienceProfileResponse(
                user_id=user_id,
                github_id=github_id,
            )

        row = cast(list[Any], rows[0])
        return KGExperienceProfileResponse(
            user_id=cast(str | None, row[0]),
            profile_id=cast(int | None, row[1]),
            github_id=cast(int | None, row[2]) or github_id,
            github_login=cast(str | None, row[3]),
            domains=self._sort_experience_items(
                [
                    KGExperienceItem.model_validate(item)
                    for item in cast(list[Any], row[4] or [])
                ]
            ),
            skills=self._sort_experience_items(
                [
                    KGExperienceItem.model_validate(item)
                    for item in cast(list[Any], row[5] or [])
                ]
            ),
            languages=self._sort_experience_items(
                [
                    KGExperienceItem.model_validate(item)
                    for item in cast(list[Any], row[6] or [])
                ]
            ),
            frameworks=self._sort_experience_items(
                [
                    KGExperienceItem.model_validate(item)
                    for item in cast(list[Any], row[7] or [])
                ]
            ),
            tools=self._sort_experience_items(
                [
                    KGExperienceItem.model_validate(item)
                    for item in cast(list[Any], row[8] or [])
                ]
            ),
        )

    def upsert_pr(
        self,
        pr: PullRequestContent,
        repo_name: str,
        resource: KGResourceSnapshot | None = None,
    ) -> None:
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

        # 2. Upsert Author & Connect (keyed primarily on user_id, then github_id)
        if resource:
            resource_props = self._build_resource_properties(
                user_id=resource.user_id,
                profile_id=resource.profile_id,
                github_id=resource.github_id or pr.author.id,
                github_login=resource.github_login or pr.author.login,
                full_name=resource.full_name,
                email=resource.email,
                position_name=resource.position_name,
            )
        else:
            fallback_user_id = f"github:{pr.author.id}"
            resource_props = self._build_resource_properties(
                user_id=fallback_user_id,
                github_id=pr.author.id,
                github_login=pr.author.login,
            )

        author_node = self._create_or_update_node(Resource, resource_props)
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

    def upsert_resource_learning_intent(
        self,
        user_id: str,
        profile_id: int | None,
        github_id: int | None,
        github_login: str | None,
        full_name: str | None,
        email: str | None,
        position_name: str | None,
        entities: ExtractedEntities,
    ) -> dict[str, int]:
        """
        Replace user intent edges with the latest submitted intent.

        We intentionally replace previous intent edges to keep the graph aligned
        with the user's most recent goals.
        """
        resource_props = self._build_resource_properties(
            user_id=user_id,
            profile_id=profile_id,
            github_id=github_id,
            github_login=github_login,
            full_name=full_name,
            email=email,
            position_name=position_name,
        )

        resource_node = self._create_or_update_node(Resource, resource_props)

        resource_node.wants_to_work_in.disconnect_all()
        resource_node.wants_to_learn_skill.disconnect_all()
        resource_node.wants_to_learn_language.disconnect_all()
        resource_node.wants_to_learn_framework.disconnect_all()
        resource_node.wants_to_learn_tool.disconnect_all()

        domain_slugs = self._normalize_unique(entities.domains)
        skill_slugs = self._normalize_unique(entities.skills)
        language_names = self._normalize_unique(entities.languages)
        framework_names = self._normalize_unique(entities.frameworks)
        tool_names = self._normalize_unique(entities.tools)

        for domain_slug in domain_slugs:
            node = self._create_or_update_node(Domain, {"slug": domain_slug})
            self._connect_if_missing(resource_node.wants_to_work_in, node)

        for skill_slug in skill_slugs:
            node = self._create_or_update_node(Skill, {"slug": skill_slug})
            self._connect_if_missing(resource_node.wants_to_learn_skill, node)

        for language_name in language_names:
            node = self._create_or_update_node(Language, {"name": language_name})
            self._connect_if_missing(resource_node.wants_to_learn_language, node)

        for framework_name in framework_names:
            node = self._create_or_update_node(Framework, {"name": framework_name})
            self._connect_if_missing(resource_node.wants_to_learn_framework, node)

        for tool_name in tool_names:
            node = self._create_or_update_node(Tool, {"name": tool_name})
            self._connect_if_missing(resource_node.wants_to_learn_tool, node)

        return {
            "wants_to_work_in_domains": len(domain_slugs),
            "wants_to_learn_skills": len(skill_slugs),
            "wants_to_learn_languages": len(language_names),
            "wants_to_learn_frameworks": len(framework_names),
            "wants_to_learn_tools": len(tool_names),
        }

    def upsert_resource_experience(
        self,
        user_id: str,
        profile_id: int | None,
        github_id: int | None,
        github_login: str | None,
        full_name: str | None = None,
        email: str | None = None,
        position_name: str | None = None,
        domains: list[KGExperienceItem] | None = None,
        skills: list[KGExperienceItem] | None = None,
        languages: list[KGExperienceItem] | None = None,
        frameworks: list[KGExperienceItem] | None = None,
        tools: list[KGExperienceItem] | None = None,
    ) -> KGExperienceProfileResponse:
        resource_props = self._build_resource_properties(
            user_id=user_id,
            profile_id=profile_id,
            github_id=github_id,
            github_login=github_login,
            full_name=full_name,
            email=email,
            position_name=position_name,
        )

        normalized_domains = (
            self._normalize_experience_items(domains, DOMAIN_VALUE_MAP)
            if domains is not None
            else None
        )
        normalized_skills = (
            self._normalize_experience_items(skills, SKILL_VALUE_MAP)
            if skills is not None
            else None
        )
        normalized_languages = (
            self._normalize_experience_items(languages, LANGUAGE_VALUE_MAP)
            if languages is not None
            else None
        )
        normalized_frameworks = (
            self._normalize_experience_items(frameworks, FRAMEWORK_VALUE_MAP)
            if frameworks is not None
            else None
        )
        normalized_tools = (
            self._normalize_experience_items(tools, TOOL_VALUE_MAP)
            if tools is not None
            else None
        )

        resource_node = self._create_or_update_node(Resource, resource_props)

        if normalized_domains is not None:
            resource_node.has_experience_domain.disconnect_all()
            for item in normalized_domains:
                node = self._create_or_update_node(Domain, {"slug": item.name})
                self._connect_if_missing(
                    resource_node.has_experience_domain,
                    node,
                    {"level": item.experience_level},
                )

        if normalized_skills is not None:
            resource_node.has_experience_skill.disconnect_all()
            for item in normalized_skills:
                node = self._create_or_update_node(Skill, {"slug": item.name})
                self._connect_if_missing(
                    resource_node.has_experience_skill,
                    node,
                    {"level": item.experience_level},
                )

        if normalized_languages is not None:
            resource_node.has_experience_language.disconnect_all()
            for item in normalized_languages:
                node = self._create_or_update_node(Language, {"name": item.name})
                self._connect_if_missing(
                    resource_node.has_experience_language,
                    node,
                    {"level": item.experience_level},
                )

        if normalized_frameworks is not None:
            resource_node.has_experience_framework.disconnect_all()
            for item in normalized_frameworks:
                node = self._create_or_update_node(Framework, {"name": item.name})
                self._connect_if_missing(
                    resource_node.has_experience_framework,
                    node,
                    {"level": item.experience_level},
                )

        if normalized_tools is not None:
            resource_node.has_experience_tool.disconnect_all()
            for item in normalized_tools:
                node = self._create_or_update_node(Tool, {"name": item.name})
                self._connect_if_missing(
                    resource_node.has_experience_tool,
                    node,
                    {"level": item.experience_level},
                )

        return self.get_resource_experience(github_id=github_id, user_id=user_id)
