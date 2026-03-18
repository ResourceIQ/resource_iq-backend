"""Unit tests for ScoreService.

All database queries, embedding generation, and torch operations are
mocked so these tests run without GPU, model files, or database access.
"""

from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.api.score.score_schema import BestFitInput, PrScoreInfo, ScoreProfile
from app.api.score.score_service import ScoreService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_db() -> MagicMock:
    return MagicMock()


@pytest.fixture()
def service(mock_db: MagicMock) -> ScoreService:
    return ScoreService(mock_db)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_profile(
    github_id: int | None = 42,
    user_id: str | None = None,
    position: str = "Developer",
) -> MagicMock:
    p = MagicMock()
    p.user_id = user_id or str(uuid4())
    p.github_id = github_id
    p.position = position
    return p


_SENTINEL = object()


def _make_pr_vector(
    pr_id: int = 1,
    pr_title: str = "Fix auth",
    pr_url: str = "https://github.com/org/repo/pull/1",
    pr_description: str = "Fixed redirect",
    embedding: list[float] | None | object = _SENTINEL,
) -> MagicMock:
    v = MagicMock()
    v.pr_id = pr_id
    v.pr_title = pr_title
    v.pr_url = pr_url
    v.pr_description = pr_description
    v.embedding = [0.1, 0.2, 0.3] if embedding is _SENTINEL else embedding
    return v


# ===================================================================
# 1. Aggregate similarity score (class method, pure logic)
# ===================================================================

class TestAggregateSimilarityScore:
    def test_empty_similarities(self) -> None:
        assert ScoreService._aggregate_similarity_score([]) == 0.0

    def test_all_below_threshold(self) -> None:
        result = ScoreService._aggregate_similarity_score([0.1, 0.15, 0.2])
        assert result == 0.0

    def test_single_relevant_similarity(self) -> None:
        result = ScoreService._aggregate_similarity_score([0.5])
        # With only 1 relevant PR out of RELEVANT_PR_TARGET=3 and
        # HISTORY_PR_TARGET=10, confidence is penalized heavily.
        assert result > 0
        assert result < 500

    def test_multiple_strong_similarities(self) -> None:
        sims = [0.9, 0.85, 0.8, 0.75, 0.7]
        result = ScoreService._aggregate_similarity_score(sims)
        assert result > 0

    def test_more_history_increases_confidence(self) -> None:
        # Same top similarities but more history = higher confidence
        few_history = [0.8, 0.7, 0.6]
        large_history = [0.8, 0.7, 0.6, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25]

        score_few = ScoreService._aggregate_similarity_score(few_history)
        score_large = ScoreService._aggregate_similarity_score(large_history)

        assert score_large > score_few

    def test_sorted_order_doesnt_matter(self) -> None:
        ascending = [0.3, 0.5, 0.7, 0.9]
        descending = [0.9, 0.7, 0.5, 0.3]

        assert ScoreService._aggregate_similarity_score(ascending) == \
               ScoreService._aggregate_similarity_score(descending)

    def test_respects_max_scoring_prs(self) -> None:
        sims = [0.9] * 20
        result = ScoreService._aggregate_similarity_score(sims)
        # Score should be the same whether we have 8 or 20 identical relevant sims
        # because MAX_SCORING_PRS caps at 8
        sims_capped = [0.9] * 8
        result_capped = ScoreService._aggregate_similarity_score(sims_capped)
        # The only difference is history_confidence (20 vs 8 total)
        assert result >= result_capped


# ===================================================================
# 2. Calculate developer GitHub score
# ===================================================================

