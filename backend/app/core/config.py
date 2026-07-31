from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "local"
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:5175",
        "http://localhost:5176",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "http://127.0.0.1:5175",
        "http://127.0.0.1:5176",
    ]
    ai_provider: str = "mock"
    ai_api_key: str | None = None
    ai_api_base_url: str | None = None
    ai_model: str = "moonshot-v1-8k"
    ai_prompt_version: str = "p0-mindmap-v1"
    ai_timeout_seconds: int = 45
    ai_mock_fallback: bool = True
    supabase_jwt_secret: str | None = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8-sig", extra="ignore")


settings = Settings()
