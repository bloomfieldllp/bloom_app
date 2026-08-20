import os
import sys
import platform
from pydantic_settings import BaseSettings, SettingsConfigDict

def get_default_sqlite_path() -> str:
    if os.environ.get("VERCEL") is not None:
        return "bloom_local.db"
    if platform.system() == "Windows":
        app_data = os.environ.get("APPDATA")
        if app_data:
            dir_path = os.path.join(app_data, "BloomOperator")
            try:
                os.makedirs(dir_path, exist_ok=True)
                return os.path.join(dir_path, "bloom_local.db")
            except Exception:
                pass
    return "bloom_local.db"

def get_default_log_dir() -> str:
    if platform.system() == "Windows":
        app_data = os.environ.get("APPDATA")
        if app_data:
            dir_path = os.path.join(app_data, "BloomOperator", "logs")
            try:
                os.makedirs(dir_path, exist_ok=True)
                return dir_path
            except Exception:
                pass
    return "logs"

class Settings(BaseSettings):
    MONGODB_URI: str = "mongodb+srv://bloom_id_app:Swami2003@cluster0.lbhnhkh.mongodb.net/?appName=Cluster0"
    MONGODB_DATABASE: str = "bloom_id_card"
    SECRET_KEY: str = "super-secret-key-change-in-production"
    SESSION_COOKIE_NAME: str = "bloom_session"
    APP_ENV: str = "development"
    IS_LOCAL_OPERATOR: bool = os.environ.get("VERCEL") is None
    REMOTE_SERVER_URL: str = "https://bloom-app-orcin.vercel.app"  # Fallback target URL
    SQLITE_DB_PATH: str = get_default_sqlite_path()
    LOG_DIR: str = get_default_log_dir()

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()


