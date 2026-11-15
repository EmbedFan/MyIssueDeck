"""Bearer token and dashboard session middleware."""

from __future__ import annotations

import hashlib
import hmac
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from urllib.parse import quote

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse

DASHBOARD_SESSION_COOKIE = "issuedeck_dashboard_session"
DASHBOARD_SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 7
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


@dataclass(frozen=True)
class BearerTokenCredential:
    """A bearer token: either the plaintext (config tokens) or its SHA-256 (runtime tokens)."""

    name: str
    scopes: frozenset[str]
    token: str | None = None
    token_sha256: str | None = None

    @property
    def session_key(self) -> str:
        """Key used to sign dashboard session cookies for this credential."""
        return self.token if self.token is not None else (self.token_sha256 or "")

    def matches(self, presented: str) -> bool:
        if self.token is not None:
            return hmac.compare_digest(presented, self.token)
        if self.token_sha256:
            return hmac.compare_digest(sha256_hex(presented), self.token_sha256)
        return False

    def allows(self, required_scope: str) -> bool:
        if "admin" in self.scopes:
            return True
        if required_scope == "read":
            return bool(self.scopes & {"read", "agent"})
        if required_scope == "agent":
            return "agent" in self.scopes
        return False


def make_dashboard_session_cookie(token: str, *, issued_at: int | None = None) -> str:
    timestamp = issued_at or int(time.time())
    signature = _dashboard_session_signature(token, timestamp)
    return f"v1.{timestamp}.{signature}"


def is_valid_dashboard_session_cookie(
    value: str | None,
    token: str,
    *,
    now: int | None = None,
    max_age_seconds: int = DASHBOARD_SESSION_MAX_AGE_SECONDS,
) -> bool:
    if not value:
        return False

    try:
        version, raw_timestamp, presented_signature = value.split(".", 2)
        timestamp = int(raw_timestamp)
    except (TypeError, ValueError):
        return False

    current_time = now or int(time.time())
    if version != "v1":
        return False
    if timestamp > current_time + 60:
        return False
    if current_time - timestamp > max_age_seconds:
        return False

    expected_signature = _dashboard_session_signature(token, timestamp)
    return hmac.compare_digest(presented_signature, expected_signature)


def _dashboard_session_signature(token: str, timestamp: int) -> str:
    payload = f"issuedeck.dashboard.v1.{timestamp}".encode()
    return hmac.new(token.encode(), payload, hashlib.sha256).hexdigest()


class BearerTokenMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        token: str | None = None,
        tokens: Iterable[BearerTokenCredential] | None = None,
        exempt_paths: Iterable[str] = (),
        dashboard_paths: Iterable[str] = (),
        dashboard_login_path: str = "/dashboard/login",
        dashboard_cookie_name: str = DASHBOARD_SESSION_COOKIE,
        dashboard_session_max_age_seconds: int = DASHBOARD_SESSION_MAX_AGE_SECONDS,
        token_provider: Callable[[], Iterable[BearerTokenCredential]] | None = None,
    ):
        super().__init__(app)
        if tokens is None:
            if token is None:
                raise ValueError("BearerTokenMiddleware requires token or tokens")
            tokens = (
                BearerTokenCredential(
                    name="api_token",
                    token=token,
                    scopes=frozenset({"admin"}),
                ),
            )
        self._static_tokens = tuple(tokens)
        # Runtime tokens (FEA-0004) are read on every request, so changes apply
        # without a restart.
        self._token_provider = token_provider
        self._exempt = tuple(exempt_paths)
        self._dashboard_paths = tuple(dashboard_paths)
        self._dashboard_login_path = dashboard_login_path
        self._dashboard_cookie_name = dashboard_cookie_name
        self._dashboard_session_max_age_seconds = dashboard_session_max_age_seconds

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if any(path == p or path.startswith(p + "/") for p in self._exempt):
            return await call_next(request)

        credential, bearer_error = self._authenticate_bearer(request)
        if credential is not None:
            required_scope = self._required_scope(request)
            if credential.allows(required_scope):
                return await call_next(request)
            return self._forbidden(
                f"token scope does not allow {required_scope} access"
            )

        if self._is_dashboard_path(path):
            cookie_value = request.cookies.get(self._dashboard_cookie_name)
            if self._is_valid_dashboard_session(cookie_value):
                return await call_next(request)

            if request.method in {"GET", "HEAD"}:
                return RedirectResponse(
                    url=self._dashboard_login_url(request),
                    status_code=303,
                )
            return self._unauth("missing dashboard session")

        return self._unauth(bearer_error)

    def _authenticate_bearer(
        self, request: Request,
    ) -> tuple[BearerTokenCredential | None, str]:
        header = request.headers.get("authorization", "")
        if not header.lower().startswith("bearer "):
            return None, "missing bearer token"
        presented = header.split(" ", 1)[1]
        for credential in self._credentials():
            if credential.matches(presented):
                return credential, ""
        return None, "invalid bearer token"

    def _credentials(self) -> tuple[BearerTokenCredential, ...]:
        extra = tuple(self._token_provider()) if self._token_provider else ()
        return (*self._static_tokens, *extra)

    def _required_scope(self, request: Request) -> str:
        if self._is_dashboard_path(request.url.path):
            return "admin"
        if request.method in SAFE_METHODS:
            return "read"
        if request.url.path.startswith("/api/"):
            return "agent"
        return "admin"

    def _is_valid_dashboard_session(self, cookie_value: str | None) -> bool:
        return any(
            is_valid_dashboard_session_cookie(
                cookie_value,
                credential.session_key,
                max_age_seconds=self._dashboard_session_max_age_seconds,
            )
            for credential in self._credentials()
            if credential.allows("admin") and credential.session_key
        )

    def _is_dashboard_path(self, path: str) -> bool:
        return any(path == p or path.startswith(p + "/") for p in self._dashboard_paths)

    def _dashboard_login_url(self, request: Request) -> str:
        next_url = request.url.path
        if request.url.query:
            next_url = f"{next_url}?{request.url.query}"
        return f"{self._dashboard_login_path}?next={quote(next_url, safe='')}"

    @staticmethod
    def _unauth(msg: str) -> JSONResponse:
        return JSONResponse(
            status_code=401,
            content={"error": {"code": "unauthorized", "message": msg, "details": {}}},
        )

    @staticmethod
    def _forbidden(msg: str) -> JSONResponse:
        return JSONResponse(
            status_code=403,
            content={"error": {"code": "forbidden", "message": msg, "details": {}}},
        )
