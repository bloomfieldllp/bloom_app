import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    MONGODB_URI: str = "mongodb+srv://bloom_id_app:Swami2003@cluster0.lbhnhkh.mongodb.net/?appName=Cluster0"
    MONGODB_DATABASE: str = "bloom_id_card"
    SECRET_KEY: str = "super-secret-key-change-in-production"
    SESSION_COOKIE_NAME: str = "bloom_session"
    APP_ENV: str = "development"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
