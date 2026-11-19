import hashlib
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.auth.security import get_current_user
from app.database import get_db
from app.i18n import error_detail, localized, translate
from app.models import Notification, PushSubscription, User
from app.schemas import (
    Message,
    NotificationListRead,
    NotificationPreferencesUpdate,
    NotificationRead,
    NotificationSettingsRead,
    NotificationsReadRequest,
    NotificationTestRequest,
    PushSubscriptionCreate,
    PushUnsubscribeRequest,
    UnreadCountRead,
)
from app.services.webpush import (
    send_web_push,
    validate_push_endpoint,
    validate_subscription_keys,
    vapid_config,
)

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def _settings_read(db: Session, user: User) -> NotificationSettingsRead:
    config = vapid_config()
    subs = list(
        db.scalars(
            select(PushSubscription)
            .where(PushSubscription.user_id == user.id)
            .order_by(PushSubscription.id)
        ).all()
    )
    return NotificationSettingsRead(
        push_configured=config is not None,
        vapid_public_key=config[1] if config is not None else None,
        timezone=user.notification_timezone,
        subscription_count=len(subs),
        endpoint_hashes=[
            hashlib.sha256(sub.endpoint.encode("utf-8")).hexdigest() for sub in subs
        ],
    )


@router.get("/settings", response_model=NotificationSettingsRead)
def get_notification_settings(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> NotificationSettingsRead:
    return _settings_read(db, user)


@router.put("/settings", response_model=NotificationSettingsRead)
def update_notification_settings(
    payload: NotificationPreferencesUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> NotificationSettingsRead:
    user.notification_timezone = payload.timezone
    db.commit()
    return _settings_read(db, user)


@router.post("/subscriptions", response_model=NotificationSettingsRead, status_code=201)
def create_push_subscription(
    payload: PushSubscriptionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> NotificationSettingsRead:
    if vapid_config() is None:
        raise HTTPException(
            status_code=503, detail=localized("api.webPushIsNotConfiguredOnThisServer")
        )
    try:
        endpoint = validate_push_endpoint(payload.endpoint, resolve_dns=True)
        validate_subscription_keys(payload.p256dh, payload.auth)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=error_detail(error)) from error

    now = datetime.now(UTC)
    existing = db.scalar(select(PushSubscription).where(PushSubscription.endpoint == endpoint))
    if existing is None:
        db.add(
            PushSubscription(
                user_id=user.id,
                endpoint=endpoint,
                p256dh=payload.p256dh.strip(),
                auth=payload.auth.strip(),
                created_at=now,
            )
        )
    else:
        switched = existing.user_id != user.id
        existing.user_id = user.id
        existing.p256dh = payload.p256dh.strip()
        existing.auth = payload.auth.strip()
        if switched:
            existing.created_at = now
    user.notification_timezone = payload.timezone
    db.commit()
    return _settings_read(db, user)


@router.post("/unsubscribe", response_model=NotificationSettingsRead)
def unsubscribe_push(
    payload: PushUnsubscribeRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> NotificationSettingsRead:
    db.execute(
        delete(PushSubscription).where(
            PushSubscription.user_id == user.id,
            PushSubscription.endpoint == payload.endpoint.strip(),
        )
    )
    db.commit()
    return _settings_read(db, user)


@router.post("/test", response_model=Message)
def send_test_notification(
    payload: NotificationTestRequest | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Message:
    if vapid_config() is None:
        raise HTTPException(
            status_code=503, detail=localized("api.webPushIsNotConfiguredOnThisServer")
        )
    query = select(PushSubscription).where(PushSubscription.user_id == user.id)
    if payload is not None and payload.endpoint:
        query = query.where(PushSubscription.endpoint == payload.endpoint.strip())
    subs = list(db.scalars(query).all())
    if not subs:
        raise HTTPException(
            status_code=409, detail=localized("api.noActivePushSubscriptionForThisDevice")
        )
    push_payload = {
        "title": translate("notification.testTitle", user.language),
        "body": translate("notification.testBody", user.language),
        "url": "/#/settings",
        "tag": "next-task-test",
    }
    sent_any = False
    expired_ids: list[int] = []
    for sub in subs:
        outcome = send_web_push(sub.endpoint, sub.p256dh, sub.auth, push_payload, ttl=300)
        if outcome == "sent":
            sent_any = True
        elif outcome == "expired":
            expired_ids.append(sub.id)
    if expired_ids:
        db.execute(delete(PushSubscription).where(PushSubscription.id.in_(expired_ids)))
        db.commit()
    if not sent_any:
        raise HTTPException(
            status_code=502, detail=localized("api.pushServiceRejectedNotification")
        )
    return Message(message=localized("api.testNotificationSent"))


@router.get("", response_model=NotificationListRead)
def list_notifications(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> NotificationListRead:
    unread_count = (
        db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == user.id, Notification.read_at.is_(None))
        )
        or 0
    )
    items = list(
        db.scalars(
            select(Notification)
            .where(Notification.user_id == user.id)
            .order_by(Notification.created_at.desc(), Notification.id.desc())
            .limit(50)
        ).all()
    )
    return NotificationListRead(
        unread_count=unread_count,
        items=[NotificationRead.model_validate(item) for item in items],
    )


@router.post("/read", response_model=UnreadCountRead)
def mark_notifications_read(
    payload: NotificationsReadRequest | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> UnreadCountRead:
    ids = payload.ids if payload is not None else None
    if ids is None or ids:
        stmt = (
            update(Notification)
            .where(Notification.user_id == user.id, Notification.read_at.is_(None))
            .values(read_at=datetime.now(UTC))
        )
        if ids is not None:
            stmt = stmt.where(Notification.id.in_(ids))
        db.execute(stmt)
        db.commit()
    unread_count = (
        db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == user.id, Notification.read_at.is_(None))
        )
        or 0
    )
    return UnreadCountRead(unread_count=unread_count)
