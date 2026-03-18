"""Unit tests for VectorEmbeddingService.

Tests cover text cleaning, dimension normalization, prompt-name mapping,
retryable-error detection, and the store_pr_contexts pipeline.
API/model calls are fully mocked.
"""

from unittest.mock import MagicMock, patch

import pytest
import requests

from app.api.embedding.embedding_service import (
    VectorEmbeddingService,
    is_retryable_error,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def service() -> VectorEmbeddingService:
    """Build service with API mode, bypassing __init__ side-effects."""
    with patch.object(VectorEmbeddingService, "__init__", lambda self, *a, **kw: None):
        svc = VectorEmbeddingService.__new__(VectorEmbeddingService)
        svc.db = MagicMock()
        svc.use_api = True
        svc.api_key = "test-key"
        svc.api_url = "https://api.jina.ai/v1/embeddings"
        svc.embedding_model = "jina-code-embeddings-0.5b"
        return svc


# ===================================================================
# 1. is_retryable_error (module-level helper)
# ===================================================================

class TestIsRetryableError:
    def test_429_is_retryable(self) -> None:
        resp = MagicMock()
        resp.status_code = 429
        exc = requests.exceptions.HTTPError(response=resp)
        assert is_retryable_error(exc) is True

    def test_500_is_retryable(self) -> None:
        resp = MagicMock()
        resp.status_code = 500
        exc = requests.exceptions.HTTPError(response=resp)
        assert is_retryable_error(exc) is True

    def test_502_is_retryable(self) -> None:
        resp = MagicMock()
        resp.status_code = 502
        exc = requests.exceptions.HTTPError(response=resp)
        assert is_retryable_error(exc) is True

    def test_400_is_not_retryable(self) -> None:
        resp = MagicMock()
        resp.status_code = 400
        exc = requests.exceptions.HTTPError(response=resp)
        assert is_retryable_error(exc) is False

    def test_connection_error_is_retryable(self) -> None:
        exc = requests.exceptions.ConnectionError("Connection refused")
        assert is_retryable_error(exc) is True

    def test_timeout_is_retryable(self) -> None:
        exc = requests.exceptions.Timeout("Timed out")
        assert is_retryable_error(exc) is True

    def test_non_requests_error_not_retryable(self) -> None:
        exc = ValueError("Some error")
        assert is_retryable_error(exc) is False


# ===================================================================
# 2. Prompt name to task mapping (static method)
# ===================================================================

class TestPromptNameToTask:
    def test_query_suffix(self) -> None:
        assert VectorEmbeddingService._prompt_name_to_task("nl2code_query") == "nl2code.query"

    def test_document_suffix(self) -> None:
        assert VectorEmbeddingService._prompt_name_to_task("retrieval_document") == "retrieval.passage"

    def test_already_dotted(self) -> None:
        assert VectorEmbeddingService._prompt_name_to_task("nl2code.query") == "nl2code.query"

    def test_none_returns_none(self) -> None:
        assert VectorEmbeddingService._prompt_name_to_task(None) is None

    def test_unrecognized_returns_none(self) -> None:
        assert VectorEmbeddingService._prompt_name_to_task("random_name") is None


# ===================================================================
# 3. Text cleaning
# ===================================================================

class TestCleanTextForEmbedding:
    def test_normal_text_passes_through(self, service: VectorEmbeddingService) -> None:
        result = service._clean_text_for_embedding("Hello world")
        assert result == "Hello world"

    def test_empty_string_returns_placeholder(self, service: VectorEmbeddingService) -> None:
        assert service._clean_text_for_embedding("") == "Empty content"

    def test_whitespace_only_returns_placeholder(self, service: VectorEmbeddingService) -> None:
        assert service._clean_text_for_embedding("   ") == "Empty content"

    def test_removes_zero_width_chars(self, service: VectorEmbeddingService) -> None:
        text = "Hello\u200bWorld\ufeff"
        result = service._clean_text_for_embedding(text)
        assert "\u200b" not in result
        assert "\ufeff" not in result
        assert "HelloWorld" in result

    def test_collapses_whitespace(self, service: VectorEmbeddingService) -> None:
        result = service._clean_text_for_embedding("Hello   \t  World")
        assert result == "Hello World"

    def test_truncates_long_text(self, service: VectorEmbeddingService) -> None:
        long_text = "x" * 10000
        result = service._clean_text_for_embedding(long_text)
        assert len(result) <= 8020
        assert result.endswith("[truncated]")

    def test_preserves_newlines_in_control_char_removal(self, service: VectorEmbeddingService) -> None:
        text = "Line1\nLine2\tTabbed"
        result = service._clean_text_for_embedding(text)
        # Newlines/tabs get collapsed to single space by the whitespace regex
        assert "Line1" in result
        assert "Line2" in result


# ===================================================================
# 4. Embedding dimension normalization
# ===================================================================

class TestNormalizeEmbeddingDimension:
    @patch("app.api.embedding.embedding_service.settings")
    def test_exact_dimension_unchanged(self, mock_settings: MagicMock, service: VectorEmbeddingService) -> None:
        mock_settings.EMBEDDING_DIMENSION = 4
        embedding = [0.1, 0.2, 0.3, 0.4]
        result = service._normalize_embedding_dimension(embedding)
        assert result == [0.1, 0.2, 0.3, 0.4]

    @patch("app.api.embedding.embedding_service.settings")
    def test_pads_shorter_embedding(self, mock_settings: MagicMock, service: VectorEmbeddingService) -> None:
        mock_settings.EMBEDDING_DIMENSION = 6
        embedding = [0.1, 0.2, 0.3]
        result = service._normalize_embedding_dimension(embedding)
        assert len(result) == 6
        assert result[:3] == [0.1, 0.2, 0.3]
        assert result[3:] == [0.0, 0.0, 0.0]

    @patch("app.api.embedding.embedding_service.settings")
    def test_truncates_longer_embedding(self, mock_settings: MagicMock, service: VectorEmbeddingService) -> None:
        mock_settings.EMBEDDING_DIMENSION = 3
        embedding = [0.1, 0.2, 0.3, 0.4, 0.5]
        result = service._normalize_embedding_dimension(embedding)
        assert result == [0.1, 0.2, 0.3]


# ===================================================================
# 5. Store PR contexts pipeline
# ===================================================================

class TestStorePrContexts:
    def _make_pr_content(self, pr_id: int = 100, title: str = "Fix", context: str = "ctx") -> MagicMock:
        pr = MagicMock()
        pr.id = pr_id
        pr.number = 1
        pr.title = title
        pr.body = "body"
        pr.html_url = "https://github.com/org/repo/pull/1"
        pr.context = context
        pr.changed_files = ["a.py"]
        pr.labels = ["bug"]
        pr.repo_id = 999
        pr.repo_name = "repo"
        pr.author = MagicMock()
        pr.author.login = "alice"
        pr.author.id = 42
        return pr

    def test_empty_list_returns_zero(self, service: VectorEmbeddingService) -> None:
        author = MagicMock()
        author.login = "alice"
        assert service.store_pr_contexts(author, []) == 0

    @patch.object(VectorEmbeddingService, "generate_embeddings")
    def test_skips_already_embedded_prs(
        self,
        mock_gen: MagicMock,
        service: VectorEmbeddingService,
    ) -> None:
        author = MagicMock()
        author.login = "alice"
        pr = self._make_pr_content(pr_id=100)

        # Simulate PR already exists in DB
        service.db.query.return_value.filter.return_value.all.return_value = [("100",)]

        result = service.store_pr_contexts(author, [pr])

        mock_gen.assert_not_called()
        assert result == 1  # skipped count

    @patch("app.api.embedding.embedding_service.GitHubPRVector")
    @patch.object(VectorEmbeddingService, "_normalize_embedding_dimension", side_effect=lambda self, x: x)
    @patch.object(VectorEmbeddingService, "generate_embeddings")
    def test_stores_new_pr_vectors(
        self,
        mock_gen: MagicMock,
        mock_normalize: MagicMock,
        mock_vector_cls: MagicMock,
        service: VectorEmbeddingService,
    ) -> None:
        author = MagicMock()
        author.login = "alice"
        pr = self._make_pr_content(pr_id=200)

        # No existing PRs
        service.db.query.return_value.filter.return_value.all.return_value = []
        mock_gen.return_value = [[0.1, 0.2, 0.3]]

        result = service.store_pr_contexts(author, [pr])

        mock_gen.assert_called_once()
        service.db.add.assert_called()
        service.db.commit.assert_called()
        assert result >= 1


# ===================================================================
# 6. Store all authors PR contexts
# ===================================================================

class TestStoreAllAuthorsPrContexts:
    @patch.object(VectorEmbeddingService, "store_pr_contexts")
    def test_calls_store_for_each_author(
        self, mock_store: MagicMock, service: VectorEmbeddingService
    ) -> None:
        from app.api.integrations.GitHub.github_schema import (
            GitHubUser,
        )

        pr1 = MagicMock()
        pr1.author = GitHubUser(login="alice", id=1)
        pr2 = MagicMock()
        pr2.author = GitHubUser(login="bob", id=2)

        mock_store.return_value = 1

        service.store_all_authors_pr_contexts({"alice": [pr1], "bob": [pr2]})

        assert mock_store.call_count == 2

    @patch.object(VectorEmbeddingService, "store_pr_contexts")
    def test_skips_empty_pr_lists(
        self, mock_store: MagicMock, service: VectorEmbeddingService
    ) -> None:
        service.store_all_authors_pr_contexts({"alice": [], "bob": []})
        mock_store.assert_not_called()
