"""Unit tests for KnowledgeGraphService.

All Neo4j/neomodel calls are mocked — these tests verify the upsert
logic, relationship wiring, and label extraction without a graph DB.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.api.knowledge_graph.kg_service import KnowledgeGraphService

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def service() -> KnowledgeGraphService:
    return KnowledgeGraphService()


# ===================================================================
# 1. Label extraction from context string
# ===================================================================

class TestExtractLabelsFromContext:
    def test_extracts_comma_separated_labels(self, service: KnowledgeGraphService) -> None:
        context = "PR_INTENT: Fix\nLABELS: bug, enhancement, docs\nFILE_CHANGES:"
        result = service._extract_labels_from_context(context)
        assert result == ["bug", "enhancement", "docs"]

    def test_returns_empty_for_no_labels_line(self, service: KnowledgeGraphService) -> None:
        context = "PR_INTENT: Fix\nFILE_CHANGES:\n- src/main.py"
        result = service._extract_labels_from_context(context)
        assert result == []

    def test_handles_empty_labels(self, service: KnowledgeGraphService) -> None:
        context = "LABELS: "
        result = service._extract_labels_from_context(context)
        assert result == []

    def test_handles_single_label(self, service: KnowledgeGraphService) -> None:
        context = "LABELS: bugfix"
        result = service._extract_labels_from_context(context)
        assert result == ["bugfix"]

    def test_strips_whitespace(self, service: KnowledgeGraphService) -> None:
        context = "LABELS:   bug ,  fix  ,  docs  "
        result = service._extract_labels_from_context(context)
        assert result == ["bug", "fix", "docs"]


# ===================================================================
# 2. _create_or_update_node (static helper)
# ===================================================================

class TestCreateOrUpdateNode:
    def test_delegates_to_model(self) -> None:
        mock_model = MagicMock()
        mock_node = MagicMock()
        mock_model.create_or_update.return_value = [mock_node]

        result = KnowledgeGraphService._create_or_update_node(
            mock_model, {"name": "test"}
        )

        mock_model.create_or_update.assert_called_once_with({"name": "test"})
        assert result is mock_node


# ===================================================================
# 3. upsert_pr
# ===================================================================

class TestUpsertPr:
    @patch.object(KnowledgeGraphService, "_create_or_update_node")
    def test_creates_pr_author_component_files_labels(
        self, mock_upsert: MagicMock, service: KnowledgeGraphService
    ) -> None:
        pr_node = MagicMock()
        author_node = MagicMock()
        component_node = MagicMock()
        file_node = MagicMock()
        label_node = MagicMock()

        mock_upsert.side_effect = [
            pr_node, author_node, component_node, file_node, label_node
        ]

        # Ensure relationships don't think they are already connected
        pr_node.author.is_connected.return_value = False
        pr_node.repo_component.is_connected.return_value = False
        pr_node.modified_files.is_connected.return_value = False
        pr_node.pr_labels.is_connected.return_value = False

        pr = MagicMock()
        pr.id = 100
        pr.number = 1
        pr.title = "Fix auth"
        pr.html_url = "https://github.com/org/repo/pull/1"
        pr.author.login = "alice"
        pr.author.id = 42
        pr.changed_files = ["src/auth.py"]
        pr.labels = ["bugfix"]
        pr.context = None

        service.upsert_pr(pr, repo_name="repo")

        assert mock_upsert.call_count == 5
        pr_node.author.connect.assert_called_once_with(author_node)
        pr_node.repo_component.connect.assert_called_once_with(component_node)
        pr_node.modified_files.connect.assert_called_once_with(file_node)
        pr_node.pr_labels.connect.assert_called_once_with(label_node)

    @patch.object(KnowledgeGraphService, "_create_or_update_node")
    def test_extracts_labels_from_context_when_none_provided(
        self, mock_upsert: MagicMock, service: KnowledgeGraphService
    ) -> None:
        pr_node = MagicMock()
        author_node = MagicMock()
        component_node = MagicMock()
        label_node = MagicMock()

        mock_upsert.side_effect = [
            pr_node, author_node, component_node, label_node
        ]

        # Ensure relationships don't think they are already connected
        pr_node.author.is_connected.return_value = False
        pr_node.repo_component.is_connected.return_value = False
        pr_node.pr_labels.is_connected.return_value = False

        pr = MagicMock()
        pr.id = 200
        pr.number = 2
        pr.title = "Add feature"
        pr.html_url = "https://github.com/org/repo/pull/2"
        pr.author.login = "bob"
        pr.author.id = 99
        pr.changed_files = []
        pr.labels = []  # Empty labels
        pr.context = "LABELS: enhancement"

        service.upsert_pr(pr, repo_name="repo")

        # Should extract "enhancement" from context
        pr_node.pr_labels.connect.assert_called_once()


# ===================================================================
# 4. upsert_jira_issue
# ===================================================================

class TestUpsertJiraIssue:
    @patch.object(KnowledgeGraphService, "_create_or_update_node")
    def test_creates_issue_and_epic_nodes(
        self, mock_upsert: MagicMock, service: KnowledgeGraphService
    ) -> None:
        issue_node = MagicMock()
        epic_node = MagicMock()
        comp_node = MagicMock()
        mock_upsert.side_effect = [issue_node, epic_node, comp_node]

        # Ensure relationships don't think they are already connected
        issue_node.epic.is_connected.return_value = False
        issue_node.components.is_connected.return_value = False

        issue = {
            "key": "PROJ-1",
            "summary": "Fix login",
            "status": "Done",
            "epic_key": "PROJ-E1",
            "epic_summary": "Auth Epic",
            "url": "https://jira.example.com/browse/PROJ-1",
            "components": ["auth"],
        }

        service.upsert_jira_issue(issue)

        assert mock_upsert.call_count == 3
        issue_node.epic.connect.assert_called_once_with(epic_node)
        issue_node.components.connect.assert_called_once_with(comp_node)

    @patch.object(KnowledgeGraphService, "_create_or_update_node")
    def test_skips_epic_when_not_present(
        self, mock_upsert: MagicMock, service: KnowledgeGraphService
    ) -> None:
        issue_node = MagicMock()
        mock_upsert.return_value = issue_node

        issue = {
            "key": "PROJ-2",
            "summary": "Minor fix",
            "status": "Open",
            "epic_key": None,
            "epic_summary": None,
            "url": "https://jira.example.com/browse/PROJ-2",
            "components": [],
        }

        service.upsert_jira_issue(issue)

        issue_node.epic.connect.assert_not_called()


# ===================================================================
# 5. link_pr_to_jira
# ===================================================================

class TestLinkPrToJira:
    @patch("app.api.knowledge_graph.kg_service.JiraIssue")
    @patch("app.api.knowledge_graph.kg_service.PR")
    def test_connects_pr_to_issue(
        self,
        mock_pr_cls: MagicMock,
        mock_issue_cls: MagicMock,
        service: KnowledgeGraphService,
    ) -> None:
        pr_node = MagicMock()
        issue_node = MagicMock()
        mock_pr_cls.nodes.get.return_value = pr_node
        mock_issue_cls.nodes.get.return_value = issue_node

        # Ensure relationships don't think they are already connected
        pr_node.resolves.is_connected.return_value = False

        service.link_pr_to_jira(pr_id=100, issue_key="PROJ-1")

        mock_pr_cls.nodes.get.assert_called_once_with(identifier=100)
        mock_issue_cls.nodes.get.assert_called_once_with(key="PROJ-1")
        pr_node.resolves.connect.assert_called_once_with(issue_node)


# ===================================================================
# 6. add_similar_pr_edges
# ===================================================================

class TestAddSimilarPrEdges:
    @patch("app.api.knowledge_graph.kg_service.PR")
    def test_connects_similar_prs(
        self, mock_pr_cls: MagicMock, service: KnowledgeGraphService
    ) -> None:
        pr_a = MagicMock()
        pr_b = MagicMock()
        mock_pr_cls.nodes.get.side_effect = [pr_a, pr_b]

        # Ensure relationships don't think they are already connected
        pr_a.similar_to.is_connected.return_value = False

        service.add_similar_pr_edges([(1, 2, 0.95)])

        pr_a.similar_to.connect.assert_called_once_with(pr_b, {"score": 0.95})


# ===================================================================
# 7. upsert_pr_entities
# ===================================================================

class TestUpsertPrEntities:
    @patch("app.api.knowledge_graph.kg_service.PR")
    @patch.object(KnowledgeGraphService, "_create_or_update_node")
    def test_connects_all_entity_types(
        self,
        mock_upsert: MagicMock,
        mock_pr_cls: MagicMock,
        service: KnowledgeGraphService,
    ) -> None:
        pr_node = MagicMock()
        mock_pr_cls.nodes.get.return_value = pr_node

        entity_node = MagicMock()
        mock_upsert.return_value = entity_node

        # Ensure relationships don't think they are already connected
        pr_node.uses_language.is_connected.return_value = False
        pr_node.uses_framework.is_connected.return_value = False
        pr_node.touches_domain.is_connected.return_value = False
        pr_node.demonstrates_skill.is_connected.return_value = False
        pr_node.uses_tool.is_connected.return_value = False

        entities = MagicMock()
        entities.is_empty.return_value = False
        entities.languages = ["Python"]
        entities.frameworks = ["FastAPI"]
        entities.domains = ["backend"]
        entities.skills = ["api-design"]
        entities.tools = ["Docker"]

        service.upsert_pr_entities(pr_id=100, author_id=42, entities=entities)

        assert pr_node.uses_language.connect.call_count == 1
        assert pr_node.uses_framework.connect.call_count == 1
        assert pr_node.touches_domain.connect.call_count == 1
        assert pr_node.demonstrates_skill.connect.call_count == 1
        assert pr_node.uses_tool.connect.call_count == 1

    @patch("app.api.knowledge_graph.kg_service.PR")
    @patch.object(KnowledgeGraphService, "_create_or_update_node")
    def test_skips_when_entities_empty(
        self,
        mock_upsert: MagicMock,
        mock_pr_cls: MagicMock,
        service: KnowledgeGraphService,
    ) -> None:
        entities = MagicMock()
        entities.is_empty.return_value = True

        service.upsert_pr_entities(pr_id=100, author_id=42, entities=entities)

        mock_pr_cls.nodes.get.assert_not_called()
        mock_upsert.assert_not_called()
