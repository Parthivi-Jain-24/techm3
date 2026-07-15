"""Password hashing via Argon2id (argon2-cffi).

We never implement our own hashing, never store/return/log plaintext or hashes,
and never raise from verification (a wrong password is a normal ``False``).
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error

_hasher = PasswordHasher()  # Argon2id defaults

# A fixed dummy hash used to equalize verification time for unknown users, so
# response timing does not reveal whether a username exists.
_DUMMY_HASH = _hasher.hash("argon2-timing-equalizer")


def hash_password(plaintext: str) -> str:
    """Return an Argon2id hash. Input is never stored or logged."""
    return _hasher.hash(plaintext)


def verify_password(stored_hash: str, plaintext: str) -> bool:
    """Verify a password against a stored Argon2id hash. Returns False on any
    mismatch or malformed hash — never raises, never logs the inputs."""
    try:
        return _hasher.verify(stored_hash, plaintext)
    except (Argon2Error, Exception):  # noqa: BLE001 - fail closed, never leak
        return False


def dummy_verify(plaintext: str) -> None:
    """Run a verify against a dummy hash to keep timing constant for unknown
    users. Result is intentionally ignored."""
    try:
        _hasher.verify(_DUMMY_HASH, plaintext)
    except Exception:  # noqa: BLE001
        pass
