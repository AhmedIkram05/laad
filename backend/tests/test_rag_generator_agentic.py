"""Tests for Agentic RAG generator features:
self-consistency scoring, verbalized confidence, reflexion, citation grounding.
"""

import pytest
from unittest.mock import MagicMock, patch

from backend.src.rag.retriever import RetrievedChunk


@pytest.fixture
def sample_chunks():
    return [
        RetrievedChunk(
            text="2026-05-15T10:00:00Z [ATM_APP] NETWORK_DISCONNECT: ATM-GB-0001 connection lost | error_code=ERR-0040, response_time_ms=30000",
            chunk_id="chunk_1",
            atm_id="ATM-GB-0001",
            timestamp="2026-05-15T10:00:00Z",
            distance=0.1,
            confidence_score=0.9,
        ),
        RetrievedChunk(
            text="2026-05-15T10:01:00Z [KAFKA] ATM-GB-0001 status: Offline | atm_status=Offline, correlation_id=corr-0030",
            chunk_id="chunk_2",
            atm_id="ATM-GB-0001",
            timestamp="2026-05-15T10:01:00Z",
            distance=0.15,
            confidence_score=0.85,
        ),
    ]


class TestTextSimilarity:
    """Test self-consistency text similarity computation."""

    def test_identical_texts(self):
        from backend.src.rag.generator import _compute_text_similarity
        text = "ATM-GB-0001 has a network timeout error"
        score = _compute_text_similarity(text, text)
        assert score == 1.0

    def test_similar_texts(self):
        from backend.src.rag.generator import _compute_text_similarity
        a = "ATM-GB-0001 has a network timeout error"
        b = "ATM-GB-0001 is experiencing a network timeout"
        score = _compute_text_similarity(a, b)
        assert 0.3 < score < 1.0

    def test_different_texts(self):
        from backend.src.rag.generator import _compute_text_similarity
        a = "ATM-GB-0001 has a network timeout error"
        b = "The weather today is sunny and warm"
        score = _compute_text_similarity(a, b)
        assert score < 0.3

    def test_empty_texts(self):
        from backend.src.rag.generator import _compute_text_similarity
        assert _compute_text_similarity("", "") == 0.0
        assert _compute_text_similarity("hello", "") == 0.0


class TestEntityExtraction:
    """Test entity extraction for citation grounding."""

    def test_extract_atm_ids(self):
        from backend.src.rag.generator import _extract_entities
        text = "ATM-GB-0001 and ATM-0002 are both experiencing issues"
        entities = _extract_entities(text)
        assert "ATM-GB-0001" in entities["atm_ids"]
        assert len(entities["atm_ids"]) >= 1

    def test_extract_error_codes(self):
        from backend.src.rag.generator import _extract_entities
        text = "Error code ERR-0040 detected on ATM-GB-0001"
        entities = _extract_entities(text)
        assert "ERR-0040" in entities["error_codes"]

    def test_extract_anomaly_types(self):
        from backend.src.rag.generator import _extract_entities
        text = "This matches anomaly type A1 and A3"
        entities = _extract_entities(text)
        assert "A1" in entities["anomaly_types"]
        assert "A3" in entities["anomaly_types"]

    def test_extract_correlation_ids(self):
        from backend.src.rag.generator import _extract_entities
        text = "correlation corr-0030-nnet-disc-0001 found"
        entities = _extract_entities(text)
        assert len(entities["correlation_ids"]) >= 1

    def test_no_entities(self):
        from backend.src.rag.generator import _extract_entities
        entities = _extract_entities("Hello, this is a simple question")
        assert all(len(v) == 0 for v in entities.values())


