from fastapi import APIRouter, HTTPException

from app.api.score.score_schema import BestFitInput, ScoreProfile
from app.api.score.score_service import ScoreService
from app.utils.deps import SessionDep

router = APIRouter(prefix="/score", tags=["score"])


@router.post("/best-fits")
def get_best_fits(
    db: SessionDep,
    best_fit_input: BestFitInput,
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
        results = score_service.get_best_fits(best_fit_input=best_fit_input)
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