class TestCalculateDeveloperGithubScore:
    @patch("app.api.score.score_service.cosine_similarity")
    @patch("app.api.score.score_service.torch")
    def test_returns_zero_with_no_prs(
        self,
        mock_torch: MagicMock,
        mock_cos_sim: MagicMock,
        service: ScoreService,
        mock_db: MagicMock,
    ) -> None:
        mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []

        score, prs = service._calculate_developer_github_score(
            github_id=42, task_embedding=[0.1, 0.2], threshold=50
        )

        assert score == 0.0
        assert prs == []

    @patch("app.api.score.score_service.cosine_similarity")
    @patch("app.api.score.score_service.torch")
    def test_calculates_score_from_prs(
        self,
        mock_torch: MagicMock,
        mock_cos_sim: MagicMock,
        service: ScoreService,
        mock_db: MagicMock,
    ) -> None:
        pr_vectors = [
            _make_pr_vector(pr_id=1, embedding=[0.5, 0.5, 0.5]),
            _make_pr_vector(pr_id=2, embedding=[0.3, 0.3, 0.3]),
        ]
        mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = pr_vectors

        mock_tensor = MagicMock()
        mock_torch.tensor.return_value = mock_tensor
        mock_torch.float = "float32"

        # Return high similarity for both PRs
        sim_result = MagicMock()
        sim_result.item.return_value = 0.85
        mock_cos_sim.return_value = sim_result

        score, prs = service._calculate_developer_github_score(
            github_id=42, task_embedding=[0.1, 0.2, 0.3], threshold=50
        )

        assert score > 0
        assert len(prs) == 2
        assert prs[0].match_percentage == pytest.approx(85.0)

    @patch("app.api.score.score_service.cosine_similarity")
    @patch("app.api.score.score_service.torch")
    def test_skips_prs_with_none_embedding(
        self,
        mock_torch: MagicMock,
        mock_cos_sim: MagicMock,
        service: ScoreService,
        mock_db: MagicMock,
    ) -> None:
        pr_vectors = [
            _make_pr_vector(pr_id=1, embedding=None),
            _make_pr_vector(pr_id=2, embedding=[0.5, 0.5]),
        ]
        mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = pr_vectors

        mock_tensor = MagicMock()
        mock_torch.tensor.return_value = mock_tensor
        mock_torch.float = "float32"

        sim_result = MagicMock()
        sim_result.item.return_value = 0.7
        mock_cos_sim.return_value = sim_result

        score, prs = service._calculate_developer_github_score(
            github_id=42, task_embedding=[0.1, 0.2], threshold=50
        )

        assert len(prs) == 1
        assert prs[0].pr_id == 2

    @patch("app.api.score.score_service.cosine_similarity")
    @patch("app.api.score.score_service.torch")
    def test_returns_top_3_prs(
        self,
        mock_torch: MagicMock,
        mock_cos_sim: MagicMock,
        service: ScoreService,
        mock_db: MagicMock,
    ) -> None:
        pr_vectors = [_make_pr_vector(pr_id=i, embedding=[0.5] * 3) for i in range(5)]
        mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = pr_vectors

        mock_tensor = MagicMock()
        mock_torch.tensor.return_value = mock_tensor
        mock_torch.float = "float32"

        sim_result = MagicMock()
        sim_result.item.return_value = 0.6
        mock_cos_sim.return_value = sim_result

        _, prs = service._calculate_developer_github_score(
            github_id=42, task_embedding=[0.1] * 3, threshold=50
        )

        assert len(prs) <= 3


# ===================================================================
# 3. Get best fits
# ===================================================================

