from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import get_current_user
from app.database import get_db
from app.models import Task, User
from app.schemas import ScoringSettings
from app.services.scoring import (
    DEFAULT_SCORING_FORMULA,
    FormulaError,
    evaluate_formula,
    score_variables,
    validate_formula,
)

router = APIRouter(tags=["settings"])


@router.get("/api/settings/scoring", response_model=ScoringSettings)
def get_scoring_settings(user: User = Depends(get_current_user)) -> ScoringSettings:
    return ScoringSettings(scoring_formula=user.scoring_formula or DEFAULT_SCORING_FORMULA)


@router.put("/api/settings/scoring", response_model=ScoringSettings)
def update_scoring_settings(
    payload: ScoringSettings,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ScoringSettings:
    try:
        validate_formula(payload.scoring_formula)
    except FormulaError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    tasks = db.scalars(
        select(Task).where(
            Task.user_id == user.id,
            Task.priority > 0,
            Task.finished_at.is_(None),
        )
    ).all()
    now = datetime.now(UTC)
    for task in tasks:
        try:
            evaluate_formula(payload.scoring_formula, score_variables(task, now))
        except FormulaError as error:
            raise HTTPException(
                status_code=422,
                detail=f"Formula cannot score task #{task.id}: {error}",
            ) from error
    user.scoring_formula = payload.scoring_formula
    db.commit()
    return payload
