"""Encryption at rest for broker credentials.

A broker token is the one thing FinView stores that it could not rebuild from
the user's own files: whoever reads it can pull the account's whole history.
It is kept encrypted with Fernet (AES-128-CBC + HMAC-SHA256) under
`FINVIEW_CREDENTIALS_KEY`, which lives in Secret Manager, never in the database.

No key means no connections: `CredentialsUnavailable` is raised rather than
falling back to storing the token in clear.
"""

from cryptography.fernet import Fernet, InvalidToken

from backend.config import settings


class CredentialsUnavailable(RuntimeError):
    """The key is missing or cannot decrypt what is stored."""


def _fernet() -> Fernet:
    key = settings.credentials_key
    if not key:
        raise CredentialsUnavailable("FINVIEW_CREDENTIALS_KEY is not set")
    try:
        return Fernet(key.encode())
    except ValueError as exc:
        raise CredentialsUnavailable("FINVIEW_CREDENTIALS_KEY is not a valid Fernet key") from exc


def credentials_enabled() -> bool:
    try:
        _fernet()
    except CredentialsUnavailable:
        return False
    return True


def encrypt_secret(plain: str) -> str:
    return _fernet().encrypt(plain.encode()).decode()


def decrypt_secret(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as exc:
        # A rotated key: the stored token is unreadable, the user must reconnect.
        raise CredentialsUnavailable("stored credential cannot be decrypted") from exc
