from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

load_dotenv()



class Settings(BaseSettings):
    """
    全局配置管理类 (Global Configuration)
    基于 Pydantic-Settings 实现，自动从 .env 文件读取并校验环境变量。
    """
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # 1. 应用基础配置 (App Basics)
    app_env: str = "local"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://localhost:5174",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:5174",
        ]
    )

    # 2. 大模型与推理引擎配置 (LLM & Inference)
    vllm_base_url: str = "http://127.0.0.1:8001/v1"
    vllm_model: str = "Qwen2.5-7B-Instruct"
    vllm_api_key: str = "EMPTY"
    vllm_timeout_seconds: float = 120
    llm_context_window_chars: int = 24_000  # Token 爆显存防御边界 (Context Truncation Limit)
    llm_max_output_tokens: int = 2048

    # 3. 智能体与图状态机配置 (Agent & Graph)
    max_agent_steps: int = 12         # 主控路由器的最大跳转次数 (Global Circuit Breaker)
    max_reflexion_steps: int = 2      # 单节点最大反思重试次数 (Reflexion Circuit Breaker)
    sql_require_hitl: bool = True     # 开启 HITL (Human-in-the-Loop) 人机协同审批拦截
    allow_write_sql: bool = False     # 数据库写保护开关 (Database Write Protection)

    # 4. 存储与分级缓存架构 (Storage & Tiered Cache)
    redis_url: str | None = "redis://localhost:6379/0"  # 热数据层 (Hot-tier State Checkpointer)
    postgres_dsn: str = "postgresql://postgres:postgres@localhost:5432/agentic_datalab"  # PostgreSQL 数据库连接
    checkpoint_ttl_seconds: int = 86_400                # 会话快照默认过期时间 (1天)
    data_root: Path = Path("./storage")                 # 物理文件存储根目录
    hot_dataset_max_mb: int = 64                        # 内存中允许的最大数据集大小，超限自动落盘
    cold_dataset_format: str = "parquet"                # 冷数据集高压缩比格式

    # 6. JWT 认证配置 (JWT Authentication)
    jwt_secret_key: str = Field(
        default="your-secret-key-change-this-in-production-min-32-chars",
        description="JWT secret key for token signing (must be at least 32 characters)"
    )
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60 * 24 * 7  # 7 天

    # 5. AutoML 与机器学习实验追踪配置 (AutoML & MLflow)
    mlflow_tracking_uri: str = "sqlite:///./storage/mlflow.db"
    mlflow_artifact_root: str = "./storage/mlflow_artifacts"
    mlflow_experiment_name: str = "Agentic-DataLab"
    h2o_max_runtime_seconds: int = 300      # H2O 训练最长硬超时时间 (Training Hard Timeout)
    h2o_outer_timeout_seconds: int = 360    # 容器执行超时时间
    h2o_max_models: int = 8                 # 模型搜索池最大容量

    def __init__(self, **kwargs):
        """初始化配置并验证安全设置"""
        super().__init__(**kwargs)
        self._validate_jwt_secret()
        self.ensure_dirs()

    def _validate_jwt_secret(self) -> None:
        """
        验证 JWT 密钥安全性
        检测是否使用默认密钥或弱密钥
        """
        dangerous_patterns = [
            "your-secret-key",
            "change-this",
            "secret-key",
            "test-secret",
            "dev-secret",
            "example",
        ]

        jwt_lower = self.jwt_secret_key.lower()
        for pattern in dangerous_patterns:
            if pattern in jwt_lower:
                raise ValueError(
                    f"\n{'='*70}\n"
                    f"🚨 SECURITY ERROR: Dangerous JWT secret key detected!\n"
                    f"{'='*70}\n"
                    f"The current JWT_SECRET_KEY contains '{pattern}' which is insecure.\n"
                    f"\n"
                    f"To fix this:\n"
                    f"1. Generate a secure secret key:\n"
                    f"   python backend/scripts/generate_secret.py\n"
                    f"\n"
                    f"2. Or use Python directly:\n"
                    f"   python -c \"import secrets; print(secrets.token_urlsafe(32))\"\n"
                    f"\n"
                    f"3. Update your .env file with the generated key:\n"
                    f"   JWT_SECRET_KEY=<your-generated-key>\n"
                    f"{'='*70}\n"
                )

        if len(self.jwt_secret_key) < 32:
            raise ValueError(
                f"\n{'='*70}\n"
                f"🚨 SECURITY ERROR: JWT secret key is too short!\n"
                f"{'='*70}\n"
                f"The key must contain at least 32 characters.\n"
                f"Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(32))\"\n"
                f"{'='*70}\n"
            )

        # Warn if key looks too simple (all same character, sequential, etc.)
        if len(set(self.jwt_secret_key)) < 10:
            raise ValueError(
                f"\n{'='*70}\n"
                f"🚨 SECURITY ERROR: JWT secret key is too simple!\n"
                f"{'='*70}\n"
                f"The key uses too few unique characters (< 10).\n"
                f"Please generate a cryptographically secure random key.\n"
                f"{'='*70}\n"
            )

    def ensure_dirs(self) -> None:
        """
        初始化系统必须的物理隔离槽位目录
        """
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
    """
    单例模式获取配置对象。
    利用 lru_cache 避免每次注入时重新读取 .env 文件造成的 IO 损耗。
    """
    settings = Settings()
    settings.ensure_dirs()
    return settings
