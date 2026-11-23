import logging
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import anyio
from app.auth.security import hash_token, replace_password
from app.database import SessionLocal
from app.mcp_oauth import Server
from app.mcp_server import Verifier
from app.models import MCPCode, MCPCredential, MCPGrant, User
from app.oauth_bridge import OAuthRequest
from authlib.oauth2.rfc7636.challenge import create_s256_code_challenge
from sqlalchemy import select
from starlette.datastructures import FormData, Headers, QueryParams


def test_password_replacement_revokes_only_owners_grants(create_user):
    first = create_user("first-mcp@example.com")
    second = create_user("second-mcp@example.com")
    with SessionLocal() as db:
        for user in (first, second):
            db.add(
                MCPGrant(
                    user_id=user.id,
                    client_id="https://client.example/meta",
                    client_name="Client",
                    redirect_uri="https://client.example/cb",
                    resource="https://server.example/mcp",
                    scope="tasks:read",
                )
            )
        db.commit()
        replace_password(db, db.get(User, first.id), "new password long enough")
        db.commit()
        grants = db.scalars(select(MCPGrant).order_by(MCPGrant.user_id)).all()
        assert grants[0].revoked_at is not None
        assert grants[1].revoked_at is None


def test_only_hashes_of_codes_and_credentials_are_stored(create_user):
    user = create_user("storage-mcp@example.com")
    with SessionLocal() as db:
        grant = MCPGrant(
            user_id=user.id,
            client_id="https://client.example/meta",
            client_name="Client",
            redirect_uri="https://client.example/cb",
            resource="https://server.example/mcp",
            scope="tasks:read",
        )
        db.add(grant)
        db.flush()
        expiry = datetime.now(UTC) + timedelta(minutes=5)
        db.add(
            MCPCode(
                token_hash=hash_token("code"),
                grant_id=grant.id,
                code_challenge="a" * 43,
                code_challenge_method="S256",
                expires_at=expiry,
            )
        )
        db.add(
            MCPCredential(
                token_hash=hash_token("token"),
                grant_id=grant.id,
                kind="access",
                scope="tasks:read",
                expires_at=expiry,
            )
        )
        db.commit()
        assert db.get(MCPCode, "code") is None
        assert db.get(MCPCredential, "token") is None
        assert db.get(MCPCode, hash_token("code")).grant.user_id == user.id


def test_same_client_grants_keep_distinct_user_subjects_and_expire(create_user):
    first = create_user("mcp-subject-one@example.com")
    second = create_user("mcp-subject-two@example.com")
    with SessionLocal() as db:
        for user, token in ((first, "token-one"), (second, "token-two")):
            grant = MCPGrant(
                user_id=user.id,
                client_id="https://client.example/meta",
                client_name="Client",
                redirect_uri="https://client.example/cb",
                resource="https://server.example/mcp",
                scope="tasks:read",
            )
            db.add(grant)
            db.flush()
            db.add(
                MCPCredential(
                    token_hash=hash_token(token),
                    grant_id=grant.id,
                    kind="access",
                    scope="tasks:read",
                    expires_at=datetime.now(UTC) + timedelta(hours=1),
                )
            )
        db.commit()
    one = anyio.run(Verifier().verify_token, "token-one")
    two = anyio.run(Verifier().verify_token, "token-two")
    assert one.subject == str(first.id) and two.subject == str(second.id)
    with SessionLocal() as db:
        credential = db.get(MCPCredential, hash_token("token-one"))
        credential.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
    assert anyio.run(Verifier().verify_token, "token-one") is None
    assert anyio.run(Verifier().verify_token, "token-two") is not None
    with SessionLocal() as db:
        db.delete(db.get(User, second.id))
        db.commit()
    assert anyio.run(Verifier().verify_token, "token-two") is None


def test_authlib_exchange_persists_and_refresh_replay_revokes(create_user, caplog):
    caplog.set_level(logging.DEBUG)
    user = create_user("exchange-mcp@example.com")
    issuer = "https://server.example"
    client_id = "https://client.example/meta"
    callback = "https://client.example/cb"
    metadata = {
        "client_id": client_id,
        "client_name": "Client",
        "redirect_uris": [callback],
        "token_endpoint_auth_method": "none",
        "grant_types": ["authorization_code", "refresh_token"],
    }
    verifier = "a" * 43
    query = QueryParams(
        {
            "client_id": client_id,
            "redirect_uri": callback,
            "response_type": "code",
            "scope": "tasks:read",
            "resource": issuer + "/mcp",
            "code_challenge": create_s256_code_challenge(verifier),
            "code_challenge_method": "S256",
        }
    )
    with SessionLocal() as db:
        server = Server(db, metadata, issuer)
        request = OAuthRequest(
            "GET", issuer + "/oauth/authorize?" + str(query), Headers(), query, {}
        )
        response = server.create_authorization_response(request, grant_user=db.get(User, user.id))
        code = parse_qs(urlsplit(response.headers["location"]).query)["code"][0]
        db.commit()

    def token_request(values):
        with SessionLocal() as db:
            server = Server(db, metadata, issuer)
            request = OAuthRequest(
                "POST", issuer + "/oauth/token", Headers(), QueryParams(), FormData(values)
            )
            response = server.create_token_response(request)
            db.commit()
            import json

            return response.status_code, json.loads(response.body)

    status, token = token_request(
        {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": code,
            "redirect_uri": callback,
            "code_verifier": verifier,
            "resource": issuer + "/mcp",
        }
    )
    assert status == 200
    assert code not in caplog.text
    assert token["access_token"] not in caplog.text
    assert token["refresh_token"] not in caplog.text
    refresh = {
        "grant_type": "refresh_token",
        "client_id": client_id,
        "refresh_token": token["refresh_token"],
        "resource": issuer + "/mcp",
    }
    status, rotated = token_request(refresh)
    assert status == 200 and rotated["refresh_token"] != token["refresh_token"]
    assert token_request(refresh)[0] == 400
    with SessionLocal() as db:
        assert db.scalar(select(MCPGrant)).revoked_at is not None
