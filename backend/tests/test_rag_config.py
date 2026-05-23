"""Tests for backend.src.rag.config."""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest


class TestRAGConfig:
    def test_defaults(self):
        with patch.dict(os.environ, {}, clear=True):
            from importlib import reload
            import backend.src.rag.config as cfg
            reload(cfg)
            config = cfg.RAGConfig()
            assert config.confidence_high_threshold == 0.8
            assert config.confidence_medium_threshold == 0.5
            assert config.retrieval_top_k == 10
            assert config.self_consistency_samples == 3
            assert config.temperature == 0.6
            assert config.chunk_truncate_length == 800
            assert config.ollama_model == "gemma4:31b-cloud"
            assert config.ollama_fallback_models == ["nemotron-3-supercloud"]
            assert config.redis_host == "localhost"
            assert config.redis_port == 6379
            assert config.cache_ttl == 300

    def test_env_override(self):
        with patch.dict(os.environ, {
            "RAG_TOP_K": "10",
            "RAG_TEMPERATURE": "0.9",
            "CONF_HIGH": "0.95",
            "REDIS_HOST": "myredis",
            "REDIS_PORT": "6380",
            "REDIS_CACHE_TTL": "600",
            "OLLAMA_MODEL": "llama3",
        }, clear=True):
            from importlib import reload
            import backend.src.rag.config as cfg
            reload(cfg)
            config = cfg.RAGConfig()
            assert config.retrieval_top_k == 10
            assert config.temperature == 0.9
            assert config.confidence_high_threshold == 0.95
            assert config.redis_host == "myredis"
            assert config.redis_port == 6380
            assert config.cache_ttl == 600
            assert config.ollama_model == "llama3"

    def test_is_configured_false_no_keys(self):
        with patch.dict(os.environ, {}, clear=True):
            from importlib import reload
            import backend.src.rag.config as cfg
            reload(cfg)
            config = cfg.RAGConfig()
            assert config.is_configured is False

    @pytest.mark.parametrize("key", ["OPENROUTER_API_KEY", "OLLAMA_API_KEY"])
    def test_is_configured_with_any_key(self, key):
        with patch.dict(os.environ, {key: "test-key"}, clear=True):
            from importlib import reload
            import backend.src.rag.config as cfg
            reload(cfg)
            config = cfg.RAGConfig()
            assert config.is_configured is True
