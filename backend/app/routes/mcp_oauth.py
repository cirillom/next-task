import json
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from authlib.oauth2.rfc6749 import OAuth2Error
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session
from starlette.datastructures import Headers, QueryParams

from app.auth.rate_limit import ip_key, reserve_window_attempt
from app.auth.security import _as_utc, current_session, get_current_user, hash_token
from app.cimd import ClientMetadataResolver, InvalidClientMetadata
from app.database import SessionLocal, get_db
from app.mcp_oauth import Issuer, Server
from app.models import MCPAuthorization, MCPCode, MCPCredential, MCPGrant, User
from app.oauth_bridge import OAuthRequest, oauth_request
from app.services.mail import MailConfigurationError, public_app_url

router = APIRouter()
resolver = ClientMetadataResolver()


def rate_limit(request: Request):
    address = request.client.host if request.client else "unknown"
    with SessionLocal() as db:
        if (
            reserve_window_attempt(
                db,
                "mcp:" + ip_key(address),
                datetime.now(UTC),
                window=timedelta(minutes=1),
                limit=120,
            )
            is None
        ):
            raise HTTPException(status_code=429, detail="Too many requests")


def issuer() -> str:
    try:
        return public_app_url()
    except MailConfigurationError as error:
        raise HTTPException(status_code=503, detail="MCP is not configured") from error


def check_origin(request: Request, origin: str):
    if request.headers.get("origin") != origin:
        raise HTTPException(status_code=403, detail="Invalid origin")


@router.get("/.well-known/oauth-authorization-server")
def authorization_metadata(request: Request):
    origin = issuer()
    rate_limit(request)
    return {
        "issuer": origin,
        "authorization_endpoint": origin + "/oauth/authorize",
        "token_endpoint": origin + "/oauth/token",
        "revocation_endpoint": origin + "/oauth/revoke",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "scopes_supported": ["tasks:read"],
        "token_endpoint_auth_methods_supported": ["none"],
        "revocation_endpoint_auth_methods_supported": ["none"],
        "client_id_metadata_document_supported": True,
        "authorization_response_iss_parameter_supported": True,
    }


@router.get("/oauth/authorize")
async def authorize(request: Request):
    query = request.url.query
    _ = request.query_params
    request.scope["query_string"] = b""
    origin = issuer()
    rate_limit(request)
    if len(query) > 8192 or any(
        key in request.query_params
        for key in ("access_token", "refresh_token", "token", "client_secret")
    ):
        return JSONResponse({"error": "invalid_request"}, status_code=400)
    oauth = await oauth_request(request, origin)
    try:
        metadata = await resolver.resolve(oauth.payload.client_id)
    except InvalidClientMetadata:
        return JSONResponse({"error": "invalid_client"}, status_code=400)
    with SessionLocal() as db:
        server = Server(db, metadata, origin)
        try:
            server.get_consent_grant(oauth)
        except OAuth2Error as error:
            response = server.handle_error_response(oauth, error)
            Issuer(origin).add_issuer_parameter(server, response)
            return response
        opaque = secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        for model in (MCPAuthorization, MCPCode, MCPCredential):
            db.execute(delete(model).where(model.expires_at <= now))
        db.add(
            MCPAuthorization(
                request_hash=hash_token(opaque),
                query=query,
                metadata_json=json.dumps(metadata),
                expires_at=now + timedelta(minutes=5),
            )
        )
        db.commit()
    return RedirectResponse(
        "/#/mcp-consent?" + urlencode({"request": opaque}),
        status_code=303,
        headers={"Cache-Control": "no-store"},
    )


def authorization(
    db: Session, request: Request, request_id: str, *, bind: bool = False
) -> tuple[MCPAuthorization, User]:
    session = current_session(request, db)
    pending = db.get(MCPAuthorization, hash_token(request_id))
    if not session:
        raise HTTPException(status_code=401, detail="Sign in required")
    if not pending or _as_utc(pending.expires_at) <= datetime.now(UTC):
        raise HTTPException(status_code=404, detail="Authorization request expired")
    if (not pending.session_hash and not bind) or (
        pending.session_hash and pending.session_hash != session.token_hash
    ):
        raise HTTPException(status_code=404, detail="Authorization request expired")
    pending.session_hash = session.token_hash
    return pending, session.user


