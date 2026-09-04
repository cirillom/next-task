from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import distinct, func, select, update
from sqlalchemy.orm import Session

from app.auth.security import get_current_user
from app.config import get_settings
from app.database import get_db
from app.models import McpAuthorizationCode, McpOAuthToken, User
from app.schemas import McpSettingsRead

router = APIRouter(prefix="/api/integrations/mcp", tags=["mcp"])


def _settings(db: Session, user: User) -> McpSettingsRead:
    now = datetime.now(UTC)
    active_connections = db.scalar(
        select(func.count(distinct(McpOAuthToken.client_id))).where(
            McpOAuthToken.user_id == user.id,
            McpOAuthToken.revoked_at.is_(None),
            McpOAuthToken.refresh_expires_at > now,
        )
    )
    base_url = get_settings().mcp_public_url.rstrip("/")
    return McpSettingsRead(
        connector_url=f"{base_url}/mcp",
        active_connections=active_connections or 0,
    )


@router.get("", response_model=McpSettingsRead)
def get_mcp_settings(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> McpSettingsRead:
    return _settings(db, user)


@router.delete("", response_model=McpSettingsRead)
def revoke_mcp_connections(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> McpSettingsRead:
    now = datetime.now(UTC)
    db.execute(
        update(McpOAuthToken)
        .where(McpOAuthToken.user_id == user.id, McpOAuthToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    db.query(McpAuthorizationCode).filter(McpAuthorizationCode.user_id == user.id).delete()
    db.commit()
    return _settings(db, user)
