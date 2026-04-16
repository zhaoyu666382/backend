from pydantic_settings import BaseSettings
from typing import List
from pathlib import Path
import os


class Settings(BaseSettings):

    # ========================
    # 项目路径
    # ========================
    BASE_DIR: Path = Path(__file__).resolve().parent
    DATA_DIR: Path = BASE_DIR / "data"
    UPLOAD_DIR: Path = BASE_DIR / "uploads"
    PEST_UPLOAD_DIR: Path = DATA_DIR / "pest_uploads"
    BLOCKCHAIN_FILE: Path = DATA_DIR / "blockchain_chain.json"

    # ========================
    # 应用基础配置
    # ========================
    APP_NAME: str = "绿色食品交易平台"
    VERSION: str = "1.0.0"
    DEBUG: bool = True
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # ========================
    # CORS配置
    # ========================
    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:5175",
    ]

    # ========================
    # 数据库配置
    # ========================
    DATABASE_PATH: Path = DATA_DIR / "green_food.db"
    DATABASE_URL: str = ""

    # ========================
    # JWT配置
    # ========================
    SECRET_KEY: str = "green-food-demo-secret-key-change-me"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    # ========================
    # 日志配置
    # ========================
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "app.log"

    # ========================
    # 区块链配置
    # ========================
    BLOCKCHAIN_NETWORK: str = "fabric"
    BLOCKCHAIN_CHANNEL: str = "green-food-channel"

    # ========================
    # Redis配置
    # ========================
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0

    # ========================
    # 上传限制
    # ========================
    MAX_UPLOAD_SIZE: int = 10485760

    # ========================
    # AI配置（新增）
    # ========================
    QWEN_API_KEY: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "allow"

    def model_post_init(self, __context):

        # 创建必要目录
        os.makedirs(self.DATA_DIR, exist_ok=True)
        os.makedirs(self.UPLOAD_DIR, exist_ok=True)
        os.makedirs(self.PEST_UPLOAD_DIR, exist_ok=True)

        # 自动生成数据库URL
        db_path = str(self.DATABASE_PATH.resolve())

        if os.name == "nt":
            self.DATABASE_URL = f"sqlite:///{db_path}"
        else:
            self.DATABASE_URL = f"sqlite:////{db_path}"


# 创建配置实例
settings = Settings()