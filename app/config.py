from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    APP_NAME: str = "Xybitz"
    DEBUG: bool = False
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/xybitz.db"

    # LLM Provider — supports ollama | openai | groq
    LLM_PROVIDER: str = "ollama"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.2:3b"
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.1-8b-instant"

    SUMMARY_WORD_TARGET: int = 100
    FETCH_INTERVAL_MINUTES: int = 30
    ARTICLE_RETENTION_DAYS: int = 3
    INITIAL_BACKFILL_DAYS: int = 3
    DISPLAY_DAYS: int = 3
    SUMMARISATION_CONCURRENCY: int = 3
    FEEDS_CONFIG_PATH: str = "./data/feeds.yaml"
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "xybitz@admin"


settings = Settings()
