from pydantic_settings import BaseSettings
from typing import List
import os

class Settings(BaseSettings):
    app_env: str = os.getenv("APP_ENV", "development")
    api_prefix: str = os.getenv("API_PREFIX", "/api")
    cors_origins: List[str] = []

    class Config:
        env_prefix = ""
        env_file = ".env"

    def __init__(self, **values):
        super().__init__(**values)
        raw = os.getenv("CORS_ORIGINS", "")
        if raw:
            self.cors_origins = [o.strip() for o in raw.split(",") if o.strip()]

settings = Settings()
