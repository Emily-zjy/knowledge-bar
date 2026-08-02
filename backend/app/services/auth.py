import jwt

from app.core.config import settings


class AuthError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def verify_optional_supabase_jwt(authorization: str | None) -> str | None:
    if not authorization:
        return None

    if not authorization.startswith("Bearer "):
        raise AuthError("UNAUTHORIZED", "Authorization header must use Bearer token.")

    if not settings.supabase_jwt_secret:
        return None

    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
            options={"verify_aud": False},
        )
    except jwt.PyJWTError as exc:
        raise AuthError("UNAUTHORIZED", "Login token is invalid or expired.") from exc

    user_id = payload.get("sub")
    if not user_id:
        raise AuthError("UNAUTHORIZED", "Login token is missing the user id.")
    return str(user_id)


def verify_required_supabase_jwt(authorization: str | None) -> str:
    if not authorization:
        raise AuthError("UNAUTHORIZED", "Login is required for this API.")

    if not settings.supabase_jwt_secret:
        raise AuthError("AUTH_NOT_CONFIGURED", "SUPABASE_JWT_SECRET is not configured on the backend.")

    user_id = verify_optional_supabase_jwt(authorization)
    if not user_id:
        raise AuthError("UNAUTHORIZED", "Login is required for this API.")
    return user_id
