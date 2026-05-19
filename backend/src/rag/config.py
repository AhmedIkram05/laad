"""RAG configuration and environment variables."""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


class RAGConfig:
    """Configuration for RAG diagnostic assistant."""

    def __init__(self):
        self.gemini_api_key: Optional[str] = os.getenv("GEMINI_API_KEY")
        self.groq_api_key: Optional[str] = os.getenv("GROQ_API_KEY")
        self.openrouter_api_key: Optional[str] = os.getenv("OPENROUTER_API_KEY")

        self.ollama_api_key: Optional[str] = os.getenv("OLLAMA_API_KEY")
        self.ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "https://ollama.com")
        self.ollama_model: str = os.getenv("OLLAMA_MODEL", "gemma4:31b-cloud")
        self.ollama_fallback_models: list[str] = [m.strip() for m in os.getenv("OLLAMA_FALLBACK_MODELS", "nemotron-3-supercloud").split(",") if m.strip()]


        self.primary_model: str = os.getenv("RAG_PRIMARY_MODEL", "gemma4:31b-cloud")
        self.fallback_model: str = os.getenv("RAG_FALLBACK_MODEL", "nemotron-3-supercloud")

        self.chroma_host: str = os.getenv("CHROMA_HOST", "localhost")
        try:
            self.chroma_port: int = int(os.getenv("CHROMA_PORT", "8001"))
        except (ValueError, TypeError):
            logger.warning("Invalid CHROMA_PORT, defaulting to 8001")
            self.chroma_port = 8001
        self.chroma_collection: str = os.getenv("CHROMA_COLLECTION", "atm_logs")

        try:
            self.retrieval_top_k: int = int(os.getenv("RAG_TOP_K", "3"))
            self.self_consistency_samples: int = int(os.getenv("RAG_SAMPLES", "1"))
            self.temperature: float = float(os.getenv("RAG_TEMPERATURE", "0.6"))
            self.confidence_high_threshold: float = float(os.getenv("CONF_HIGH", "0.8"))
            self.confidence_medium_threshold: float = float(os.getenv("CONF_MEDIUM", "0.5"))
            self.chunk_truncate_length: int = int(os.getenv("RAG_CHUNK_TRUNCATE", "800"))
            self.error_only: bool = os.getenv("RAG_ERROR_ONLY", "true").lower() == "true"
            self.anomaly_types: list[str] = [t.strip() for t in os.getenv("RAG_ANOMALY_TYPES", "A1,A2,A3,A4,A5,A6,A7,UNKNOWN,NORMAL").split(",") if t.strip()]
            self.most_recent_first: bool = os.getenv("RAG_MOST_RECENT_FIRST", "true").lower() == "true"
        except (ValueError, TypeError):
            logger.warning("Invalid numeric config value, using defaults")
            self.retrieval_top_k = 3
            self.self_consistency_samples = 1
            self.temperature = 0.6
            self.confidence_high_threshold = 0.8
            self.confidence_medium_threshold = 0.5
            self.chunk_truncate_length = 800
            self.error_only = True
            self.anomaly_types = ["A1", "A2", "A3", "A4", "A5", "A6", "A7", "UNKNOWN", "NORMAL"]
            self.most_recent_first = True

        self.redis_host: str = os.getenv("REDIS_HOST", "localhost")
        try:
            self.redis_port: int = int(os.getenv("REDIS_PORT", "6379"))
        except (ValueError, TypeError):
            logger.warning("Invalid REDIS_PORT, defaulting to 6379")
            self.redis_port = 6379
        self.cache_ttl: int = int(os.getenv("REDIS_CACHE_TTL", "300"))

        self._check_configured()

    def _check_configured(self) -> None:
        """Log warning if RAG is not fully configured."""
        if not (self.ollama_api_key or self.openrouter_api_key or self.gemini_api_key or self.groq_api_key):
            logger.warning("No LLM API keys set - RAG diagnostic assistant will not be available")

    @property
    def is_configured(self) -> bool:
        """Check if RAG is configured with at least one API key."""
        return bool(self.ollama_api_key or self.gemini_api_key or self.groq_api_key or self.openrouter_api_key)

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return os.getenv("ENV", "development") == "production"


config = RAGConfig()