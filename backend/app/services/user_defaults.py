from sqlalchemy.orm import Session

from app.models import TaskStatus, User


def add_default_statuses(db: Session, user: User) -> None:
    db.flush()
    db.add_all(
        [
            TaskStatus(user_id=user.id, name="todo", score_value=0),
            TaskStatus(user_id=user.id, name="doing", score_value=1),
        ]
    )
