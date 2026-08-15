"""RAG configuration and environment variables."""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


class RAGConfig:
    """Configuration for RAG diagnostic assistant."""

    def __init__(self):
        # W&B Serverless Inference (single provider for all LLM calls)
        self.llm_base_url: str = os.getenv(
            "LLM_BASE_URL", "https://api.inference.wandb.ai/v1"
        )
        self.llm_api_key: Optional[str] = os.getenv("LLM_API_KEY") or os.getenv(
            "WANDB_API_KEY"
        )
        self.llm_model: str = os.getenv("LLM_MODEL", "google/gemma-4-31B-it")

        self.chroma_host: str = os.getenv("CHROMA_HOST", "localhost")
        try:
            self.chroma_port: int = int(os.getenv("CHROMA_PORT", "8001"))
        except (ValueError, TypeError):
            logger.warning("Invalid CHROMA_PORT, defaulting to 8001")
            self.chroma_port = 8001
        self.chroma_collection: str = os.getenv("CHROMA_COLLECTION", "atm_logs")

        try:
            self.retrieval_top_k: int = int(os.getenv("RAG_TOP_K", "10"))
            self.self_consistency_samples: int = int(os.getenv("RAG_SAMPLES", "3"))
            self.temperature: float = float(os.getenv("RAG_TEMPERATURE", "0.6"))
            self.confidence_high_threshold: float = float(os.getenv("CONF_HIGH", "0.8"))
            self.confidence_medium_threshold: float = float(
                os.getenv("CONF_MEDIUM", "0.5")
            )
            self.chunk_truncate_length: int = int(
                os.getenv("RAG_CHUNK_TRUNCATE", "800")
            )
            self.error_only: bool = (
                os.getenv("RAG_ERROR_ONLY", "true").lower() == "true"
            )
            self.anomaly_types: list[str] = [
                t.strip()
                for t in os.getenv(
                    "RAG_ANOMALY_TYPES", "A1,A2,A3,A4,A5,A6,A7,UNKNOWN,NORMAL"
                ).split(",")
                if t.strip()
            ]
            self.most_recent_first: bool = (
                os.getenv("RAG_MOST_RECENT_FIRST", "true").lower() == "true"
            )

            self.reflexion_enabled: bool = (
                os.getenv("RAG_REFLEXION", "true").lower() == "true"
            )
            self.citation_grounding_enabled: bool = (
                os.getenv("RAG_CITATION_GROUNDING", "true").lower() == "true"
            )
            self.self_consistency_enabled: bool = (
                os.getenv("RAG_SELF_CONSISTENCY", "true").lower() == "true"
            )
            self.cross_encoder_enabled: bool = (
                os.getenv("RAG_CROSS_ENCODER", "true").lower() == "true"
            )
            self.cross_encoder_model: str = os.getenv(
                "RAG_CROSS_ENCODER_MODEL", "cross-encoder/ms-marco-MiniLM-L-2-v2"
            )
            self.agent_max_rounds: int = int(os.getenv("AGENT_MAX_ROUNDS", "2"))
            self.agent_max_retries: int = int(os.getenv("AGENT_MAX_RETRIES", "1"))
            self.agent_grounding_retry_threshold: float = float(
                os.getenv("AGENT_GROUNDING_RETRY_THRESHOLD", "0.6")
            )
            self.agent_max_llm_calls: int = int(os.getenv("AGENT_MAX_LLM_CALLS", "24"))
            self.hybrid_top_k: int = int(os.getenv("RAG_HYBRID_TOP_K", "5"))
            # 0 disables the client-side global rate limiter (eval runs).
            self.rate_limit_per_min: int = int(os.getenv("RAG_RATE_LIMIT", "20"))
        except (ValueError, TypeError):
            logger.warning("Invalid numeric config value, using defaults")
            self.retrieval_top_k = 10
            self.self_consistency_samples = 1
            self.temperature = 0.6
            self.confidence_high_threshold = 0.8
            self.confidence_medium_threshold = 0.5
            self.chunk_truncate_length = 800
            self.error_only = True
            self.anomaly_types = [
                "A1",
                "A2",
                "A3",
                "A4",
                "A5",
                "A6",
                "A7",
                "UNKNOWN",
                "NORMAL",
            ]
            self.most_recent_first = True
            self.reflexion_enabled = True
            self.citation_grounding_enabled = True
            self.self_consistency_enabled = True
            self.cross_encoder_enabled = True
            self.cross_encoder_model = "cross-encoder/ms-marco-MiniLM-L-2-v2"
            self.agent_max_rounds = 2
            self.agent_max_retries = 1
            self.agent_grounding_retry_threshold = 0.6
            self.agent_max_llm_calls = 24
            self.hybrid_top_k = 5
            self.rate_limit_per_min = 20

        self.redis_host: str = os.getenv("REDIS_HOST", "localhost")
        try:
            self.redis_port: int = int(os.getenv("REDIS_PORT", "6379"))
        except (ValueError, TypeError):
            logger.warning("Invalid REDIS_PORT, defaulting to 6379")
            self.redis_port = 6379
        self.cache_ttl: int = int(os.getenv("REDIS_CACHE_TTL", "300"))

        self.otel_jsonl: Optional[str] = os.getenv("OTEL_JSONL") or None

        self._check_configured()

    def _check_configured(self) -> None:
        """Log warning if RAG is not fully configured."""
        if not (self.llm_api_key):
            logger.warning(
                "No LLM API keys set - RAG diagnostic assistant will not be available"
            )

    @property
    def is_configured(self) -> bool:
        """Check if RAG is configured with at least one API key."""
        return bool(self.llm_api_key)

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return os.getenv("ENV", "development") == "production"


config = RAGConfig()
