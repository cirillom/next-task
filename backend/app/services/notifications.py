"""Due-date and timed-unblock notification scheduling, deduplication, and delivery."""

import os
from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.i18n import Language, localized, translate
from app.models import Notification, PushSubscription, Task, TaskBlock, User
from app.services.tasks import (
    block_is_active,
    descendant_tasks,
    normalize_utc,
    unfinished_descendant_count,
)
from app.services.webpush import send_web_push, vapid_config


def validate_timezone(value: str) -> str:
    cleaned = value.strip()
    if not cleaned or len(cleaned) > 64:
        raise ValueError(localized("api.invalidTimeZone"))
    try:
        ZoneInfo(cleaned)
    except (ZoneInfoNotFoundError, KeyError, ValueError) as error:
        raise ValueError(localized("api.invalidTimeZone")) from error
    return cleaned


def effective_timezone(tz_name: str | None) -> ZoneInfo:
    for candidate in (tz_name, os.environ.get("TZ"), "UTC"):
        if not candidate:
            continue
        try:
            return ZoneInfo(candidate)
        except (ZoneInfoNotFoundError, KeyError, ValueError):
            continue
    return ZoneInfo("UTC")


def task_is_actionable(task: Task, now: datetime) -> bool:
    return (
        task.priority > 0
        and task.finished_at is None
        and task.abandoned_by_task_id is None
        and not any(block_is_active(block, now) for block in task.blocks)
        and unfinished_descendant_count(task) == 0
    )


def was_blocked_at(task: Task, instant: datetime) -> bool:
    return any(
        normalize_utc(block.blocked_at) <= instant
        and (block.unblocked_at is None or normalize_utc(block.unblocked_at) > instant)
        for block in task.blocks
    )


def _was_abandoned_at(candidate: Task, instant: datetime, root_id: int) -> bool:
    current: Task | None = candidate
    while current is not None and current.id != root_id:
        if current.abandoned_at is not None and normalize_utc(current.abandoned_at) <= instant:
            return True
        current = current.parent
    return False


def had_unfinished_descendant_at(task: Task, instant: datetime) -> bool:
    return any(
        normalize_utc(descendant.created_at) <= instant
        and (descendant.finished_at is None or normalize_utc(descendant.finished_at) > instant)
        and not _was_abandoned_at(descendant, instant, task.id)
        for descendant in descendant_tasks(task)
    )


def _unblocked_kind(task: Task, local_today: date) -> str:
    if task.due_date is None:
        return "unblocked"
    if task.due_date < local_today:
        return "unblocked_overdue"
    if task.due_date == local_today:
        return "unblocked_due"
    return "unblocked"


def record_dependency_unblock_notification(
    db: Session,
    user_id: int,
    action: str,
    blocker_id: int,
    candidate_task_ids: list[int],
    now: datetime,
) -> None:
    unique_ids = sorted(set(candidate_task_ids))
    if not unique_ids:
        return
    # Expire identity-map collections so flushed updates are visible to eligibility checks.
    db.flush()
    db.expire_all()
    user = db.get(User, user_id)
    if user is None:
        return
    candidates = list(
        db.scalars(
            select(Task)
            .where(Task.user_id == user_id, Task.id.in_(unique_ids))
            .order_by(Task.id)
        )
        .unique()
        .all()
    )
    ready = [task for task in candidates if task_is_actionable(task, now)]
    if not ready:
        return
    local_today = now.astimezone(effective_timezone(user.notification_timezone)).date()
    kind = _unblocked_kind(ready[0], local_today) if len(ready) == 1 else "unblocked"
    db.add(
        Notification(
            user_id=user_id,
            task_id=ready[0].id,
            kind=kind,
            dedup_key=f"dep:{action}:{blocker_id}:{now.isoformat()}",
            task_title=ready[0].title,
            extra_count=len(ready) - 1,
            created_at=now,
        )
    )


def build_push_payload(
    kind: str,
    task_id: int,
    task_title: str,
    language: Language,
    dedup_key: str,
) -> dict[str, str]:
    if kind == "due":
        title = translate("notification.dueTitle", language)
        body = translate("notification.dueBody", language, title=task_title)
    else:
        title = translate("notification.unblockedTitle", language)
        body_key = {
            "unblocked_due": "notification.unblockedDueBody",
            "unblocked_overdue": "notification.unblockedOverdueBody",
        }.get(kind, "notification.unblockedBody")
        body = translate(body_key, language, title=task_title)
    return {"title": title, "body": body, "url": f"/#/tasks?task={task_id}", "tag": dedup_key}


