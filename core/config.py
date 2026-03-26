from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Supabase
    SUPABASE_URL: str
    SUPABASE_SERVICE_KEY: str

    # n8n
    N8N_BASE_URL: str                  # e.g. https://n8n.yourname.render.com
    N8N_WEBHOOK_SECRET: str            # shared secret for backend ↔ n8n auth

    # Self-reference (for building callback_url sent to n8n)
    BACKEND_URL: str

    # OpenAI — used for embeddings (text-embedding-3-small)
    OPENAI_API_KEY: str

    # LiteLLM
    LITELLM_URL: str = ""
    LITELLM_API_KEY: str = ""

    # CORS — comma-separated list of allowed frontend origins
    ALLOWED_ORIGINS: str = "http://localhost:3000"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()