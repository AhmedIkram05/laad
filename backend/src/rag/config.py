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

        self.primary_model: str = os.getenv("RAG_PRIMARY_MODEL", "gemini-2.0-flash")
        self.fallback_model: str = os.getenv("RAG_FALLBACK_MODEL", "groq/llama-3.1-70b-versatile")

        self.chroma_host: str = os.getenv("CHROMA_HOST", "localhost")
        try:
            self.chroma_port: int = int(os.getenv("CHROMA_PORT", "8001"))
        except (ValueError, TypeError):
            logger.warning("Invalid CHROMA_PORT, defaulting to 8001")
            self.chroma_port = 8001
        self.chroma_collection: str = os.getenv("CHROMA_COLLECTION", "atm_logs")

        try:
            self.retrieval_top_k: int = int(os.getenv("RAG_TOP_K", "5"))
            self.self_consistency_samples: int = int(os.getenv("RAG_SAMPLES", "3"))
            self.temperature: float = float(os.getenv("RAG_TEMPERATURE", "0.6"))
            self.confidence_high_threshold: float = float(os.getenv("CONF_HIGH", "0.8"))
            self.confidence_medium_threshold: float = float(os.getenv("CONF_MEDIUM", "0.5"))
        except (ValueError, TypeError):
            logger.warning("Invalid numeric config value, using defaults")
            self.retrieval_top_k = 5
            self.self_consistency_samples = 3
            self.temperature = 0.6
            self.confidence_high_threshold = 0.8
            self.confidence_medium_threshold = 0.5

        self.calibration_enabled: bool = os.getenv("RAG_CALIBRATION_ENABLED", "true").lower() == "true"

        self._check_configured()

    def _check_configured(self) -> None:
        """Log warning if RAG is not fully configured."""
        if not self.openrouter_api_key:
            logger.warning("OPENROUTER_API_KEY not set - RAG diagnostic assistant will not be available")

    @property
    def is_configured(self) -> bool:
        """Check if RAG is configured with at least one API key."""
        return bool(self.gemini_api_key or self.groq_api_key or self.openrouter_api_key)

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return os.getenv("ENV", "development") == "production"


config = RAGConfig()