def claim_and_send(
    db: Session,
    user: User,
    *,
    task_id: int,
    task_title: str,
    kind: str,
    dedup_key: str,
    trigger_utc: datetime,
    now: datetime,
) -> bool:
    inserted_id = db.scalar(
        sqlite_insert(Notification)
        .values(
            user_id=user.id,
            task_id=task_id,
            kind=kind,
            dedup_key=dedup_key,
            task_title=task_title,
            extra_count=0,
            created_at=now,
        )
        .on_conflict_do_nothing(index_elements=["user_id", "dedup_key"])
        .returning(Notification.id)
    )
    db.commit()
    if inserted_id is None:
        return False

    subs = list(
        db.scalars(select(PushSubscription).where(PushSubscription.user_id == user.id)).all()
    )
    eligible = [sub for sub in subs if normalize_utc(sub.created_at) <= trigger_utc]
    if eligible and vapid_config() is not None:
        payload = build_push_payload(kind, task_id, task_title, user.language, dedup_key)
        expired_ids = [
            sub.id
            for sub in eligible
            if send_web_push(sub.endpoint, sub.p256dh, sub.auth, payload) == "expired"
        ]
        if expired_ids:
            db.execute(delete(PushSubscription).where(PushSubscription.id.in_(expired_ids)))
            db.commit()
    return True


def run_notifier_once(db: Session, now: datetime | None = None) -> int:
    current = normalize_utc(now or datetime.now(UTC))
    sent_count = 0

    for user in db.scalars(select(User)).all():
        tz = effective_timezone(user.notification_timezone)
        local_today = current.astimezone(tz).date()
        trigger_utc = datetime.combine(
            local_today, time(9, 0, fold=0), tzinfo=tz
        ).astimezone(UTC)
        if current < trigger_utc:
            continue
        due_tasks = list(
            db.scalars(
                select(Task).where(
                    Task.user_id == user.id,
                    Task.priority > 0,
                    Task.finished_at.is_(None),
                    Task.abandoned_at.is_(None),
                    Task.due_date == local_today,
                )
            )
            .unique()
            .all()
        )
        for task in due_tasks:
            if not task_is_actionable(task, current) or was_blocked_at(task, trigger_utc):
                continue
            if claim_and_send(
                db,
                user,
                task_id=task.id,
                task_title=task.title,
                kind="due",
                dedup_key=f"due:{task.id}:{local_today.isoformat()}",
                trigger_utc=trigger_utc,
                now=current,
            ):
                sent_count += 1

    blocks = list(
        db.scalars(
            select(TaskBlock)
            .join(Task, TaskBlock.task_id == Task.id)
            .where(
                TaskBlock.auto_unblock.is_(True),
                TaskBlock.unblocked_at.is_not(None),
                TaskBlock.unblocked_at <= current,
                Task.priority > 0,
                Task.finished_at.is_(None),
                Task.abandoned_at.is_(None),
            )
            .order_by(TaskBlock.unblocked_at, TaskBlock.id)
        )
        .unique()
        .all()
    )
    for block in blocks:
        if block.unblocked_at is None:
            continue
        b_end = normalize_utc(block.unblocked_at)
        if b_end > current:
            continue
        task = block.task
        if not task_is_actionable(task, current):
            continue
        if any(
            other.id != block.id
            and (other.unblocked_at is None or normalize_utc(other.unblocked_at) > b_end)
            for other in task.blocks
        ):
            continue
        if had_unfinished_descendant_at(task, b_end):
            continue
        user = task.user
        local_today = current.astimezone(effective_timezone(user.notification_timezone)).date()
        kind = _unblocked_kind(task, local_today)
        if claim_and_send(
            db,
            user,
            task_id=task.id,
            task_title=task.title,
            kind=kind,
            dedup_key=f"timed:{task.id}:{b_end.isoformat()}",
            trigger_utc=b_end,
            now=current,
        ):
            sent_count += 1

    return sent_count
