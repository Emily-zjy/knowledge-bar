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
        raise AuthError("UNAUTHORIZED", "Authorization 请求头格式无效。")

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
        raise AuthError("UNAUTHORIZED", "登录状态无效，请重新登录。") from exc

    user_id = payload.get("sub")
    if not user_id:
        raise AuthError("UNAUTHORIZED", "登录状态缺少用户信息。")
    return str(user_id)
