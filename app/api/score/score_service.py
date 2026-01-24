import logging
from typing import Any, cast

import torch
from sqlalchemy.orm import Session
from sqlmodel import select
from torch import cosine_similarity

from app.api.embedding.embedding_model import GitHubPRVector
from app.api.embedding.embedding_service import VectorEmbeddingService
from app.api.profiles.profile_model import ResourceProfile
from app.api.score.score_schema import BestFitInput, PrScoreInfo, ScoreProfile
from app.api.user.user_model import User

logger = logging.getLogger(__name__)


class ScoreService:
    def __init__(self, db: Session) -> None:
        self.db = db

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
        similarities = []
        pr_matches: list[PrScoreInfo] = []
        for pr in prs:
            if pr.embedding is None:
                continue
            pr_tensor = torch.tensor(pr.embedding, dtype=torch.float)
            # Use dim=0 since vectors are 1-D
            sim = cosine_similarity(task_tensor, pr_tensor, dim=0)
            similarities.append(sim)

            pr_matches.append(
                PrScoreInfo(
                    pr_title=pr.pr_title,
                    pr_url=pr.pr_url,
                    match_percentage=sim * 100.0,
                )
            )

        if not similarities:
            return 0.0, []
        final_score = float(torch.stack(similarities).mean().item() * 1000)
        pr_matches.sort(key=lambda x: x.match_percentage, reverse=True)

        return final_score, pr_matches[:3]

    def get_best_fits(self, best_fit_input: BestFitInput) -> list[ScoreProfile]:
        """
        Get the top N Resources best suited for the given task.
        Returns a list of tuples (user_id, score).
        """
        task = f"{best_fit_input.task_title}\n\n{best_fit_input.task_description}"
        top_n = best_fit_input.max_results
        # Get all profiles
        profiles = self.db.query(ResourceProfile).all()

        if not profiles:
            return []

        # Generate task embedding
        embedding_service = VectorEmbeddingService(self.db)
        task_embedding = embedding_service.generate_embeddings([task])[0]

        # Calculate scores for each profile
        scores: list[ScoreProfile] = []
        for profile in profiles:
            stmt = select(User.full_name).where(User.id == profile.user_id)
            user_name = self.db.execute(stmt).scalar() or "Unknown"
            score_profile = ScoreProfile(user_id=profile.user_id, user_name=user_name)
            if not profile.github_id:
                continue
            try:
                github_pr_score, top_prs = self._calculate_developer_github_score(
                    github_id=profile.github_id,
                    task_embedding=task_embedding,
                    threshold=50,  # Consider up to 50 most recent PRs
                )
                score_profile.github_pr_score = github_pr_score
                score_profile.pr_info = top_prs
                scores.append(score_profile)
            except Exception as e:
                # Log error but continue with next profile
                logger.error(
                    f"Error calculating github_pr_score for user_id {profile.user_id}: {e}"
                )
                continue

        # Sort by score descending and return top N
        scores.sort(key=lambda x: x.total_score, reverse=True)
        return scores[:top_n]
