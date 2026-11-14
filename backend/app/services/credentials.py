import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings
from app.i18n import localized


class CredentialError(RuntimeError):
    pass


def _fernet() -> Fernet:
    secret = get_settings().credential_secret.get_secret_value()
    if len(secret) < 32:
        raise CredentialError(
            localized("api.credentialEncryptionNotConfigured")
        )
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
    return Fernet(key)


def encrypt_credential(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt_credential(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken as error:
        raise CredentialError(
            localized("api.geminiKeyUnreadable")
        ) from error
