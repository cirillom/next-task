"""Web Push encryption (RFC 8291 aes128gcm) and VAPID signing (RFC 8292)."""

import base64
import ipaddress
import json
import logging
import os
import socket
import struct
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import urlsplit

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.config import get_settings
from app.i18n import localized

logger = logging.getLogger(__name__)


class PushConfigurationError(ValueError):
    pass


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("Blank base64url value")
    padded = cleaned + "=" * (-len(cleaned) % 4)
    return base64.b64decode(padded.encode("ascii"), altchars=b"-_", validate=True)


def generate_vapid_keypair() -> tuple[str, str]:
    """Return a newly generated P-256 (private_b64url, public_b64url) pair."""
    private_key = ec.generate_private_key(ec.SECP256R1())
    private_raw = private_key.private_numbers().private_value.to_bytes(32, "big")
    return _b64url_encode(private_raw), vapid_public_key_b64(private_key)


def load_vapid_private_key(raw: str) -> ec.EllipticCurvePrivateKey:
    value = raw.strip()
    if not value:
        raise PushConfigurationError("VAPID private key is not configured.")
    try:
        if "BEGIN " in value:
            loaded = serialization.load_pem_private_key(value.encode("utf-8"), password=None)
            if (
                not isinstance(loaded, ec.EllipticCurvePrivateKey)
                or loaded.curve.name != "secp256r1"
            ):
                raise PushConfigurationError("VAPID private key must use P-256.")
            return loaded
        raw_bytes = _b64url_decode(value)
        if len(raw_bytes) != 32:
            raise PushConfigurationError("VAPID private key must be 32 bytes.")
        secret = int.from_bytes(raw_bytes, "big")
        if secret <= 0:
            raise PushConfigurationError("VAPID private key is invalid.")
        return ec.derive_private_key(secret, ec.SECP256R1())
    except PushConfigurationError:
        raise
    except (ValueError, TypeError, UnicodeEncodeError) as error:
        raise PushConfigurationError("VAPID private key is invalid.") from error


def vapid_public_key_b64(private_key: ec.EllipticCurvePrivateKey) -> str:
    public_bytes = private_key.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    return _b64url_encode(public_bytes)


def vapid_config() -> tuple[ec.EllipticCurvePrivateKey, str, str] | None:
    settings = get_settings()
    raw_key = settings.vapid_private_key.get_secret_value().strip()
    if not raw_key:
        return None
    try:
        private_key = load_vapid_private_key(raw_key)
    except PushConfigurationError:
        logger.warning("Ignoring invalid NEXT_TASK_VAPID_PRIVATE_KEY configuration")
        return None

    subject = settings.vapid_subject.strip()
    if not subject:
        app_url = settings.public_app_url.strip().rstrip("/")
        if app_url.startswith("https://"):
            subject = app_url
    if not (
        (subject.startswith("mailto:") and "@" in subject[7:])
        or (subject.startswith("https://") and bool(urlsplit(subject).hostname))
    ):
        return None
    return private_key, vapid_public_key_b64(private_key), subject


def build_vapid_header(
    endpoint: str,
    private_key: ec.EllipticCurvePrivateKey,
    public_b64: str,
    subject: str,
    now: datetime | None = None,
) -> str:
    parsed = urlsplit(endpoint)
    aud = f"{parsed.scheme}://{parsed.netloc}"
    exp = int((now or datetime.now(UTC)).timestamp()) + 12 * 3600
    header_b64 = _b64url_encode(
        json.dumps({"typ": "JWT", "alg": "ES256"}, separators=(",", ":")).encode("utf-8")
    )
    payload_b64 = _b64url_encode(
        json.dumps({"aud": aud, "exp": exp, "sub": subject}, separators=(",", ":")).encode("utf-8")
    )
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    der_sig = private_key.sign(signing_input, ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der_sig)
    raw_sig = r.to_bytes(32, "big") + s.to_bytes(32, "big")
    jwt = f"{header_b64}.{payload_b64}.{_b64url_encode(raw_sig)}"
    return f"vapid t={jwt}, k={public_b64}"


def validate_subscription_keys(p256dh: str, auth: str) -> tuple[bytes, bytes]:
    try:
        ua_pub = _b64url_decode(p256dh)
        auth_secret = _b64url_decode(auth)
        if len(ua_pub) != 65 or ua_pub[0] != 0x04 or len(auth_secret) != 16:
            raise ValueError("Invalid key length")
        ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_pub)
    except (ValueError, TypeError, UnicodeEncodeError) as error:
        raise ValueError(localized("api.invalidPushKeys")) from error
    return ua_pub, auth_secret


