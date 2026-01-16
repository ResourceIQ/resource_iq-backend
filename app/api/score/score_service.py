import logging

import torch
from torch import cosine_similarity

from app.api.embedding.embedding_model import GitHubPRVector
from app.api.embedding.embedding_service import VectorEmbeddingService
from app.api.profiles.profile_model import ResourceProfile
from app.utils.deps import SessionDep

logger = logging.getLogger(__name__)

class ScoreService:
    def __init__(self, db: SessionDep):
        self.db = db

    def _calculate_developer_github_score(self, github_id: int, task_tensor: torch.Tensor, threshold: int) -> float:
        """
        Calculate a similarity-based score for a GitHub user.
        Returns the average cosine similarity (%) across up to `threshold` PRs.
        """
        prs = (
            self.db.query(GitHubPRVector)
            .filter(GitHubPRVector.author_id == github_id)
            .order_by(GitHubPRVector.pr_id.desc())
            .limit(threshold)
            .all()
        )

        similarities = []
        for pr in prs:
            if pr.embedding is None:
                continue
            pr_tensor = torch.tensor(pr.embedding, dtype=torch.float)
            # Use dim=0 since vectors are 1-D
            sim = cosine_similarity(task_tensor, pr_tensor, dim=0)
            similarities.append(sim)

        if not similarities:
            return 0.0

        # Average similarity scaled to percentage
        return float(torch.stack(similarities).mean().item() * 1000)

    def get_best_fits(self, task: str, top_n: int) -> list[tuple[int, float]]:
        """
        Get the top N Resources best suited for the given task.
        Returns a list of tuples (user_id, score).
        """
        # Get all profiles
        profiles = (
            self.db.query(ResourceProfile)
            .all()
        )

        if not profiles:
            return []

        # Generate task embedding
        embedding_service = VectorEmbeddingService(self.db)
        task_embedding = embedding_service.generate_embeddings([task])[0]
        task_tensor = torch.tensor(task_embedding, dtype=torch.float)

        # Calculate scores for each profile
        scores: list[tuple[int, float]] = []
        for profile in profiles:
            if not profile.github_id:
                continue
            try:
                score = self._calculate_developer_github_score(
                    github_id=profile.github_id,
                    task_tensor=task_tensor,
                    threshold=50,  # Consider up to 50 most recent PRs
                )
                scores.append((profile.user_id, score))
            except Exception as e:
                # Log error but continue with next profile
                logger.error(f"Error calculating score for user_id {profile.user_id}: {e}")
                continue

        # Sort by score descending and return top N
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_n]
