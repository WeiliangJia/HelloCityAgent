from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator
from typing import Optional


class Settings(BaseSettings):
    """Application configuration with type safety"""
    model_config = SettingsConfigDict(
        env_file=".env.local",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    # OpenAI Configuration
    openai_api_key: Optional[str] = None
    llm_model: str = "gpt-5-mini"  # Fallback for backward compatibility
    embeddings_model: str = "text-embedding-3-small"

    # Azure OpenAI Configuration
    azure_openai_api_key: Optional[str] = None
    azure_openai_endpoint: Optional[str] = None
    azure_openai_api_version: str = "2024-02-15-preview"
    azure_openai_chat_deployment: Optional[str] = None
    azure_openai_embeddings_deployment: Optional[str] = None

    # Dual Model Strategy (Chat vs Checklist)
    llm_model_chat: Optional[str] = None           # Fast model for conversation
    llm_model_checklist: Optional[str] = None      # High-quality model for checklist generation
    llm_model_judge: Optional[str] = None          # Lightweight model for routing/decision making
    llm_model_summary: Optional[str] = None        # Model used to summarize search/conversation context

    # Celery Configuration
    celery_broker_url: str = "redis://redis:6379/0"
    celery_result_backend: str = "redis://redis:6379/0"

    # ChromaDB Configuration
    chroma_persist_directory: str = "./chroma_db"
    enable_rag: bool = True
    enable_web_search: bool = True
    ENABLE_SUPERVISOR: bool = True

    @model_validator(mode='after')
    def set_model_defaults(self):
        """Backward compatibility: fall back to llm_model if specific models not set"""
        # If llm_model_chat not explicitly set, use llm_model
        if self.llm_model_chat is None:
            self.llm_model_chat = self.llm_model
            print(f"[CONFIG] llm_model_chat not set, using llm_model: {self.llm_model}")

        # If llm_model_checklist not explicitly set, use llm_model
        if self.llm_model_checklist is None:
            self.llm_model_checklist = self.llm_model
            print(f"[CONFIG] llm_model_checklist not set, using llm_model: {self.llm_model}")

        if self.llm_model_judge is None:
            self.llm_model_judge = self.llm_model_chat or self.llm_model
            print(f"[CONFIG] llm_model_judge not set, using llm_model_chat: {self.llm_model_judge}")

        if self.llm_model_summary is None:
            self.llm_model_summary = self.llm_model_checklist or self.llm_model
            print(f"[CONFIG] llm_model_summary not set, using llm_model_checklist: {self.llm_model_summary}")

        if not self.openai_api_key and not self.azure_openai_api_key:
            raise ValueError(
                "Set OPENAI_API_KEY or AZURE_OPENAI_API_KEY in .env.local (at least one is required)."
            )

        if self.azure_openai_api_key and not self.azure_openai_endpoint:
            raise ValueError("AZURE_OPENAI_ENDPOINT is required when using Azure OpenAI.")

        return self

    # Convenience property for consistency with other flags
    @property
    def enable_supervisor(self) -> bool:
        return bool(self.ENABLE_SUPERVISOR)

    @property
    def use_azure_openai(self) -> bool:
        """Azure OpenAI is active if an endpoint is provided."""
        return bool(self.azure_openai_endpoint)

    @property
    def resolved_api_key(self) -> Optional[str]:
        """Prefer the Azure key when Azure is enabled, otherwise default OpenAI key."""
        return self.azure_openai_api_key or self.openai_api_key


def get_settings() -> Settings:
    """Settings instance (cache removed to allow dynamic config changes)"""
    return Settings()
