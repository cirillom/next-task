"""Authlib hooks for the MCP authorization server."""

import logging
import secrets
from datetime import UTC, datetime, timedelta

from authlib.oauth2.rfc6749 import AuthorizationServer, InvalidRequestError, grants
from authlib.oauth2.rfc6750 import BearerTokenGenerator
from authlib.oauth2.rfc7009 import RevocationEndpoint
from authlib.oauth2.rfc7636 import CodeChallenge
from authlib.oauth2.rfc9207 import IssuerParameter
from sqlalchemy.orm import Session

from app.auth.security import _as_utc, hash_token
from app.models import MCPCode, MCPCredential, MCPGrant, User
from app.oauth_bridge import OAuthRequest, oauth_response

# Authlib logs complete token responses at DEBUG; credentials must never enter logs.
for name in ("authorization_code", "refresh_token"):
    logging.getLogger("authlib.oauth2.rfc6749.grants." + name).setLevel(logging.INFO)


class Client:
    def __init__(self, metadata: dict):
        self.metadata = metadata

    def get_client_id(self):
        return self.metadata["client_id"]

    def get_default_redirect_uri(self):
        return None

    def check_redirect_uri(self, uri):
        return uri in self.metadata["redirect_uris"]

    def check_endpoint_auth_method(self, method, endpoint):
        return method == "none"

    def check_response_type(self, response_type):
        return response_type in self.metadata.get("response_types", ["code"])

    def check_grant_type(self, grant_type):
        return grant_type in self.metadata.get("grant_types", ["authorization_code"])

    def get_allowed_scope(self, scope):
        return scope or "tasks:read"


class Issuer(IssuerParameter):
    def __init__(self, issuer):
        self.issuer = issuer

    def get_issuer(self):
        return self.issuer


class Server(AuthorizationServer):
    def __init__(self, db: Session, metadata: dict, issuer: str):
        super().__init__(scopes_supported=["tasks:read"])
        self.db = db
        self.client = Client(metadata)
        self.issuer = issuer
        self.resource = issuer + "/mcp"
        self.register_grant(CodeGrant, [CodeChallenge(required=True)])
        self.register_grant(RefreshGrant)
        self.register_endpoint(Revocation)
        self.register_extension(Issuer(issuer))
        self.register_token_generator(
            "default",
            BearerTokenGenerator(
                lambda **_: secrets.token_urlsafe(32),
                lambda **_: secrets.token_urlsafe(32),
                expires_generator=3600,
            ),
        )

    def query_client(self, client_id):
        return self.client if client_id == self.client.get_client_id() else None

    def create_oauth2_request(self, request):
        assert isinstance(request, OAuthRequest)
        return request

    def handle_response(self, status, body, headers):
        return oauth_response(status, body, headers)

    def send_signal(self, name, *args, **kwargs):
        pass

    def save_token(self, token, request):
        grant = (request.authorization_code or request.refresh_token).grant
        now = datetime.now(UTC)
        for key, kind, lifetime in (
            ("access_token", "access", timedelta(hours=1)),
            ("refresh_token", "refresh", timedelta(days=30)),
        ):
            if key in token:
                self.db.add(
                    MCPCredential(
                        token_hash=hash_token(token[key]),
                        grant_id=grant.id,
                        kind=kind,
                        scope=token.get("scope", grant.scope),
                        expires_at=now + lifetime,
                    )
                )


class CodeGrant(grants.AuthorizationCodeGrant):
    TOKEN_ENDPOINT_AUTH_METHODS = ["none"]

    def validate_authorization_request(self):
        redirect = super().validate_authorization_request()
        self.validate_no_multiple_request_parameter(self.request)
        data = self.request.payload.data
        if (
            self.request.payload.datalist.get("resource") != [self.server.resource]
            or not data.get("code_challenge")
            or data.get("code_challenge_method") != "S256"
            or not data.get("redirect_uri")
        ):
            raise InvalidRequestError(redirect_uri=redirect)
        return redirect

    def save_authorization_code(self, code, request):
        data = request.payload.data
        grant = MCPGrant(
            user_id=request.user.id,
            client_id=request.client.get_client_id(),
            client_name=request.client.metadata["client_name"],
            redirect_uri=data["redirect_uri"],
            resource=self.server.resource,
            scope=request.scope,
        )
        self.server.db.add(grant)
        self.server.db.flush()
        self.server.db.add(
            MCPCode(
                token_hash=hash_token(code),
                grant_id=grant.id,
                code_challenge=data["code_challenge"],
                code_challenge_method="S256",
                expires_at=datetime.now(UTC) + timedelta(minutes=5),
            )
        )

    def query_authorization_code(self, code, client):
        credential = self.server.db.get(MCPCode, hash_token(code))
        if not credential or credential.grant.client_id != client.get_client_id():
            return None
        grant = credential.grant
        if self.request.payload.datalist.get("resource") != [grant.resource]:
            return None
        if credential.consumed_at:
            grant.revoked_at = datetime.now(UTC)
            return None
        if grant.revoked_at or _as_utc(credential.expires_at) <= datetime.now(UTC):
            return None
        return credential

    def delete_authorization_code(self, credential):
        credential.consumed_at = datetime.now(UTC)

    def authenticate_user(self, credential):
        return self.server.db.get(User, credential.grant.user_id)


class RefreshGrant(grants.RefreshTokenGrant):
    TOKEN_ENDPOINT_AUTH_METHODS = ["none"]
    INCLUDE_NEW_REFRESH_TOKEN = True

    def authenticate_refresh_token(self, token):
        credential = self.server.db.get(MCPCredential, hash_token(token))
        if not credential or credential.kind != "refresh":
            return None
        grant = credential.grant
        if grant.client_id != self.request.payload.client_id or self.request.payload.datalist.get(
            "resource"
        ) != [grant.resource]:
            return None
        if credential.consumed_at:
            grant.revoked_at = datetime.now(UTC)
            return None
        if grant.revoked_at or _as_utc(credential.expires_at) <= datetime.now(UTC):
            return None
        return credential

    def authenticate_user(self, credential):
        return self.server.db.get(User, credential.grant.user_id)

    def revoke_old_credential(self, credential):
        credential.consumed_at = datetime.now(UTC)


class Revocation(RevocationEndpoint):
    CLIENT_AUTH_METHODS = ["none"]

    def query_token(self, token_string, token_type_hint):
        return self.server.db.get(MCPCredential, hash_token(token_string))

    def revoke_token(self, token, request):
        token.grant.revoked_at = datetime.now(UTC)
