import logging
import uuid
from typing import Any, cast

import torch
from sqlalchemy.orm import Session
from sqlmodel import select
from torch import cosine_similarity

from app.api.embedding.embedding_model import GitHubPRVector, JiraIssueVector
from app.api.embedding.embedding_service import VectorEmbeddingService
from app.api.integrations.Jira.jira_model import JiraOAuthToken, JiraOrgIntegration
from app.api.integrations.Jira.jira_service import JiraIntegrationService
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
    MIN_RELEVANT_SIMILARITY = 0.30
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
        # If explicit entities are provided, use them; else extract from text
        if any(
            [
                best_fit_input.skills,
                best_fit_input.domains,
                best_fit_input.tools,
                best_fit_input.languages,
            ]
        ):
            return ExtractedEntities(
                skills=best_fit_input.skills or [],
                domains=best_fit_input.domains or [],
                tools=best_fit_input.tools or [],
                languages=best_fit_input.languages or [],
                frameworks=best_fit_input.frameworks or [],
            )
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
        pr_matches = [
            pr
            for pr in pr_matches
            if pr.match_percentage / 100.0 >= self.MIN_RELEVANT_SIMILARITY
        ]
        pr_matches.sort(key=lambda x: x.match_percentage, reverse=True)

        return final_score, pr_matches[:3]

    def _resolve_jira_browse_url(self) -> str:
        """Resolve the browsable Jira site URL from OAuth token, org integration, or settings."""
        token: JiraOAuthToken | None = self.db.query(JiraOAuthToken).first()
        if token and token.jira_site_url:
            return str(token.jira_site_url).rstrip("/")

        integration: JiraOrgIntegration | None = self.db.query(
            JiraOrgIntegration
        ).first()
        if integration and integration.jira_url:
            return str(integration.jira_url).rstrip("/")

        return (settings.JIRA_URL or "").rstrip("/")

    @staticmethod
    def _extract_summary_from_context(context: str) -> str:
        """Extract the SUMMARY field from a Jira issue context string."""
        for line in context.splitlines():
            if line.startswith("SUMMARY: "):
                return line[len("SUMMARY: ") :]
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

        jira_base_url = self._resolve_jira_browse_url()

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
        issue_matches = [
            issue
            for issue in issue_matches
            if issue.match_percentage / 100.0 >= self.MIN_RELEVANT_SIMILARITY
        ]
        issue_matches.sort(key=lambda x: x.match_percentage, reverse=True)

        return final_score, issue_matches[:3]

    def _calculate_developer_knowledge_graph_score(
        self,
        user_id: uuid.UUID,
        github_id: int | None,
        task_entities: ExtractedEntities,
    ) -> tuple[float, list[KGMatchInfo]]:
        if self.kg_service is None or self._disable_kg_scoring:
            return 0.0, []

        expertise_summary = self.kg_service.get_resource_expertise_summary(
            user_id=str(user_id),
            github_id=github_id,
        )
        return self._score_knowledge_graph_alignment(task_entities, expertise_summary)

    def _get_realtime_jira_workload_map(
        self, profiles: list[ResourceProfile]
    ) -> dict[str, int]:
        """Fetch live Jira workload counts keyed by Jira account id."""
        jira_account_ids = [
            profile.jira_account_id for profile in profiles if profile.jira_account_id
        ]
        if not jira_account_ids:
            return {}

        try:
            jira_service = JiraIntegrationService(self.db)
            return jira_service.get_live_assignee_workload_map(jira_account_ids)
        except Exception:
            logger.warning(
                "Failed to fetch live Jira workload map for scoring.",
                exc_info=True,
            )
            return {}

    def get_best_fits(self, best_fit_input: BestFitInput) -> list[ScoreProfile]:
        """
        Get the top N Resources best suited for the given task.
        Scores each profile using GitHub PRs, Jira issues, knowledge graph alignment,
        and explicit "wants to learn" and "has experience" nodes.
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
        live_jira_workload_by_account = self._get_realtime_jira_workload_map(profiles)

        # Normalize task entities for matching
        task_entities_by_category = {
            "domains": self._normalize_entity_values(task_entities.domains),
            "skills": self._normalize_entity_values(task_entities.skills),
            "languages": self._normalize_entity_values(task_entities.languages),
            "frameworks": self._normalize_entity_values(task_entities.frameworks),
            "tools": self._normalize_entity_values(task_entities.tools),
        }

        # Bonus weights
        EXPERIENCE_BONUS_BASE = 20.0  # Multiplied by (experience_level / 10)
        # Flat bonus per technology the developer has expressed intent to learn
        # that matches a task requirement. Smaller than max experience bonus to
        # reward motivation without overstating readiness.
        WANTS_TO_LEARN_BONUS = 15.0

        scores: list[ScoreProfile] = []
        for profile in profiles:
            if not profile.github_id and not profile.jira_account_id:
                continue

            stmt = select(User.full_name).where(User.id == profile.user_id)
            user_name = self.db.execute(stmt).scalar() or "Unknown"
            score_profile = ScoreProfile(
                user_id=profile.user_id,
                user_name=user_name,
                position=profile.position.name if profile.position else None,
            )
            live_jira_workload = 0
            if profile.jira_account_id:
                live_jira_workload = live_jira_workload_by_account.get(
                    profile.jira_account_id, 0
                )

            # Burnout penalty uses live Jira workload only.
            active_tasks = live_jira_workload
            burnout_level = getattr(profile, "burnout_level", 0.0) or 0.0
            burnout_penalty = (
                burnout_level * active_tasks * 10.0
            )  # Tunable factor to scale the penalty
            if burnout_level == 0:
                burnout_penalty = active_tasks * 100.0
            score_profile.live_jira_workload = live_jira_workload
            score_profile.burnout_penalty = burnout_penalty

            try:
                # --- GitHub PR score ---
                if profile.github_id:
                    github_pr_score, top_prs = self._calculate_developer_github_score(
                        github_id=profile.github_id,
                        task_embedding=task_embedding,
                        threshold=30,
                    )
                    # Increase GitHub PR score weight
                    score_profile.github_pr_score = github_pr_score * 1.5
                    score_profile.pr_info = top_prs

                # --- Knowledge Graph score (existing alignment) ---
                kg_score = 0.0
                kg_matches: list[KGMatchInfo] = []
                if (
                    profile.github_id
                    and not self._disable_kg_scoring
                    and not task_entities.is_empty()
                ):
                    try:
                        kg_score, kg_matches = (
                            self._calculate_developer_knowledge_graph_score(
                                user_id=profile.user_id,
                                github_id=profile.github_id,
                                task_entities=task_entities,
                            )
                        )
                    except Exception:
                        logger.warning(
                            "Knowledge graph scoring disabled for this request.",
                            exc_info=True,
                        )
                        self._disable_kg_scoring = True

                # --- New: Wants to Learn & Experience Bonus + Matched Node Details ---
                wants_learn_bonus = 0.0
                experience_bonus = 0.0
                experience_profile = None
                match_details: dict[str, Any] = {
                    "experience_matches": {},  # category -> list of {name, experience_level}
                    "wants_to_learn_matches": {},  # category -> list of names
                }
                if self.kg_service is not None and profile.github_id:
                    try:
                        experience_profile = self.kg_service.get_resource_experience(
                            github_id=profile.github_id,
                            user_id=str(profile.user_id),
                        )
                    except Exception as e:
                        logger.warning(
                            f"Failed to fetch experience for user {profile.user_id}: {e}"
                        )

                learning_intent = None
                if self.kg_service is not None and profile.github_id:
                    try:
                        learning_intent = self.kg_service.get_resource_learning_intent(
                            github_id=profile.github_id,
                            user_id=str(profile.user_id),
                        )
                    except Exception as e:
                        logger.warning(
                            f"Failed to fetch learning intent for user {profile.user_id}: {e}"
                        )

                if experience_profile:
                    for category in [
                        "domains",
                        "skills",
                        "languages",
                        "frameworks",
                        "tools",
                    ]:
                        task_values = set(task_entities_by_category[category])
                        experience_items = getattr(experience_profile, category, [])
                        matched_exp = []
                        for item in experience_items:
                            if item.name.strip().lower() in task_values:
                                experience_bonus += EXPERIENCE_BONUS_BASE * (
                                    item.experience_level / 10.0
                                )
                                matched_exp.append(
                                    {
                                        "name": item.name,
                                        "experience_level": item.experience_level,
                                    }
                                )
                        if matched_exp:
                            match_details["experience_matches"][category] = matched_exp

                # Wants-to-learn bonus: developer has signalled intent to grow into a
                # technology the task requires — reward motivation at a flat rate.
                _LEARNING_INTENT_FIELDS: dict[str, str] = {
                    "domains": "wants_to_work_in_domains",
                    "skills": "wants_to_learn_skills",
                    "languages": "wants_to_learn_languages",
                    "frameworks": "wants_to_learn_frameworks",
                    "tools": "wants_to_learn_tools",
                }
                if learning_intent:
                    for category, intent_field in _LEARNING_INTENT_FIELDS.items():
                        task_values = set(task_entities_by_category[category])
                        intent_values = [
                            v.strip().lower()
                            for v in getattr(learning_intent, intent_field, [])
                        ]
                        matched_learn = [v for v in intent_values if v in task_values]
                        wants_learn_bonus += len(matched_learn) * WANTS_TO_LEARN_BONUS
                        if matched_learn:
                            match_details["wants_to_learn_matches"][category] = (
                                matched_learn
                            )

                score_profile.knowledge_graph_score = (
                    kg_score + wants_learn_bonus + experience_bonus
                )
                score_profile.kg_matches = kg_matches
                score_profile.kg_match_details = match_details

                # --- Jira Issue Score ---
                if profile.jira_account_id:
                    jira_issue_score, top_issues = self._calculate_developer_jira_score(
                        jira_account_id=profile.jira_account_id,
                        task_embedding=task_embedding,
                        threshold=30,
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

    def get_job_positions(self) -> list[str]:
        """Fetch all unique job position names."""
        from app.api.profiles.position_model import JobPosition

        query = select(JobPosition.name)
        raw_results = self.db.execute(query)
        clean_list = raw_results.scalars().all()
        return list(clean_list)
