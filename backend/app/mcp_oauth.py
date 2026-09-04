from __future__ import annotations

import html
import json
import secrets
import time
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any
from urllib.parse import urlencode, urlparse

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    AuthorizeError,
    RefreshToken,
    RegistrationError,
    TokenError,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from pydantic import AnyUrl
from sqlalchemy import delete, or_, select
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from app.auth.security import normalize_email, verify_password
from app.config import get_settings
from app.database import SessionLocal
from app.models import McpAuthorizationCode, McpOAuthClient, McpOAuthToken, User
from app.services.credentials import CredentialError, decrypt_credential, encrypt_credential

SCOPES = ["tasks"]
AUTHORIZATION_LIFETIME = timedelta(minutes=10)
_LOGIN_WINDOW_SECONDS = 15 * 60
_LOGIN_ATTEMPTS = 12
_failed_logins: dict[str, deque[float]] = defaultdict(deque)


def _token_hash(token: str) -> str:
    return sha256(token.encode()).hexdigest()


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _scopes(value: str) -> list[str]:
    parsed = json.loads(value)
    return [str(item) for item in parsed]


def _is_chatgpt_redirect(uri: AnyUrl) -> bool:
    parsed = urlparse(str(uri))
    return (
        parsed.scheme == "https"
        and parsed.netloc == "chatgpt.com"
        and not parsed.fragment
        and (
            parsed.path == "/connector_platform_oauth_redirect"
            or parsed.path.startswith("/connector/oauth/")
        )
    )


class StoredAuthorizationCode(AuthorizationCode):
    user_id: int


class StoredRefreshToken(RefreshToken):
    user_id: int


