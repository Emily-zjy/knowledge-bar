from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "local"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    cors_allowed_origins: str = ""
    ai_provider: str = "mock"
    ai_api_key: str | None = None
    ai_base_url: str | None = None
    ai_api_base_url: str | None = None
    ai_model: str = "moonshot-v1-8k"
    ai_prompt_version: str = "p0-mindmap-v1"
    ai_prompt_rollout_mode: str = "stable_hash"
    ai_prompt_v2_percentage: int = 0
    ai_prompt_fallback_version: str = "v1"
    ai_timeout_seconds: int = 45
    ai_max_retries: int = 1
    ai_mock_fallback: bool = False
    supabase_url: str | None = None
    supabase_publishable_key: str | None = None
    supabase_anon_key: str | None = None
    supabase_secret_key: str | None = None
    supabase_service_role_key: str | None = None
    supabase_jwt_secret: str | None = None
    max_content_length: int = 120_000
    max_export_length: int = 5_000_000

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8-sig", extra="ignore")

    @property
    def resolved_ai_base_url(self) -> str | None:
        return self.ai_base_url or self.ai_api_base_url

    @property
    def cors_origins(self) -> list[str]:
        if self.cors_allowed_origins:
            return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]
        if self.app_env == "production":
            return []
        return [
            "http://localhost:5173",
            "http://localhost:5174",
            "http://localhost:5175",
            "http://localhost:5176",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:5174",
            "http://127.0.0.1:5175",
            "http://127.0.0.1:5176",
        ]


settings = Settings()
