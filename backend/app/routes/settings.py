from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.security import get_current_user
from app.database import get_db
from app.models import TaskStatus, User
from app.schemas import ScoringSettings, StatusCreate, StatusRead, StatusUpdate
from app.services.scoring import DEFAULT_SCORING_FORMULA, FormulaError, validate_formula

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
    user.scoring_formula = payload.scoring_formula
    db.commit()
    return payload


@router.get("/api/statuses", response_model=list[StatusRead])
def list_statuses(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[TaskStatus]:
    return list(
        db.scalars(
            select(TaskStatus).where(TaskStatus.user_id == user.id).order_by(TaskStatus.id)
        ).all()
    )


@router.post("/api/statuses", response_model=StatusRead, status_code=201)
def create_status(
    payload: StatusCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TaskStatus:
    item = TaskStatus(user_id=user.id, **payload.model_dump())
    db.add(item)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="Status name already exists") from error
    db.refresh(item)
    return item


def _status(db: Session, status_id: int, user_id: int) -> TaskStatus:
    item = db.get(TaskStatus, status_id)
    if item is None or item.user_id != user_id:
        raise HTTPException(status_code=404, detail="Status not found")
    return item


@router.patch("/api/statuses/{status_id}", response_model=StatusRead)
def update_status(
    status_id: int,
    payload: StatusUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TaskStatus:
    item = _status(db, status_id, user.id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, key, value)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="Status name already exists") from error
    return item


@router.delete("/api/statuses/{status_id}", status_code=204)
def delete_status(
    status_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    db.delete(_status(db, status_id, user.id))
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="Status is in use") from error
    return Response(status_code=204)
