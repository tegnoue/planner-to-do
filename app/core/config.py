from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://planner:planner@localhost:5432/planner"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