class NextTaskOAuthProvider:
    def __init__(self) -> None:
        settings = get_settings()
        self.issuer = settings.mcp_public_url.rstrip("/")
        self.resource = f"{self.issuer}/mcp"
        self.access_lifetime = timedelta(minutes=settings.mcp_access_token_minutes)
        self.refresh_lifetime = timedelta(days=settings.mcp_refresh_token_days)

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        with SessionLocal() as db:
            stored = db.get(McpOAuthClient, client_id)
            if stored is None:
                return None
            values = json.loads(stored.metadata_json)
            if stored.client_secret_encrypted:
                values["client_secret"] = decrypt_credential(stored.client_secret_encrypted)
            return OAuthClientInformationFull.model_validate(values)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        redirect_uris = client_info.redirect_uris or []
        if not redirect_uris or not all(_is_chatgpt_redirect(uri) for uri in redirect_uris):
            raise RegistrationError(
                "invalid_redirect_uri",
                "Only the official ChatGPT OAuth callback may be registered",
            )
        values = client_info.model_dump(mode="json")
        client_secret = values.pop("client_secret", None)
        try:
            encrypted_secret = encrypt_credential(client_secret) if client_secret else None
        except CredentialError as error:
            raise RegistrationError("invalid_client_metadata", str(error)) from error
        with SessionLocal() as db:
            db.add(
                McpOAuthClient(
                    client_id=client_info.client_id,
                    metadata_json=json.dumps(values, separators=(",", ":")),
                    client_secret_encrypted=encrypted_secret,
                )
            )
            db.commit()

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        if params.resource is not None and params.resource != self.resource:
            raise AuthorizeError("invalid_target", "Unknown resource")
        scopes = params.scopes or SCOPES
        if not set(scopes).issubset(SCOPES):
            raise AuthorizeError("invalid_scope", "Unknown scope")
        request_data = {
            "client_id": client.client_id,
            "params": params.model_dump(mode="json"),
            "issued_at": int(time.time()),
        }
        request_token = encrypt_credential(json.dumps(request_data, separators=(",", ":")))
        return f"{self.issuer}/login?{urlencode({'request': request_token})}"

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> StoredAuthorizationCode | None:
        with SessionLocal() as db:
            item = db.get(McpAuthorizationCode, _token_hash(authorization_code))
            if item is None or item.client_id != client.client_id:
                return None
            return StoredAuthorizationCode(
                code=authorization_code,
                scopes=_scopes(item.scopes_json),
                expires_at=int(_as_utc(item.expires_at).timestamp()),
                client_id=item.client_id,
                code_challenge=item.code_challenge,
                redirect_uri=AnyUrl(item.redirect_uri),
                redirect_uri_provided_explicitly=item.redirect_uri_provided_explicitly,
                resource=item.resource,
                subject=str(item.user_id),
                user_id=item.user_id,
            )

    def _new_tokens(
        self,
        db: Any,
        *,
        client_id: str,
        user_id: int,
        scopes: list[str],
        existing: McpOAuthToken | None = None,
    ) -> OAuthToken:
        now = datetime.now(UTC)
        access_token = f"ntat_{secrets.token_urlsafe(32)}"
        refresh_token = f"ntrt_{secrets.token_urlsafe(32)}"
        item = existing or McpOAuthToken(client_id=client_id, user_id=user_id)
        item.access_token_hash = _token_hash(access_token)
        item.refresh_token_hash = _token_hash(refresh_token)
        item.scopes_json = json.dumps(scopes, separators=(",", ":"))
        item.resource = self.resource
        item.access_expires_at = now + self.access_lifetime
        item.refresh_expires_at = now + self.refresh_lifetime
        item.revoked_at = None
        if existing is None:
            db.add(item)
        return OAuthToken(
            access_token=access_token,
            expires_in=int(self.access_lifetime.total_seconds()),
            scope=" ".join(scopes),
            refresh_token=refresh_token,
        )

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: StoredAuthorizationCode
    ) -> OAuthToken:
        with SessionLocal() as db:
            stored = db.get(McpAuthorizationCode, _token_hash(authorization_code.code))
            if stored is None or stored.client_id != client.client_id:
                raise TokenError("invalid_grant", "Authorization code has already been used")
            tokens = self._new_tokens(
                db,
                client_id=client.client_id,
                user_id=stored.user_id,
                scopes=_scopes(stored.scopes_json),
            )
            db.delete(stored)
            db.commit()
            return tokens

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> StoredRefreshToken | None:
        with SessionLocal() as db:
            item = db.scalar(
                select(McpOAuthToken).where(
                    McpOAuthToken.refresh_token_hash == _token_hash(refresh_token),
                    McpOAuthToken.client_id == client.client_id,
                    McpOAuthToken.revoked_at.is_(None),
                )
            )
            if item is None:
                return None
            return StoredRefreshToken(
                token=refresh_token,
                client_id=item.client_id,
                scopes=_scopes(item.scopes_json),
                expires_at=int(_as_utc(item.refresh_expires_at).timestamp()),
                subject=str(item.user_id),
                user_id=item.user_id,
            )

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: StoredRefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        with SessionLocal() as db:
            item = db.scalar(
                select(McpOAuthToken).where(
                    McpOAuthToken.refresh_token_hash == _token_hash(refresh_token.token),
                    McpOAuthToken.client_id == client.client_id,
                    McpOAuthToken.revoked_at.is_(None),
                )
            )
            if item is None or _as_utc(item.refresh_expires_at) <= datetime.now(UTC):
                raise TokenError("invalid_grant", "Refresh token is invalid or expired")
            tokens = self._new_tokens(
                db,
                client_id=client.client_id,
                user_id=item.user_id,
                scopes=scopes,
                existing=item,
            )
            db.commit()
            return tokens

    async def load_access_token(self, token: str) -> AccessToken | None:
        with SessionLocal() as db:
            item = db.scalar(
                select(McpOAuthToken).where(
                    McpOAuthToken.access_token_hash == _token_hash(token),
                    McpOAuthToken.revoked_at.is_(None),
                )
            )
            if item is None or _as_utc(item.access_expires_at) <= datetime.now(UTC):
                return None
            return AccessToken(
                token=token,
                client_id=item.client_id,
                scopes=_scopes(item.scopes_json),
                expires_at=int(_as_utc(item.access_expires_at).timestamp()),
                resource=item.resource,
                subject=str(item.user_id),
                claims={"iss": self.issuer},
            )

    async def verify_token(self, token: str) -> AccessToken | None:
        return await self.load_access_token(token)

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        now = datetime.now(UTC)
        token_hash = _token_hash(token.token)
        with SessionLocal() as db:
            item = db.scalar(
                select(McpOAuthToken).where(
                    or_(
                        McpOAuthToken.access_token_hash == token_hash,
                        McpOAuthToken.refresh_token_hash == token_hash,
                    )
                )
            )
            if item is not None:
                item.revoked_at = now
                db.commit()

    async def exchange_identity_assertion(self, client: Any, params: Any) -> OAuthToken:
        raise TokenError("unsupported_grant_type", "Identity assertions are not supported")


