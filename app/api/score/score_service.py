import logging
from typing import Any, cast

import torch
from sqlalchemy.orm import Session
from sqlmodel import select
from torch import cosine_similarity

from app.api.embedding.embedding_model import GitHubPRVector, JiraIssueVector
from app.api.embedding.embedding_service import VectorEmbeddingService
from app.api.knowledge_graph.kg_extractor import ExtractedEntities, LLMEntityExtractor
from app.api.knowledge_graph.kg_schema import KGExpertiseSummary
from app.api.knowledge_graph.kg_service import KnowledgeGraphService
from app.api.profiles.profile_model import ResourceProfile
from app.api.score.score_schema import (
    BestFitInput,
    IssueScoreInfo,
    KGMatchInfo,
    PrScoreInfo,
    ScoreProfile,
)
from app.api.user.user_model import User
from app.core.config import settings

logger = logging.getLogger(__name__)


class ScoreService:
    # Ignore weak cosine matches that tend to be semantically noisy.
    MIN_RELEVANT_SIMILARITY = 0.28
    # We only need a small, strong set of PRs to estimate fit quality.
    MAX_SCORING_PRS = 8
    # Confidence saturates after this many relevant PRs.
    RELEVANT_PR_TARGET = 3
    # Confidence saturates after this many total PRs.
    HISTORY_PR_TARGET = 10
    KG_MAX_SCORE = 350.0
    KG_HISTORY_TARGET = 4
    KG_CATEGORY_WEIGHTS = {
        "domains": 4.0,
        "skills": 3.0,
        "frameworks": 2.0,
        "tools": 1.5,
        "languages": 1.0,
    }
    KG_EVIDENCE_TARGETS = {
        "domains": 2,
        "skills": 2,
        "frameworks": 2,
        "tools": 2,
        "languages": 3,
    }

    def __init__(self, db: Session) -> None:
        self.db = db
        self.task_entity_extractor = LLMEntityExtractor()
        self.kg_service = KnowledgeGraphService() if settings.neo4j_enabled else None
        self._disable_kg_scoring = False

    @staticmethod
    def _normalize_entity_values(values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            key = value.strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            normalized.append(key)
        return normalized

    def _extract_task_entities(self, best_fit_input: BestFitInput) -> ExtractedEntities:
        return self.task_entity_extractor.extract(
            files=[],
            commit_messages=[],
            title=best_fit_input.task_title,
            body=best_fit_input.task_description,
            labels=[],
        )

    @classmethod
    def _score_knowledge_graph_alignment(
        cls,
        task_entities: ExtractedEntities,
        expertise_summary: KGExpertiseSummary,
    ) -> tuple[float, list[KGMatchInfo]]:
        if task_entities.is_empty() or expertise_summary.pr_count <= 0:
            return 0.0, []

        expertise_by_category: dict[str, dict[str, int]] = {
            "languages": expertise_summary.languages,
            "frameworks": expertise_summary.frameworks,
            "domains": expertise_summary.domains,
            "skills": expertise_summary.skills,
            "tools": expertise_summary.tools,
        }
        task_by_category: dict[str, list[str]] = {
            "languages": cls._normalize_entity_values(task_entities.languages),
            "frameworks": cls._normalize_entity_values(task_entities.frameworks),
            "domains": cls._normalize_entity_values(task_entities.domains),
            "skills": cls._normalize_entity_values(task_entities.skills),
            "tools": cls._normalize_entity_values(task_entities.tools),
        }

        matches: list[KGMatchInfo] = []
        weighted_alignment = 0.0
        applicable_weight = 0.0

        for category, weight in cls.KG_CATEGORY_WEIGHTS.items():
            requested_values = task_by_category[category]
            if not requested_values:
                continue

            applicable_weight += weight
            category_counts = expertise_by_category[category]
            category_strengths: list[float] = []
            evidence_target = cls.KG_EVIDENCE_TARGETS[category]

            for requested_value in requested_values:
                evidence_count = category_counts.get(requested_value, 0)
                if evidence_count <= 0:
                    continue

                match_strength = min(1.0, evidence_count / evidence_target)
                category_strengths.append(match_strength)
                matches.append(
                    KGMatchInfo(
                        category=category,
                        value=requested_value,
                        evidence_count=evidence_count,
                        match_strength=match_strength,
                    )
                )

            if not category_strengths:
                continue

            coverage = len(category_strengths) / len(requested_values)
            average_strength = sum(category_strengths) / len(category_strengths)
            weighted_alignment += weight * coverage * average_strength

        if applicable_weight == 0 or weighted_alignment == 0.0:
            return 0.0, []

        history_confidence = min(
            1.0, expertise_summary.pr_count / cls.KG_HISTORY_TARGET
        )
        normalized_alignment = weighted_alignment / applicable_weight
        score = normalized_alignment * history_confidence * cls.KG_MAX_SCORE

        matches.sort(
            key=lambda match: (match.match_strength, match.evidence_count),
            reverse=True,
        )
        return float(score), matches[:6]

    @classmethod
    def _aggregate_similarity_score(cls, similarities: list[float]) -> float:
        """Aggregate PR similarities into a final score with confidence weighting."""
        if not similarities:
            return 0.0

        sorted_similarities = sorted(similarities, reverse=True)
        relevant_similarities = [
            sim for sim in sorted_similarities if sim >= cls.MIN_RELEVANT_SIMILARITY
        ]

        # If none of a developer's PRs are relevant enough, exclude them from ranking.
        if not relevant_similarities:
            return 0.0

        top_relevant = relevant_similarities[: cls.MAX_SCORING_PRS]
        weights = [1.0 / (idx + 1) for idx, _ in enumerate(top_relevant)]
        weighted_similarity = sum(
            sim * weight for sim, weight in zip(top_relevant, weights, strict=False)
        ) / sum(weights)

        # Penalize sparse history so one accidental match is not over-ranked.
        relevance_confidence = min(1.0, len(top_relevant) / cls.RELEVANT_PR_TARGET)
        history_confidence = min(1.0, len(sorted_similarities) / cls.HISTORY_PR_TARGET)
        confidence = float((relevance_confidence * history_confidence) ** 0.5)

        return float(weighted_similarity) * confidence * 1000.0

    def _calculate_developer_github_score(
        self, github_id: int, task_embedding: list[float], threshold: int
    ) -> tuple[float, list[PrScoreInfo]]:
        """
        Calculate a similarity-based score for a GitHub user.
        Returns the average cosine similarity (%) across up to `threshold` PRs.
        """
        github_filter = cast(Any, GitHubPRVector.author_id == github_id)
        prs = (
            self.db.query(GitHubPRVector)
            .filter(github_filter)
            .order_by(GitHubPRVector.embedding.cosine_distance(task_embedding))
            .limit(threshold)
            .all()
        )

        if not prs:
            return 0.0, []

        task_tensor = torch.tensor(task_embedding, dtype=torch.float)
        similarities: list[float] = []
        pr_matches: list[PrScoreInfo] = []
        for pr in prs:
            if pr.embedding is None:
                continue
            pr_tensor = torch.tensor(pr.embedding, dtype=torch.float)
            # Use dim=0 since vectors are 1-D
            sim = cosine_similarity(task_tensor, pr_tensor, dim=0)
            sim_value = float(sim.item())
            similarities.append(sim_value)

            pr_matches.append(
                PrScoreInfo(
                    pr_id=pr.pr_id,
                    pr_title=pr.pr_title,
                    pr_url=pr.pr_url,
                    pr_description=pr.pr_description,
                    match_percentage=sim_value * 100.0,
                )
            )

        if not similarities:
            return 0.0, []
        final_score = self._aggregate_similarity_score(similarities)
        pr_matches.sort(key=lambda x: x.match_percentage, reverse=True)

        return final_score, pr_matches[:3]

    @staticmethod
    def _extract_summary_from_context(context: str) -> str:
        """Extract the SUMMARY field from a Jira issue context string."""
        for line in context.splitlines():
            if line.startswith("SUMMARY: "):
                return line[len("SUMMARY: "):]
        return ""

    def _calculate_developer_jira_score(
        self, jira_account_id: str, task_embedding: list[float], threshold: int
    ) -> tuple[float, list[IssueScoreInfo]]:
        """
        Calculate a similarity-based score for a Jira user.
        Returns the aggregated score and top matching issues.
        """
        jira_filter = cast(Any, JiraIssueVector.assignee_account_id == jira_account_id)
        issues = (
            self.db.query(JiraIssueVector)
            .filter(jira_filter)
            .order_by(JiraIssueVector.embedding.cosine_distance(task_embedding))
            .limit(threshold)
            .all()
        )

        if not issues:
            return 0.0, []

        jira_base_url = (settings.JIRA_URL or "").rstrip("/")
        task_tensor = torch.tensor(task_embedding, dtype=torch.float)
        similarities: list[float] = []
        issue_matches: list[IssueScoreInfo] = []
        for issue in issues:
            if issue.embedding is None:
                continue
            issue_tensor = torch.tensor(issue.embedding, dtype=torch.float)
            sim = cosine_similarity(task_tensor, issue_tensor, dim=0)
            sim_value = float(sim.item())
            similarities.append(sim_value)

            issue_matches.append(
                IssueScoreInfo(
                    issue_key=issue.issue_key,
                    issue_summary=self._extract_summary_from_context(
                        issue.context or ""
                    ),
                    issue_url=f"{jira_base_url}/browse/{issue.issue_key}"
                    if jira_base_url
                    else "",
                    match_percentage=sim_value * 100.0,
                )
            )

        if not similarities:
            return 0.0, []
        final_score = self._aggregate_similarity_score(similarities)
        issue_matches.sort(key=lambda x: x.match_percentage, reverse=True)

        return final_score, issue_matches[:3]

    def _calculate_developer_knowledge_graph_score(
        self, github_id: int, task_entities: ExtractedEntities
    ) -> tuple[float, list[KGMatchInfo]]:
        if self.kg_service is None or self._disable_kg_scoring:
            return 0.0, []

        expertise_summary = self.kg_service.get_resource_expertise_summary(github_id)
        return self._score_knowledge_graph_alignment(task_entities, expertise_summary)

    def get_best_fits(self, best_fit_input: BestFitInput) -> list[ScoreProfile]:
        """
        Get the top N Resources best suited for the given task.
        Scores each profile using GitHub PRs, Jira issues, and knowledge graph alignment.
        """
        task = f"{best_fit_input.task_title}\n\n{best_fit_input.task_description}"
        top_n = best_fit_input.max_results
        profiles = self.db.query(ResourceProfile).all()

        if not profiles:
            return []

        embedding_service = VectorEmbeddingService(self.db)

        task_embedding = embedding_service.generate_embeddings(
            [task],
            prompt_name=settings.GITHUB_QUERY_PROMPT_NAME,
        )[0]

        task_entities = self._extract_task_entities(best_fit_input)
        logger.info("Score task entities extracted: %s", task_entities.to_dict())

        scores: list[ScoreProfile] = []
        for profile in profiles:
            if not profile.github_id and not profile.jira_account_id:
                continue

            stmt = select(User.full_name).where(User.id == profile.user_id)
            user_name = self.db.execute(stmt).scalar() or "Unknown"
            score_profile = ScoreProfile(
                user_id=profile.user_id, user_name=user_name, position=profile.position
            )

            try:
                if profile.github_id:
                    github_pr_score, top_prs = (
                        self._calculate_developer_github_score(
                            github_id=profile.github_id,
                            task_embedding=task_embedding,
                            threshold=50,
                        )
                    )
                    score_profile.github_pr_score = github_pr_score
                    score_profile.pr_info = top_prs

                    if not self._disable_kg_scoring and not task_entities.is_empty():
                        try:
                            kg_score, kg_matches = (
                                self._calculate_developer_knowledge_graph_score(
                                    github_id=profile.github_id,
                                    task_entities=task_entities,
                                )
                            )
                            score_profile.knowledge_graph_score = kg_score
                            score_profile.kg_matches = kg_matches
                        except Exception:
                            logger.warning(
                                "Knowledge graph scoring disabled for this request.",
                                exc_info=True,
                            )
                            self._disable_kg_scoring = True

                if profile.jira_account_id:
                    jira_issue_score, top_issues = (
                        self._calculate_developer_jira_score(
                            jira_account_id=profile.jira_account_id,
                            task_embedding=task_embedding,
                            threshold=50,
                        )
                    )
                    score_profile.jira_issue_score = jira_issue_score
                    score_profile.issue_info = top_issues

                scores.append(score_profile)
            except Exception as e:
                logger.error(
                    f"Error calculating scores for user_id {profile.user_id}: {e}"
                )
                continue

        scores.sort(key=lambda x: x.total_score, reverse=True)
        return scores[:top_n]