def encrypt_webpush_payload(
    plaintext: bytes,
    p256dh: str,
    auth: str,
    *,
    salt: bytes | None = None,
    server_private_key: ec.EllipticCurvePrivateKey | None = None,
) -> bytes:
    ua_pub_bytes, auth_secret = validate_subscription_keys(p256dh, auth)
    ua_public_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_pub_bytes)
    as_private = server_private_key or ec.generate_private_key(ec.SECP256R1())
    as_pub_bytes = as_private.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    ecdh_secret = as_private.exchange(ec.ECDH(), ua_public_key)
    key_info = b"WebPush: info\x00" + ua_pub_bytes + as_pub_bytes
    ikm = HKDF(algorithm=hashes.SHA256(), length=32, salt=auth_secret, info=key_info).derive(
        ecdh_secret
    )
    nonce_salt = salt if salt is not None else os.urandom(16)
    if len(nonce_salt) != 16:
        raise ValueError("Salt must be 16 bytes")
    cek = HKDF(
        algorithm=hashes.SHA256(),
        length=16,
        salt=nonce_salt,
        info=b"Content-Encoding: aes128gcm\x00",
    ).derive(ikm)
    nonce = HKDF(
        algorithm=hashes.SHA256(), length=12, salt=nonce_salt, info=b"Content-Encoding: nonce\x00"
    ).derive(ikm)
    ciphertext = AESGCM(cek).encrypt(nonce, plaintext + b"\x02", None)
    header = nonce_salt + struct.pack("!IB", 4096, len(as_pub_bytes)) + as_pub_bytes
    return header + ciphertext


def _is_public_ip(raw_ip: str) -> bool:
    ip = ipaddress.ip_address(raw_ip.split("%", 1)[0])
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return (
        ip.is_global
        and not ip.is_private
        and not ip.is_loopback
        and not ip.is_link_local
        and not ip.is_multicast
        and not ip.is_reserved
        and not ip.is_unspecified
    )


def validate_push_endpoint(endpoint: str, *, resolve_dns: bool = True) -> str:
    cleaned = endpoint.strip()
    if not cleaned or len(cleaned) > 2048:
        raise ValueError(localized("api.invalidPushEndpoint"))
    parsed = urlsplit(cleaned)
    try:
        port = parsed.port
    except ValueError as error:
        raise ValueError(localized("api.invalidPushEndpoint")) from error
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or port not in (None, 443)
    ):
        raise ValueError(localized("api.invalidPushEndpoint"))

    hostname = parsed.hostname.rstrip(".").lower()
    if (
        not hostname
        or hostname == "localhost"
        or hostname.endswith((".localhost", ".local", ".internal"))
        or "." not in hostname
    ):
        raise ValueError(localized("api.invalidPushEndpoint"))
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        raise ValueError(localized("api.invalidPushEndpoint"))

    if resolve_dns:
        try:
            infos = socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
        except OSError as error:
            raise ValueError(localized("api.invalidPushEndpoint")) from error
        if not infos or not all(_is_public_ip(info[4][0]) for info in infos):
            raise ValueError(localized("api.invalidPushEndpoint"))

    return cleaned


def send_web_push(
    endpoint: str,
    p256dh: str,
    auth: str,
    payload: dict[str, object],
    *,
    ttl: int = 3600,
) -> Literal["sent", "expired", "failed"]:
    config = vapid_config()
    if config is None:
        return "failed"
    private_key, public_b64, subject = config
    try:
        # shortcut: validates DNS before httpx send without IP pinning;
        # upgrade to a custom transport if DNS rebinding becomes a threat.
        validated_endpoint = validate_push_endpoint(endpoint, resolve_dns=True)
        body = encrypt_webpush_payload(
            json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            p256dh,
            auth,
        )
    except ValueError as error:
        logger.warning("Push preparation failed (%s)", type(error).__name__)
        return "failed"

    vapid_header = build_vapid_header(validated_endpoint, private_key, public_b64, subject)
    try:
        response = httpx.post(
            validated_endpoint,
            content=body,
            headers={
                "Content-Type": "application/octet-stream",
                "Content-Encoding": "aes128gcm",
                "TTL": str(ttl),
                "Urgency": "normal",
                "Authorization": vapid_header,
            },
            timeout=10.0,
            follow_redirects=False,
        )
    except httpx.HTTPError as error:
        logger.warning("Push delivery failed (%s)", type(error).__name__)
        return "failed"

    if 200 <= response.status_code < 300:
        return "sent"
    if response.status_code in (404, 410):
        return "expired"
    logger.warning("Push delivery rejected with HTTP %s", response.status_code)
    return "failed"
