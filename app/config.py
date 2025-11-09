from pydantic import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./payments.db"
    ENV: str = "dev"
    MOCK_GATEWAY: bool = True
    STRIPE_API_KEY: str | None = None
    STRIPE_WEBHOOK_SECRET: str | None = None

settings = Settings()
