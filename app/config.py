from pydantic_settings import BaseSettings
from pydantic import Field, computed_field


class Settings(BaseSettings):
    app_env: str = Field(default="development", alias="APP_ENV")
    api_prefix: str = Field(default="/api", alias="API_PREFIX")
    cors_origins_csv: str | None = Field(default=None, alias="CORS_ORIGINS")
    auth0_domain: str | None = Field(default=None, alias="AUTH0_DOMAIN")
    auth0_audience: str | None = Field(default=None, alias="AUTH0_AUDIENCE")

    model_config = {
        "env_file": ".env",
        "extra": "ignore",
        "populate_by_name": True,
    }

    @computed_field
    @property
    def cors_origins(self) -> list[str]:
        if self.cors_origins_csv:
            return [o.strip() for o in self.cors_origins_csv.split(",") if o.strip()]
        return []


settings = Settings()
