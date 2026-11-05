from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    database_url: str = "postgresql+psycopg://andina:local-demo-only@localhost:5432/andina"
    redis_url: str = "redis://localhost:6379/0"
    upload_dir: Path = Path("uploads")
    model_cache_dir: Path = Path("model-cache")
    llm_provider: Literal["mock", "gemini"] = "mock"
    gemini_api_key: SecretStr = SecretStr("")
    gemini_model: str = "gemini-3.5-flash-lite"
    embedding_provider: Literal["fastembed", "hash"] = "fastembed"
    similarity_threshold: float = Field(default=0.80, ge=-1, le=1)
    top_k: int = Field(default=5, ge=1, le=10)
    chunk_tokens: int = Field(default=400, ge=20, le=480)
    chunk_overlap: int = Field(default=60, ge=0)
    llm_timeout_seconds: int = Field(default=30, ge=1, le=90)
    otel_enabled: bool = True
    otel_exporter_otlp_endpoint: str = "http://localhost:4318"

    @model_validator(mode="after")
    def validate_configuration(self) -> "Settings":
        if self.llm_provider == "gemini" and not self.gemini_api_key.get_secret_value():
            raise ValueError("GEMINI_API_KEY es obligatoria cuando LLM_PROVIDER=gemini")
        if self.chunk_overlap >= self.chunk_tokens:
            raise ValueError("CHUNK_OVERLAP debe ser menor que CHUNK_TOKENS")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
