"""RAG generator for creating diagnostic responses from retrieved context."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from backend.src.rag.llm_client import get_llm_client, LLMResponse
from backend.src.rag.retriever import RetrievedChunk
from backend.src.rag.config import config
from backend.src.rag.utils import QueryType

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


DIAGNOSTIC_PROMPT = """You are an expert ATM diagnostics assistant for a financial institution.
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


TROUBLESHOOTING_PROMPT = """You are an expert ATM troubleshooting assistant for a financial institution.
Your role is to provide step-by-step solutions for ATM issues using log data.

Guidelines:
- Use the provided log context to identify the exact problem
- Provide clear, numbered troubleshooting steps the operator can follow
- Include specific commands, checks, or actions at each step
- If the context doesn't contain enough information, acknowledge uncertainty
- Never make up steps not grounded in the logs
- Format responses as: Problem Summary, Troubleshooting Steps, Expected Outcome

Prioritize:
1. Quick wins (restart, check connections)
2. Safety (don't suggest actions that could damage equipment)
3. Escalation paths for complex issues"""


GENERAL_PROMPT = """You are a helpful ATM system assistant for a financial institution.
Your role is to summarize and explain ATM log data in accessible language.

Guidelines:
- Use the provided context to answer questions
- Explain technical terms when necessary
- Be concise but complete
- If context is limited, provide what's available without speculation
- Format as: Summary, Key Points, Additional Context if needed"""


def _get_system_prompt_for_query_type(query_type: QueryType) -> str:
    """Get the appropriate system prompt based on query type."""
    if query_type == QueryType.DIAGNOSTIC:
        return DIAGNOSTIC_PROMPT
    elif query_type == QueryType.TROUBLESHOOTING:
        return TROUBLESHOOTING_PROMPT
    elif query_type == QueryType.GENERAL:
        return GENERAL_PROMPT
    else:
        return DIAGNOSTIC_PROMPT