class TestGetBestFits:
    def test_returns_empty_when_no_profiles(
        self, service: ScoreService, mock_db: MagicMock
    ) -> None:
        mock_db.query.return_value.all.return_value = []

        result = service.get_best_fits(
            BestFitInput(task_title="Build auth", task_description="OAuth flow")
        )

        assert result == []

    @patch.object(ScoreService, "_calculate_developer_github_score")
    @patch("app.api.score.score_service.VectorEmbeddingService")
    def test_ranks_by_score_descending(
        self,
        mock_embed_cls: MagicMock,
        mock_calc_score: MagicMock,
        service: ScoreService,
        mock_db: MagicMock,
    ) -> None:
        profiles = [
            _make_profile(github_id=1, user_id=str(uuid4())),
            _make_profile(github_id=2, user_id=str(uuid4())),
            _make_profile(github_id=3, user_id=str(uuid4())),
        ]
        mock_db.query.return_value.all.return_value = profiles

        mock_embed = MagicMock()
        mock_embed.generate_embeddings.return_value = [[0.1, 0.2, 0.3]]
        mock_embed_cls.return_value = mock_embed

        mock_db.execute.return_value.scalar.return_value = "Test User"

        # Return different scores for each profile
        mock_calc_score.side_effect = [
            (300.0, []),
            (800.0, []),
            (500.0, []),
        ]

        result = service.get_best_fits(
            BestFitInput(task_title="Build auth", max_results=3)
        )

        assert len(result) == 3
        assert result[0].github_pr_score == 800.0
        assert result[1].github_pr_score == 500.0
        assert result[2].github_pr_score == 300.0

    @patch.object(ScoreService, "_calculate_developer_github_score")
    @patch("app.api.score.score_service.VectorEmbeddingService")
    def test_skips_profiles_without_github(
        self,
        mock_embed_cls: MagicMock,
        mock_calc_score: MagicMock,
        service: ScoreService,
        mock_db: MagicMock,
    ) -> None:
        profiles = [
            _make_profile(github_id=1),
            _make_profile(github_id=None),
        ]
        mock_db.query.return_value.all.return_value = profiles

        mock_embed = MagicMock()
        mock_embed.generate_embeddings.return_value = [[0.1, 0.2]]
        mock_embed_cls.return_value = mock_embed

        mock_db.execute.return_value.scalar.return_value = "User"
        mock_calc_score.return_value = (500.0, [])

        result = service.get_best_fits(
            BestFitInput(task_title="task", max_results=5)
        )

        assert len(result) == 1
        mock_calc_score.assert_called_once()

    @patch.object(ScoreService, "_calculate_developer_github_score")
    @patch("app.api.score.score_service.VectorEmbeddingService")
    def test_respects_max_results(
        self,
        mock_embed_cls: MagicMock,
        mock_calc_score: MagicMock,
        service: ScoreService,
        mock_db: MagicMock,
    ) -> None:
        profiles = [_make_profile(github_id=i) for i in range(10)]
        mock_db.query.return_value.all.return_value = profiles

        mock_embed = MagicMock()
        mock_embed.generate_embeddings.return_value = [[0.1, 0.2]]
        mock_embed_cls.return_value = mock_embed

        mock_db.execute.return_value.scalar.return_value = "User"
        mock_calc_score.return_value = (100.0, [])

        result = service.get_best_fits(
            BestFitInput(task_title="task", max_results=3)
        )

        assert len(result) == 3

    @patch.object(ScoreService, "_calculate_developer_github_score")
    @patch("app.api.score.score_service.VectorEmbeddingService")
    def test_handles_scoring_error_gracefully(
        self,
        mock_embed_cls: MagicMock,
        mock_calc_score: MagicMock,
        service: ScoreService,
        mock_db: MagicMock,
    ) -> None:
        profiles = [
            _make_profile(github_id=1),
            _make_profile(github_id=2),
        ]
        mock_db.query.return_value.all.return_value = profiles

        mock_embed = MagicMock()
        mock_embed.generate_embeddings.return_value = [[0.1, 0.2]]
        mock_embed_cls.return_value = mock_embed

        mock_db.execute.return_value.scalar.return_value = "User"
        mock_calc_score.side_effect = [
            Exception("DB error"),
            (500.0, []),
        ]

        result = service.get_best_fits(
            BestFitInput(task_title="task", max_results=5)
        )

        # First profile fails, second succeeds
        assert len(result) == 1
        assert result[0].github_pr_score == 500.0

    @patch.object(ScoreService, "_calculate_developer_github_score")
    @patch("app.api.score.score_service.VectorEmbeddingService")
    def test_total_score_computed(
        self,
        mock_embed_cls: MagicMock,
        mock_calc_score: MagicMock,
        service: ScoreService,
        mock_db: MagicMock,
    ) -> None:
        profiles = [_make_profile(github_id=1)]
        mock_db.query.return_value.all.return_value = profiles

        mock_embed = MagicMock()
        mock_embed.generate_embeddings.return_value = [[0.1]]
        mock_embed_cls.return_value = mock_embed

        mock_db.execute.return_value.scalar.return_value = "Alice"

        pr_info = [PrScoreInfo(pr_id=1, pr_title="Fix", match_percentage=85.0)]
        mock_calc_score.return_value = (750.0, pr_info)

        result = service.get_best_fits(
            BestFitInput(task_title="auth task", max_results=5)
        )

        assert len(result) == 1
        assert result[0].github_pr_score == 750.0
        assert result[0].total_score == 750.0
        assert result[0].pr_info[0].match_percentage == 85.0
