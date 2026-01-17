from fastapi import APIRouter, HTTPException, Query

from app.api.score.score_schema import ScoreProfile
from app.api.score.score_service import ScoreService
from app.utils.deps import SessionDep

router = APIRouter(prefix="/score", tags=["score"])


@router.get("/best-fits")
def get_best_fits(
    db: SessionDep,
    task: str = Query(..., description="Task description to find best fits for"),
    top_n: int = Query(5, description="Number of top developers to return"),
) -> list[ScoreProfile]:
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
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
