from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


BACKEND_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_ROOT / ".env")


def _csv(name: str, default: str) -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


class BaseConfig:
    APP_ENV = os.getenv("APP_ENV", "development")
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///hr_policy.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    FRONTEND_ORIGINS = _csv(
        "FRONTEND_ORIGINS",
        "http://127.0.0.1:5173,http://localhost:5173",
    )
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False

    UPLOAD_MAX_MB = int(os.getenv("UPLOAD_MAX_MB", "10"))
    UPLOAD_MAX_BYTES = UPLOAD_MAX_MB * 1024 * 1024
    MAX_CONTENT_LENGTH = UPLOAD_MAX_BYTES + 1024 * 1024
    UPLOAD_FOLDER = str(BACKEND_ROOT / "uploads")
    SERVE_FRONTEND = os.getenv("SERVE_FRONTEND", "false").lower() == "true"
    FRONTEND_DIST_PATH = os.getenv("FRONTEND_DIST_PATH", str(BACKEND_ROOT.parent / "frontend" / "dist"))

    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
    DEEPSEEK_TIMEOUT_SECONDS = float(os.getenv("DEEPSEEK_TIMEOUT_SECONDS", "30"))
    DEEPSEEK_MAX_OUTPUT_TOKENS = int(os.getenv("DEEPSEEK_MAX_OUTPUT_TOKENS", "1600"))
    RETRIEVAL_MIN_VECTOR_SCORE = float(os.getenv("RETRIEVAL_MIN_VECTOR_SCORE", "0.54"))
    CLAIM_EVIDENCE_MIN_SCORE = float(os.getenv("CLAIM_EVIDENCE_MIN_SCORE", "0.50"))

    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")
    EMBEDDING_BACKEND = os.getenv("EMBEDDING_BACKEND", "sentence_transformers")
    CHUNKER_VERSION = os.getenv("CHUNKER_VERSION", "clause-v1")

    JSON_AS_ASCII = False


class DevelopmentConfig(BaseConfig):
    DEBUG = True


class TestingConfig(BaseConfig):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    DEEPSEEK_API_KEY = ""
    WTF_CSRF_ENABLED = False
    EMBEDDING_BACKEND = "hash"
    RETRIEVAL_MIN_VECTOR_SCORE = -1.0
    CLAIM_EVIDENCE_MIN_SCORE = -1.0


class ProductionConfig(BaseConfig):
    DEBUG = False
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"


CONFIGS = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(config_name: str | None = None) -> type[BaseConfig]:
    name = config_name or os.getenv("APP_ENV", "development")
    return CONFIGS.get(name, DevelopmentConfig)
