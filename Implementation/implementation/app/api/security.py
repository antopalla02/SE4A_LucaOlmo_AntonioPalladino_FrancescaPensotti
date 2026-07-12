"""API security primitives (DD Sec. 3.3; R42).

Passwords are never stored or compared in clear text: ``hash_password``
produces a salted PBKDF2-HMAC-SHA256 digest (R42) and ``verify_password``
performs a constant-time comparison. Authentication is token-based: a
successful login mints an opaque bearer token bound to a user id; the token
store is the seam that the per-user scoping of R42 hangs off.

The token store is process-local and in-memory on purpose — session
management is explicitly out of scope for the prototype (RASD assumptions);
what matters for the requirements is that every state-changing call is
attributable to an authenticated principal.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets

_ITERATIONS = 120_000


def hash_password(password: str) -> str:
    """PBKDF2-HMAC-SHA256 with a per-password random salt (R42)."""
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
    return f"pbkdf2_sha256${_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt_hex, digest_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        expected = bytes.fromhex(digest_hex)
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations)
        )
        return hmac.compare_digest(expected, actual)
    except (ValueError, AttributeError):
        return False


class TokenStore:
    """Opaque bearer tokens -> user id (R42 scoping seam)."""

    def __init__(self) -> None:
        self._tokens: dict[str, str] = {}

    def issue(self, user_id: str) -> str:
        token = secrets.token_urlsafe(24)
        self._tokens[token] = user_id
        return token

    def resolve(self, token: str) -> str | None:
        return self._tokens.get(token)
