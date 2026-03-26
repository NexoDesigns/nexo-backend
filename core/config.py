from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    supabase_url: str
    supabase_service_key: str
    n8n_base_url: str
    n8n_webhook_secret: str
    litellm_url: str
    litellm_api_key: str

    class Config:
        env_file = ".env"

settings = Settings()