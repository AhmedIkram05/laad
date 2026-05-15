"""RAG generator for creating diagnostic responses from retrieved context."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from backend.src.rag.llm_client import get_llm_client, LLMResponse
from backend.src.rag.retriever import RetrievedChunk

logger = logging.getLogger(__name__)


@dataclass
class GeneratedResponse:
    """Generated response with sources and metadata."""
    text: str
    sources: list[RetrievedChunk]
    model: str
    raw_response: dict
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None


SYSTEM_PROMPT = """You are an expert ATM diagnostics assistant for a financial institution.
Your role is to help operators and engineers diagnose and resolve ATM issues using log data.

Guidelines:
- Use the provided log context to answer questions accurately
- Be specific about ATM IDs, timestamps, and error codes when available
- Provide actionable troubleshooting steps
- If the context doesn't contain enough information, acknowledge uncertainty
- Never make up information not present in the context
- Format your responses clearly with sections for: Analysis, Root Cause, Recommended Actions

When providing recommendations, always prioritize:
1. Safety and security
2. Minimal service disruption
3. Quick diagnosis steps
4. Escalation paths when needed"""


class RAGGenerator:
    """Generates diagnostic responses using RAG pattern."""

    def __init__(self):
        self.llm_client = get_llm_client()

    def generate(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        include_sources: bool = True,
    ) -> GeneratedResponse:
        """Generate response from query and retrieved chunks."""
        if not chunks:
            return GeneratedResponse(
                text="I don't have enough context to answer your question. Please try again or rephrase.",
                sources=[],
                model="none",
                raw_response={},
            )

        context = self._build_context(chunks)
        prompt = self._build_prompt(query, context)

        try:
            response = self.llm_client.generate(
                prompt=prompt,
                system_prompt=SYSTEM_PROMPT,
            )

            logger.info(f"Generated response using model: {response.model}")

            return GeneratedResponse(
                text=response.text,
                sources=chunks[:5],
                model=response.model,
                raw_response=response.raw_response,
                prompt_tokens=response.prompt_tokens,
                completion_tokens=response.completion_tokens,
            )

        except Exception as e:
            logger.error(f"Generation failed: {e}")
            return GeneratedResponse(
                text="I encountered an error generating your response. Please try again.",
                sources=chunks[:5],
                model="error",
                raw_response={},
            )

    def _build_context(self, chunks: list[RetrievedChunk]) -> str:
        """Build context string from retrieved chunks."""
        context_parts = []
        for i, chunk in enumerate(chunks, 1):
            context_parts.append(f"[Log Entry {i}]:\n{chunk.text}\n")

        return "\n".join(context_parts)

    def _build_prompt(self, query: str, context: str) -> str:
        """Build prompt with query and context."""
        return f"""Based on the following ATM log data, please answer the question.

Context:
{context}

Question: {query}

Provide a helpful diagnostic response based on the logs above."""


_generator: Optional[RAGGenerator] = None


def get_generator() -> RAGGenerator:
    """Get singleton generator instance."""
    global _generator
    if _generator is None:
        _generator = RAGGenerator()
    return _generator