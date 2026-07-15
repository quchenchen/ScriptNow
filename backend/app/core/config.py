"""Application Settings"""
import os


class Settings:
    APP_NAME = "ScriptFlow"
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-in-production")
    ALGORITHM = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

    # LLM
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "dashscope")
    LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-v4-pro")
    DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
    DASHSCOPE_BASE_URL = os.getenv("DASHSCOPE_BASE_URL",
        "https://dashscope.aliyuncs.com/compatible-mode/v1")

    # AgentScope
    AGENTSCOPE_MODEL_CONFIG = "dashscope_deepseek"


settings = Settings()
