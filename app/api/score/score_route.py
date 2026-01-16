from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.api.score.score_service import ScoreService
from app.utils.deps import SessionDep

router = APIRouter(prefix="/score", tags=["score"])


@router.get("/calculate/{github_id}")
def calculate_developer_score(
    github_id: int,
    task: str = Query(..., description="Task description to score against"),
    threshold: int = Query(50, description="Number of PRs to consider"),
    db: SessionDep = None,
) -> dict[str, Any]:
    """
    Calculate a similarity-based score for a GitHub developer   
    Args:
        github_id: GitHub user ID
        task: Task description to compare against developer's PR history
        threshold: Maximum number of PRs to consider (default: 50)

    Returns:
        Score (0-100 percentage) based on average cosine similarity
    """
    try:
        score_service = ScoreService(db)
        score = score_service._calculate_developer_github_score(
            github_id=github_id,
            task=task,
            threshold=threshold,
        )
        return {"github_id": github_id, "score": score, "task": task}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/best-fits")
def get_best_fits(
    task: str = Query(..., description="Task description to find best fits for"),
    top_n: int = Query(5, description="Number of top developers to return"),
    db: SessionDep = None,
) -> dict[str, Any]:
    """
    Get the top N resource profiles best suited for a given task.
    Searches across all resource profiles with connected GitHub profiles and ranks them
    by similarity to the task description based on their PR history.
    Args:
        task: Task description to find best fits for
        top_n: Number of top resource profiles to return (default: 5)
    Returns:
        List of tuples (user_id, score) sorted by score descending
    """
    try:
        score_service = ScoreService(db)
        results = score_service.get_best_fits(task=task, top_n=top_n)
        formatted_results = [
            {"user_id": user_id, "score": score}
            for user_id, score in results
        ]
        return {
            "task": task,
            "top_n": top_n,
            "results": formatted_results,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
