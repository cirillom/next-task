"""Database-backed limits shared by all app processes."""

import hashlib
from datetime import UTC, datetime, timedelta
from ipaddress import ip_address

from sqlalchemy import and_, case, delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.models import AuthLoginAttempt, AuthRateLimit

WINDOW = timedelta(minutes=15)
LOCKOUT = timedelta(minutes=15)
ACCOUNT_FAILURE_LIMIT = 5
PASSWORD_CHANGE_FAILURE_LIMIT = 5
IP_FAILURE_LIMIT = 30
IP_FAILURE_WINDOW = timedelta(minutes=15)
IP_BURST_LIMIT = 10
IP_BURST_WINDOW = timedelta(seconds=10)


def ip_key(client_ip: str) -> str:
    try:
        address = ip_address(client_ip)
        normalized = str(address.ipv4_mapped or address) if address.version == 6 else str(address)
    except ValueError:
        normalized = client_ip.strip().lower()
    return f"login-ip:{hashlib.sha256(normalized.encode()).hexdigest()}"


def ip_burst_key(client_ip: str) -> str:
    return ip_key(client_ip).replace("login-ip:", "login-burst:", 1)


def account_key(user_id: int) -> str:
    return f"login-account:{user_id}"


def password_change_key(user_id: int) -> str:
    return f"change-password:{user_id}"


def is_locked(db: Session, key: str, now: datetime) -> bool:
    locked_until = db.scalar(select(AuthRateLimit.locked_until).where(AuthRateLimit.key == key))
    if locked_until is None:
        return False
    if locked_until.tzinfo is None:
        locked_until = locked_until.replace(tzinfo=UTC)
    return locked_until > now


def record_attempt(
    db: Session,
    key: str,
    now: datetime,
    *,
    limit: int,
    lockout: timedelta | None = None,
) -> int:
    """Atomically count an attempt and commit it before returning or hashing a password."""
    table = AuthRateLimit.__table__
    insert = postgres_insert if db.bind.dialect.name == "postgresql" else sqlite_insert
    statement = insert(table).values(key=key, attempts=1, window_started_at=now)
    stale = or_(
        table.c.window_started_at <= now - WINDOW,
        and_(table.c.locked_until.is_not(None), table.c.locked_until <= now),
    )
    next_count = case((stale, 1), else_=table.c.attempts + 1)
    values = {
        "attempts": next_count,
        "window_started_at": case((stale, now), else_=table.c.window_started_at),
        "locked_until": (
            case(
                (stale, None),
                (next_count >= limit, now + lockout),
                else_=None,
            )
            if lockout is not None
            else None
        ),
    }
    statement = statement.on_conflict_do_update(index_elements=[table.c.key], set_=values)
    attempts = db.scalar(statement.returning(table.c.attempts))
    db.commit()
    assert attempts is not None
    return attempts


def clear_attempts(db: Session, key: str) -> None:
    db.execute(delete(AuthRateLimit).where(AuthRateLimit.key == key))
    db.execute(delete(AuthLoginAttempt).where(AuthLoginAttempt.key == key))


def reserve_window_attempt(
    db: Session, key: str, now: datetime, *, window: timedelta, limit: int
) -> int | None:
    """Reserve a slot atomically before password verification; return its event ID."""
    table = AuthRateLimit.__table__
    insert = postgres_insert if db.bind.dialect.name == "postgresql" else sqlite_insert
    # The upsert locks this key until commit, serializing concurrent reservations.
    db.execute(
        insert(table)
        .values(key=key, attempts=1, window_started_at=now)
        .on_conflict_do_update(index_elements=[table.c.key], set_={"window_started_at": now})
    )
    db.execute(
        delete(AuthLoginAttempt).where(
            AuthLoginAttempt.key == key, AuthLoginAttempt.created_at <= now - window
        )
    )
    count = db.scalar(select(func.count(AuthLoginAttempt.id)).where(AuthLoginAttempt.key == key))
    if count is not None and count >= limit:
        db.commit()
        return None
    attempt = AuthLoginAttempt(key=key, created_at=now)
    db.add(attempt)
    db.commit()
    return attempt.id


def release_window_attempt(db: Session, attempt_id: int) -> None:
    db.execute(delete(AuthLoginAttempt).where(AuthLoginAttempt.id == attempt_id))
    db.commit()


def lock_window_if_full(
    db: Session, key: str, now: datetime, *, window: timedelta, limit: int, lockout: timedelta
) -> None:
    # Lock the same guard row as reservations and successful-login cleanup.
    db.execute(update(AuthRateLimit).where(AuthRateLimit.key == key).values(window_started_at=now))
    count = db.scalar(
        select(func.count(AuthLoginAttempt.id)).where(
            AuthLoginAttempt.key == key, AuthLoginAttempt.created_at > now - window
        )
    )
    if count is not None and count >= limit:
        db.execute(
            update(AuthRateLimit).where(AuthRateLimit.key == key).values(locked_until=now + lockout)
        )
    db.commit()


def purge_expired_attempts(db: Session, now: datetime) -> None:
    db.execute(
        delete(AuthRateLimit).where(AuthRateLimit.window_started_at < now - timedelta(days=1))
    )
    db.execute(
        delete(AuthLoginAttempt).where(AuthLoginAttempt.created_at < now - timedelta(days=1))
    )
