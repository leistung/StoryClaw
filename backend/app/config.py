from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # DB
    database_url: str = "postgresql+asyncpg://storyclaw:storyclaw_dev_pwd@postgres:5432/storyclaw"
    # LangGraph
    langgraph_url: str = "http://langgraph-server:8000"
    # Milvus
    milvus_host: str = "milvus"
    milvus_port: int = 19530
    # Neo4j
    neo4j_uri: str = "bolt://neo4j:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "storyclaw_neo4j_pwd"
    # Auth
    jwt_secret: str = "change-me-in-prod-please-use-a-long-random-string"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 10080
    # App
    mock_payments_enabled: bool = False
    log_level: str = "INFO"
    cors_origins: str = "http://localhost,http://localhost:5173,http://localhost:5174"
    configs_dir: str = "/app/configs"
    # 商业版本 LLM keys（服务端持有）
    openai_api_key: str = ""
    anthropic_api_key: str = ""


settings = Settings()