class TestCitationGrounding:
    """Test citation grounding verification."""

    def test_all_claims_grounded(self, sample_chunks):
        from backend.src.rag.generator import _check_citations
        answer = "ATM-GB-0001 has a network disconnect with error ERR-0040"
        score = _check_citations(answer, sample_chunks)
        assert score == 1.0

    def test_no_claims(self, sample_chunks):
        from backend.src.rag.generator import _check_citations
        answer = "This is a general statement with no specific entities"
        score = _check_citations(answer, sample_chunks)
        assert score == 1.0

    def test_unclaimed_entity(self, sample_chunks):
        from backend.src.rag.generator import _check_citations
        answer = "ATM-GB-9999 has an unknown error ERR-9999"
        score = _check_citations(answer, sample_chunks)
        assert score == 0.0

    def test_partial_grounding(self, sample_chunks):
        from backend.src.rag.generator import _check_citations
        answer = "ATM-GB-0001 has error ERR-0040 and also ATM-GB-9999 has error ERR-9999"
        score = _check_citations(answer, sample_chunks)
        assert score == 0.5


class TestGeneratedResponse:
    """Test GeneratedResponse dataclass with new agentic fields."""

    def test_response_with_agentic_fields(self, sample_chunks):
        from backend.src.rag.generator import GeneratedResponse

        response = GeneratedResponse(
            text="Network timeout detected on ATM-GB-0001",
            sources=sample_chunks,
            model="test-model",
            raw_response={},
            self_consistency_score=0.92,
            verbalized_confidence=0.88,
            grounding_score=0.95,
            critique_text="All claims supported",
            was_revised=True,
            cross_encoder_used=True,
        )

        assert response.self_consistency_score == 0.92
        assert response.verbalized_confidence == 0.88
        assert response.grounding_score == 0.95
        assert response.critique_text == "All claims supported"
        assert response.was_revised is True
        assert response.cross_encoder_used is True

    def test_response_default_agentic_fields(self, sample_chunks):
        from backend.src.rag.generator import GeneratedResponse

        response = GeneratedResponse(
            text="Test",
            sources=sample_chunks,
            model="test",
            raw_response={},
        )

        assert response.self_consistency_score is None
        assert response.verbalized_confidence is None
        assert response.grounding_score is None
        assert response.critique_text is None
        assert response.was_revised is False
        assert response.cross_encoder_used is False

    def test_anomaly_tag_extraction(self):
        from backend.src.rag.generator import _extract_anomaly_tag

        chunk = RetrievedChunk(
            text='_anomaly_tag="A1"',
            chunk_id="1",
            atm_id="ATM-GB-0001",
            timestamp="2026-05-15T10:00:00Z",
            distance=0.1,
            confidence_score=0.9,
        )
        tag = _extract_anomaly_tag(chunk)
        assert tag == "A1"


class TestGeneratorFallback:
    """Test generator fallback when LLM is unavailable."""

    @patch("backend.src.rag.generator.config")
    def test_generate_without_chunks(self, mock_config):
        from backend.src.rag.generator import RAGGenerator

        mock_config.reflexion_enabled = False
        mock_config.citation_grounding_enabled = False
        mock_config.self_consistency_enabled = False

        generator = RAGGenerator()
        generator.llm_client = MagicMock()

        response = generator.generate(query="test", chunks=[])

        assert "don't have enough context" in response.text
        assert response.model == "none"

    @patch("backend.src.rag.generator.config")
    def test_generate_fallback_on_llm_failure(self, mock_config, sample_chunks):
        from backend.src.rag.generator import RAGGenerator

        mock_config.reflexion_enabled = False
        mock_config.citation_grounding_enabled = False
        mock_config.self_consistency_enabled = False

        generator = RAGGenerator()
        generator.llm_client = MagicMock()
        generator.llm_client.generate.side_effect = Exception("LLM unavailable")

        response = generator.generate(query="test", chunks=sample_chunks)

        assert response.model == "fallback-template"
        assert len(response.sources) > 0

    def test_generate_stats_fallback(self, sample_chunks):
        from backend.src.rag.generator import RAGGenerator

        generator = RAGGenerator.__new__(RAGGenerator)
        text = generator._generate_stats_fallback(sample_chunks)
        assert "Stats query" in text
        assert "ATM-GB-0001" in text

    def test_generate_troubleshooting_fallback(self, sample_chunks):
        from backend.src.rag.generator import RAGGenerator

        generator = RAGGenerator.__new__(RAGGenerator)
        text = generator._generate_troubleshooting_fallback("error", sample_chunks)
        assert "Troubleshooting Steps" in text