async def _authorization_request(
    provider: NextTaskOAuthProvider, request_token: str
) -> tuple[OAuthClientInformationFull, AuthorizationParams]:
    try:
        decoded = json.loads(decrypt_credential(request_token))
        if int(decoded["issued_at"]) + int(AUTHORIZATION_LIFETIME.total_seconds()) < time.time():
            raise ValueError("expired")
        client = await provider.get_client(str(decoded["client_id"]))
        params = AuthorizationParams.model_validate(decoded["params"])
    except (CredentialError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("This authorization request is invalid or expired") from error
    if client is None:
        raise ValueError("This authorization request is invalid or expired")
    return client, params


def _login_page(request_token: str, client_name: str, error: str = "") -> HTMLResponse:
    error_html = f'<p class="error">{html.escape(error)}</p>' if error else ""
    body = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Connect ChatGPT to Next Task</title>
<style>
:root {{
  color-scheme:light; font-family:system-ui,sans-serif; color:#17231e; background:#f3f0e8
}}
body {{
  min-height:100vh; margin:0; display:grid; place-items:center; padding:1rem;
  box-sizing:border-box
}}
main {{
  width:min(100%,26rem); background:#fffdf8; border:1px solid #dcd8cd;
  border-radius:1rem; padding:2rem; box-shadow:0 18px 50px #1e30271a
}}
h1 {{ margin:.2rem 0 .8rem; font-family:Georgia,serif }} p {{ line-height:1.5 }}
label {{ display:grid; gap:.35rem; margin:1rem 0; font-size:.85rem; font-weight:650 }}
input {{ font:inherit; padding:.7rem; border:1px solid #cfcbbf; border-radius:.55rem }}
.actions {{
  display:flex; align-items:center; justify-content:space-between; gap:.8rem; margin-top:1.3rem
}}
button {{ font:inherit; border:0; border-radius:.55rem; padding:.72rem 1rem; cursor:pointer }}
.approve {{ color:white; background:#183e30; font-weight:700 }} .deny {{ background:#e6e2d8 }}
.error {{ background:#f9e2df; color:#842b24; border-radius:.6rem; padding:.75rem }}
small {{ color:#68736e }}
</style>
</head>
<body><main>
<small>NEXT TASK CONNECTOR</small>
<h1>Connect {html.escape(client_name)}</h1>
<p>Sign in to let ChatGPT read and manage only the Next Task workspaces your account can access.</p>
{error_html}
<form method="post" action="/login">
<input type="hidden" name="request" value="{html.escape(request_token, quote=True)}">
<label>Email<input type="email" name="email" autocomplete="username" required autofocus></label>
<label>Password
<input type="password" name="password" autocomplete="current-password" required>
</label>
<div class="actions">
<button class="deny" name="decision" value="deny">Cancel</button>
<button class="approve" name="decision" value="approve">Connect ChatGPT</button>
</div>
</form>
</main></body></html>"""
    return HTMLResponse(
        body,
        headers={
            "Cache-Control": "no-store",
            "Content-Security-Policy": (
                "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; "
                "frame-ancestors 'none'; base-uri 'none'"
            ),
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
        },
    )


def _login_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _login_limited(request: Request) -> bool:
    now = time.monotonic()
    attempts = _failed_logins[_login_key(request)]
    while attempts and attempts[0] < now - _LOGIN_WINDOW_SECONDS:
        attempts.popleft()
    return len(attempts) >= _LOGIN_ATTEMPTS


def _record_failed_login(request: Request) -> None:
    _failed_logins[_login_key(request)].append(time.monotonic())


def _clear_failed_logins(request: Request) -> None:
    _failed_logins.pop(_login_key(request), None)


def install_oauth_routes(server: Any, provider: NextTaskOAuthProvider) -> None:
    @server.custom_route("/", methods=["GET"], include_in_schema=False)
    async def landing(_request: Request) -> Response:
        return JSONResponse({"name": "Next Task MCP", "mcp": "/mcp", "status": "ok"})

    @server.custom_route("/health", methods=["GET"], include_in_schema=False)
    async def health(_request: Request) -> Response:
        return JSONResponse({"status": "ok"})

    @server.custom_route("/login", methods=["GET", "POST"], include_in_schema=False)
    async def login(request: Request) -> Response:
        if request.method == "GET":
            request_token = request.query_params.get("request", "")
        else:
            form = await request.form()
            request_token = str(form.get("request", ""))
        try:
            client, params = await _authorization_request(provider, request_token)
        except ValueError as error:
            return HTMLResponse(str(error), status_code=400, headers={"Cache-Control": "no-store"})

        redirect_uri = str(params.redirect_uri)
        if request.method == "GET":
            return _login_page(request_token, client.client_name or "ChatGPT")

        form = await request.form()
        if form.get("decision") == "deny":
            return RedirectResponse(
                construct_redirect_uri(redirect_uri, error="access_denied", state=params.state),
                status_code=302,
                headers={"Cache-Control": "no-store"},
            )
        if _login_limited(request):
            return _login_page(
                request_token,
                client.client_name or "ChatGPT",
                "Too many failed attempts. Wait 15 minutes and try again.",
            )

        email = normalize_email(str(form.get("email", "")))
        password = str(form.get("password", ""))
        with SessionLocal() as db:
            user = db.scalar(select(User).where(User.email == email))
            if user is None or not verify_password(user.password_hash, password):
                _record_failed_login(request)
                return _login_page(
                    request_token,
                    client.client_name or "ChatGPT",
                    "Invalid email or password.",
                )
            _clear_failed_logins(request)
            code = secrets.token_urlsafe(32)
            now = datetime.now(UTC)
            db.execute(delete(McpAuthorizationCode).where(McpAuthorizationCode.expires_at < now))
            db.add(
                McpAuthorizationCode(
                    code_hash=_token_hash(code),
                    client_id=client.client_id,
                    user_id=user.id,
                    scopes_json=json.dumps(params.scopes or SCOPES, separators=(",", ":")),
                    code_challenge=params.code_challenge,
                    redirect_uri=redirect_uri,
                    redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
                    resource=params.resource or provider.resource,
                    expires_at=now + AUTHORIZATION_LIFETIME,
                )
            )
            db.commit()
        return RedirectResponse(
            construct_redirect_uri(
                redirect_uri,
                code=code,
                state=params.state,
                iss=provider.issuer,
            ),
            status_code=302,
            headers={"Cache-Control": "no-store"},
        )