@router.get("/api/mcp/authorizations/{request_id}")
def authorization_details(
    request_id: str, request: Request, response: Response, db: Session = Depends(get_db)
):
    request.scope["path"] = "/api/mcp/authorizations/[redacted]"
    response.headers["Cache-Control"] = "no-store"
    if request.headers.get("origin") not in (None, issuer()) or request.headers.get(
        "sec-fetch-site"
    ) not in (None, "same-origin", "none"):
        raise HTTPException(status_code=403, detail="Invalid origin")
    db.execute(text("BEGIN IMMEDIATE"))
    pending, user = authorization(db, request, request_id, bind=True)
    metadata = json.loads(pending.metadata_json)
    query = QueryParams(pending.query)
    db.commit()
    return {
        "account": user.email,
        "client_name": metadata["client_name"],
        "redirect_uri": query.get("redirect_uri"),
        "scope": query.get("scope") or "tasks:read",
    }


class Decision(BaseModel):
    allow: bool


@router.post("/api/mcp/authorizations/{request_id}")
def decide(request_id: str, decision: Decision, request: Request, response: Response):
    request.scope["path"] = "/api/mcp/authorizations/[redacted]"
    response.headers["Cache-Control"] = "no-store"
    origin = issuer()
    check_origin(request, origin)
    with SessionLocal() as db:
        db.execute(text("BEGIN IMMEDIATE"))
        pending, user = authorization(db, request, request_id)
        query = QueryParams(pending.query)
        oauth = OAuthRequest(
            "GET", origin + "/oauth/authorize?" + pending.query, Headers(), query, {}
        )
        server = Server(db, json.loads(pending.metadata_json), origin)
        authorization_response = server.create_authorization_response(
            oauth, grant_user=user if decision.allow else None
        )
        location = authorization_response.headers.get("location")
        if not location:
            raise HTTPException(status_code=400, detail="Authorization failed")
        db.delete(pending)
        db.commit()
        return {"redirect_uri": location}


@router.post("/oauth/token")
async def token(request: Request):
    if request.url.query:
        request.scope["query_string"] = b""
        return JSONResponse({"error": "invalid_request"}, status_code=400)
    origin = issuer()
    rate_limit(request)
    oauth = await oauth_request(request, origin)
    if any(len(values) != 1 for values in oauth.payload.datalist.values()):
        return JSONResponse({"error": "invalid_request"}, status_code=400)
    try:
        metadata = await resolver.resolve(oauth.payload.client_id)
    except InvalidClientMetadata:
        return JSONResponse({"error": "invalid_client"}, status_code=400)
    with SessionLocal() as db:
        db.execute(text("BEGIN IMMEDIATE"))
        response = Server(db, metadata, origin).create_token_response(oauth)
        db.commit()
        return response


@router.post("/oauth/revoke")
async def revoke(request: Request):
    if request.url.query:
        request.scope["query_string"] = b""
        return JSONResponse({"error": "invalid_request"}, status_code=400)
    origin = issuer()
    rate_limit(request)
    oauth = await oauth_request(request, origin)
    if any(len(values) != 1 for values in oauth.payload.datalist.values()):
        return JSONResponse({"error": "invalid_request"}, status_code=400)
    try:
        metadata = await resolver.resolve(oauth.payload.client_id)
    except InvalidClientMetadata:
        return JSONResponse({"error": "invalid_client"}, status_code=400)
    with SessionLocal() as db:
        db.execute(text("BEGIN IMMEDIATE"))
        response = Server(db, metadata, origin).create_endpoint_response("revocation", oauth)
        db.commit()
        return response


@router.get("/api/settings/mcp")
def connections(
    response: Response, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    response.headers["Cache-Control"] = "no-store"
    grants = db.scalars(
        select(MCPGrant).where(MCPGrant.user_id == user.id, MCPGrant.revoked_at.is_(None))
    ).all()
    return {
        "endpoint": issuer() + "/mcp",
        "connections": [
            {
                "id": grant.id,
                "client_name": grant.client_name,
                "client_id": grant.client_id,
                "scope": grant.scope,
                "created_at": grant.created_at,
            }
            for grant in grants
        ],
    }


@router.delete("/api/settings/mcp/connections/{grant_id}", status_code=204)
def disconnect(
    grant_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    check_origin(request, issuer())
    grant = db.scalar(select(MCPGrant).where(MCPGrant.id == grant_id, MCPGrant.user_id == user.id))
    if not grant:
        raise HTTPException(status_code=404, detail="Connection not found")
    grant.revoked_at = datetime.now(UTC)
    db.commit()
