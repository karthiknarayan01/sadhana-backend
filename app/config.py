from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Elasticsearch is reachable only over the private VPC in production
    # (see infra/terraform) — this is never a public hostname.
    es_host: str = "http://localhost:9200"
    es_api_key: str | None = None
    es_index: str = "shlokas"


settings = Settings()
