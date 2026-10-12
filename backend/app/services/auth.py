from __future__ import annotations

import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_AUTH_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)


class AuthError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def verify_access_token(token: str) -> str:
    """Verify a Supabase user Access Token via Supabase Auth API.

    Uses the anon/publishable key to call GET /auth/v1/user.
    Returns the authenticated user_id.

    Raises AuthError with:
      - code="UNAUTHORIZED" (401) for missing/invalid/expired tokens
      - code="AUTH_UNAVAILABLE" (503) for network errors or Supabase 5xx
      - code="AUTH_NOT_CONFIGURED" (503) if Supabase URL/key not set
    """
    if not settings.supabase_url:
        raise AuthError("AUTH_NOT_CONFIGURED", "Supabase is not configured on the backend.")

    api_key = settings.supabase_publishable_key or settings.supabase_anon_key
    if not api_key:
        raise AuthError("AUTH_NOT_CONFIGURED", "Supabase public API key is not configured on the backend.")

    url = f"{settings.supabase_url.rstrip('/')}/auth/v1/user"
    try:
        with httpx.Client(timeout=_AUTH_TIMEOUT) as client:
            response = client.get(
                url,
                headers={
                    "apikey": api_key,
                    "Authorization": f"Bearer {token}",
                },
            )
    except (httpx.TimeoutException, httpx.TransportError) as exc:
        logger.warning("supabase_auth_api_unreachable", extra={"error_type": type(exc).__name__})
        raise AuthError("AUTH_UNAVAILABLE", "Authentication service is temporarily unavailable.") from exc

    if response.status_code == 401:
        raise AuthError("UNAUTHORIZED", "Login token is invalid or expired.")

    if response.status_code >= 500:
        logger.warning("supabase_auth_api_5xx", extra={"status": response.status_code})
        raise AuthError("AUTH_UNAVAILABLE", "Authentication service is temporarily unavailable.")

    if response.status_code != 200:
        logger.warning("supabase_auth_api_error", extra={"status": response.status_code})
        raise AuthError("UNAUTHORIZED", "Authentication failed.")

    user_data = response.json()
    user_id = user_data.get("id")
    if not user_id:
        raise AuthError("UNAUTHORIZED", "Login token is missing the user id.")
    return str(user_id)


def verify_required_supabase_jwt(authorization: str | None) -> str:
    """Require a valid Bearer token. Returns user_id or raises AuthError."""
    if not authorization:
        raise AuthError("UNAUTHORIZED", "Login is required for this API.")

    if not authorization.startswith("Bearer "):
        raise AuthError("UNAUTHORIZED", "Authorization header must use Bearer token.")

    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise AuthError("UNAUTHORIZED", "Login is required for this API.")

    return verify_access_token(token)


def verify_optional_supabase_jwt(authorization: str | None) -> str | None:
    """Verify token if present. Returns user_id or None (no token). Raises AuthError on invalid token."""
    if not authorization:
        return None

    if not authorization.startswith("Bearer "):
        raise AuthError("UNAUTHORIZED", "Authorization header must use Bearer token.")

    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        return None

    if not settings.supabase_url:
        return None

    return verify_access_token(token)
