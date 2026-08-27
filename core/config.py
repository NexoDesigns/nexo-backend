from __future__ import annotations
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Supabase
    SUPABASE_URL: str
    SUPABASE_SERVICE_KEY: str

    # n8n
    N8N_BASE_URL: str
    N8N_WEBHOOK_SECRET: str
    N8N_REQUIREMENTS_WEBHOOK_URL: str = ""
    N8N_NORMATIVES_SUGGEST_WEBHOOK_URL: str = ""
    N8N_NORMATIVES_WEBHOOK_URL: str = ""

    # Self-reference (for building callback_url sent to n8n)
    BACKEND_URL: str

    # OpenAI — used for embeddings (text-embedding-3-small)
    OPENAI_API_KEY: str

    # Digikey OAuth2
    DIGIKEY_CLIENT_ID: str = ""
    DIGIKEY_CLIENT_SECRET: str = ""

    # Mouser
    MOUSER_API_KEY: str = ""

    # LiteLLM
    LITELLM_URL: str = ""
    LITELLM_API_KEY: str = ""

    # n8n service-to-service auth (static API key, never expires)
    N8N_SERVICE_API_KEY: str = ""
    N8N_SERVICE_USER_ID: str = ""

    # CORS — comma-separated list of allowed frontend origins
    ALLOWED_ORIGINS: str = "http://localhost:3000,https://mikacelber.github.io"

    # Signing secret for the architecture-editor hand-off link (short-lived,
    # scoped token — separate from Supabase's own JWT secret, which this
    # backend never verifies against, see core/security.py)
    EDITOR_LINK_SECRET: str = ""

    # System Diagram App (architecture-editor), deployed on GitHub Pages
    ARCHITECTURE_EDITOR_URL: str = "https://mikacelber.github.io/architecture-editor/"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
