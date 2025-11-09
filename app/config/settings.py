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
    openai_api_key: str
    llm_model: str = "gpt-5-mini"  # Fallback for backward compatibility

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

        return self

    # Convenience property for consistency with other flags
    @property
    def enable_supervisor(self) -> bool:
        return bool(self.ENABLE_SUPERVISOR)


def get_settings() -> Settings:
    """Settings instance (cache removed to allow dynamic config changes)"""
    return Settings()
