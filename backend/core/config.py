from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_env: str = "local"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )

    vllm_base_url: str = "http://127.0.0.1:8001/v1"
    vllm_model: str = "Qwen2.5-7B-Instruct"
    vllm_api_key: str = "EMPTY"
    vllm_timeout_seconds: float = 120
    llm_context_window_chars: int = 24_000
    llm_max_output_tokens: int = 2048

    max_agent_steps: int = 12
    max_reflexion_steps: int = 2
    sql_require_hitl: bool = True
    allow_write_sql: bool = False

    redis_url: str | None = "redis://localhost:6379/0"
    postgres_dsn: str | None = None
    checkpoint_ttl_seconds: int = 86_400
    data_root: Path = Path("./storage")
    hot_dataset_max_mb: int = 64
    cold_dataset_format: str = "parquet"

    mlflow_tracking_uri: str = "sqlite:///./storage/mlflow.db"
    mlflow_artifact_root: str = "./storage/mlflow_artifacts"
    mlflow_experiment_name: str = "Agentic-DataLab"
    h2o_max_runtime_seconds: int = 300
    h2o_outer_timeout_seconds: int = 360
    h2o_max_models: int = 8

    def ensure_dirs(self) -> None:
        for sub in (
            self.data_root,
            self.data_root / "hot",
            self.data_root / "cold",
            self.data_root / "projects",
            self.data_root / "artifacts",
            self.data_root / "checkpoints",
            Path(self.mlflow_artifact_root),
        ):
            sub.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