class RAGGenerator:
    """Generates diagnostic responses using RAG pattern."""

    def __init__(self):
        self.llm_client = get_llm_client()

    def generate(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        include_sources: bool = True,
        query_type: QueryType = QueryType.DIAGNOSTIC,
    ) -> GeneratedResponse:
        """Generate response from query and retrieved chunks."""
        if not chunks:
            return GeneratedResponse(
                text="I don't have enough context to answer your question. Please try again or rephrase.",
                sources=[],
                model="none",
                raw_response={},
            )

        context = self._build_context(chunks, query_type)
        prompt = self._build_prompt(query, context, query_type)
        system_prompt = _get_system_prompt_for_query_type(query_type)

        try:
            response = self.llm_client.generate(
                prompt=prompt,
                system_prompt=system_prompt,
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
            fallback_text = self._generate_fallback(query, chunks)
            return GeneratedResponse(
                text=fallback_text,
                sources=chunks[:5],
                model="fallback-template",
                raw_response={},
            )

    def _generate_fallback(self, query: str, chunks: list[RetrievedChunk], query_type: QueryType = QueryType.DIAGNOSTIC) -> str:
        """Generate a basic response from chunks when LLM is unavailable."""
        if query_type == QueryType.STATS:
            return self._generate_stats_fallback(chunks)
        
        top_chunks = chunks[:3]
        
        if query_type == QueryType.TROUBLESHOOTING:
            return self._generate_troubleshooting_fallback(query, top_chunks)
        
        summary_parts = [
            f"I found {len(chunks)} relevant log entries for your query: \"{query}\"",
            "",
            "**Pattern Detection:**",
            "",
        ]
        for i, chunk in enumerate(top_chunks, 1):
            text = chunk.text[:200]
            atm = chunk.atm_id or "unknown"
            ts = chunk.timestamp or "unknown time"
            anomaly_tag = _extract_anomaly_tag(chunk)
            tag_label = f" [{anomaly_tag}]" if anomaly_tag else ""
            summary_parts.append(f"{i}. **ATM {atm}**{tag_label} (at {ts}): {text}...")

        summary_parts.extend([
            "",
            "**Severity Assessment:**",
            "",
            f"- {len(chunks)} log entries found across {len(set(c.atm_id for c in chunks if c.atm_id))} ATM(s)",
            f"- Most relevant entry distance: {chunks[0].distance:.3f} (lower = more relevant)",
            "",
            "**Recommended Actions:**",
            "",
            "1. Review the log entries above for error codes and timestamps",
            "2. Check the ATM status dashboard for current operational state",
            "3. Correlate events using the correlation_id if present in logs",
            "4. Escalate to engineering team if critical errors (FATAL/OOM) are detected",
            "",
            "**Note:** The AI response generator is currently experiencing high demand. "
            "The analysis above is based on direct log extraction. "
            "Please try again later for a full AI-generated diagnostic response.",
        ])
        return "\n".join(summary_parts)

    def _generate_stats_fallback(self, chunks: list[RetrievedChunk]) -> str:
        """Generate stats response from chunks when DB is unavailable."""
        from collections import Counter
        atms = [c.atm_id for c in chunks if c.atm_id]
        types = [_extract_anomaly_tag(c) for c in chunks]
        
        lines = [
            "Stats query - direct database access failed. Based on retrieved logs:",
            "",
            f"Total log entries: {len(chunks)}",
        ]
        
        if atms:
            atm_counts = Counter(atms)
            lines.append("")
            lines.append("By ATM:")
            for atm, count in atm_counts.most_common(5):
                lines.append(f"  {atm}: {count}")
        
        if types:
            type_counts = Counter([t for t in types if t])
            if type_counts:
                lines.append("")
                lines.append("By Type:")
                for t, count in type_counts.most_common():
                    lines.append(f"  {t}: {count}")
        
        lines.append("")
        lines.append("Note: This is approximate based on log retrieval. For accurate counts, use the /api/rag/anomalies/stats endpoint.")
        
        return "\n".join(lines)

    def _generate_troubleshooting_fallback(self, query: str, chunks: list[RetrievedChunk]) -> str:
        """Generate troubleshooting response from chunks."""
        lines = [
            f"Found {len(chunks)} relevant log entries for troubleshooting query: \"{query}\"",
            "",
            "**Quick Troubleshooting Steps:**",
            "",
        ]
        
        errors = [c for c in chunks if "error" in c.text.lower() or "fatal" in c.text.lower()]
        
        if errors:
            lines.append("1. Check for recent errors:")
            for chunk in errors[:2]:
                atm = chunk.atm_id or "unknown"
                lines.append(f"   - ATM {atm}: {chunk.text[:100]}...")
        
        lines.extend([
            "",
            "2. Verify ATM status via dashboard",
            "3. Check network connectivity for timeout issues",
            "4. Review cassette status for dispense errors",
            "",
            "**Note:** AI troubleshooting assistant unavailable. Please use dashboard for real-time ATM status.",
        ])
        
        return "\n".join(lines)

    def _build_context(self, chunks: list[RetrievedChunk], query_type: QueryType = QueryType.DIAGNOSTIC) -> str:
        """Build context string from retrieved chunks."""
        truncate_len = config.chunk_truncate_length
        context_parts = []
        for i, chunk in enumerate(chunks, 1):
            truncated_text = chunk.text[:truncate_len]
            context_parts.append(f"[Log Entry {i}]:\n{truncated_text}\n")

        return "\n".join(context_parts)

    def _build_prompt(self, query: str, context: str, query_type: QueryType = QueryType.DIAGNOSTIC) -> str:
        """Build prompt with query and context based on query type."""
        if query_type == QueryType.TROUBLESHOOTING:
            return f"""Based on the following ATM log data, provide troubleshooting steps for the question.

Context:
{context}

Question: {query}

Provide numbered troubleshooting steps the operator can follow."""

        elif query_type == QueryType.GENERAL:
            return f"""Based on the following ATM log data, provide a clear summary for the question.

Context:
{context}

Question: {query}

Provide a concise summary in plain language."""

        return f"""Based on the following ATM log data, please answer the question.

Context:
{context}

Question: {query}

Provide a helpful diagnostic response based on the logs above."""


def _extract_anomaly_tag(chunk: RetrievedChunk) -> Optional[str]:
    """Extract anomaly tag from chunk text if present."""
    import re
    match = re.search(r'_anomaly_tag["\s:=]+([A-Z]\d+)', chunk.text)
    return match.group(1) if match else None


_generator: Optional[RAGGenerator] = None


def get_generator() -> RAGGenerator:
    """Get singleton generator instance."""
    global _generator
    if _generator is None:
        _generator = RAGGenerator()
    return _generator