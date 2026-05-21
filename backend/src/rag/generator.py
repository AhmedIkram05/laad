"""RAG generator with Agentic RAG capabilities.

Features:
- Self-consistency scoring via multi-sample generation (Wang et al. 2022)
- LLM verbalized confidence estimation
- Reflexion / self-critique (two-pass: generate → critique → regenerate)
- Citation grounding verification
- Structured JSON output
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Tuple

from backend.src.rag.llm_client import get_llm_client, LLMResponse
from backend.src.rag.retriever import RetrievedChunk
from backend.src.rag.config import config
from backend.src.rag.utils import QueryType

logger = logging.getLogger(__name__)

_BOLD_HEADING_RE = re.compile(r'^\*{2}.*?\*{2}\s*$', re.MULTILINE)
_HASH_HEADING_RE = re.compile(r'^#{1,6}\s+\S', re.MULTILINE)
_LIST_ITEM_RE = re.compile(r'^(\s*[-*+] |\s*\d+[.)]\s)', re.MULTILINE)


def _normalize_markdown_spacing(text: str) -> str:
    """Normalize blank lines in markdown for proper ReactMarkdown/Prose rendering.

    Ensures:
    - Blank line before **bold** headings
    - Blank line before # markdown headings
    - Blank line between paragraphs (text blocks separated by single newline)
    - Blank line before list items
    - No more than one blank line in a row
    """
    if not text:
        return text

    lines = text.split('\n')
    result: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.rstrip()
        is_empty = stripped == ''

        is_bold_heading = bool(_BOLD_HEADING_RE.match(stripped))
        is_hash_heading = bool(_HASH_HEADING_RE.match(stripped))
        is_list_item = bool(_LIST_ITEM_RE.match(stripped))

        if is_bold_heading or is_hash_heading or is_list_item:
            if result and result[-1].strip() != '':
                result.append('')

        result.append(line)

        if (is_bold_heading or is_hash_heading) and i + 1 < len(lines) and lines[i + 1].strip() != '':
            result.append('')

        i += 1

    cleaned = '\n'.join(result)
    while '\n\n\n' in cleaned:
        cleaned = cleaned.replace('\n\n\n', '\n\n')

    return cleaned.strip()


@dataclass
class GeneratedResponse:
    """Generated response with sources and agentic metadata."""
    text: str
    sources: list[RetrievedChunk]
    model: str
    raw_response: dict
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    self_consistency_score: Optional[float] = None
    verbalized_confidence: Optional[float] = None
    grounding_score: Optional[float] = None
    critique_text: Optional[str] = None
    was_revised: bool = False
    cross_encoder_used: bool = False


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


def _compute_text_similarity(text_a: str, text_b: str) -> float:
    """Compute normalized text similarity using character n-gram overlap.

    Uses 3-gram Jaccard similarity as a lightweight proxy for semantic
    similarity without requiring an embedding model. Suitable for measuring
    self-consistency between generated responses.
    """
    def _ngrams(t: str, n: int = 3) -> set[str]:
        t = t.lower().strip()
        return {t[i:i+n] for i in range(len(t) - n + 1)}

    grams_a = _ngrams(text_a)
    grams_b = _ngrams(text_b)

    if not grams_a or not grams_b:
        return 0.0

    intersection = grams_a & grams_b
    union = grams_a | grams_b
    return len(intersection) / len(union)


def _extract_entities(text: str) -> dict[str, list[str]]:
    """Extract entities (ATM IDs, error codes, anomaly types, correlation IDs) from text."""
    entities: dict[str, list[str]] = {
        "atm_ids": list(set(re.findall(r'ATM[-_][A-Z]{2}[-_]\d{4}|ATM[-_]\d{4}|ATM-\d{1,2}', text, re.IGNORECASE))),
        "error_codes": list(set(re.findall(r'ERR[-_]\d{4}', text, re.IGNORECASE))),
        "anomaly_types": list(set(re.findall(r'\b(A[1-7])\b', text))),
        "correlation_ids": list(set(re.findall(r'corr[-_][a-z0-9]+[-_][a-z0-9]+[-_][a-z0-9]+[-_][a-z0-9]+', text, re.IGNORECASE))),
    }
    return entities


def _check_citations(answer: str, chunks: list[RetrievedChunk]) -> float:
    """Verify that entities cited in the answer exist in the source chunks.

    Returns grounding_score = grounded_claims / total_claims (1.0 if no claims).
    """
    cited = _extract_entities(answer)
    total_claims = sum(len(v) for v in cited.values())

    if total_claims == 0:
        return 1.0

    chunk_text = " ".join(c.text for c in chunks).lower()
    grounded = 0

    for category, entities in cited.items():
        for entity in entities:
            if entity.lower() in chunk_text:
                grounded += 1

    return grounded / total_claims


class RAGGenerator:
    """Generates diagnostic responses using Agentic RAG pattern.

    Supports self-consistency sampling, verbalized confidence estimation,
    reflexion (self-critique), and citation grounding verification.
    """

    def __init__(self):
        self.llm_client = get_llm_client()

    def generate(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        include_sources: bool = True,
        query_type: QueryType = QueryType.DIAGNOSTIC,
        enable_reflexion: Optional[bool] = None,
        enable_citation_grounding: Optional[bool] = None,
        enable_self_consistency: Optional[bool] = None,
    ) -> GeneratedResponse:
        """Generate response with optional Agentic RAG enhancements."""
        if enable_reflexion is None:
            enable_reflexion = config.reflexion_enabled
        if enable_citation_grounding is None:
            enable_citation_grounding = config.citation_grounding_enabled
        if enable_self_consistency is None:
            enable_self_consistency = config.self_consistency_enabled

        if not chunks:
            return GeneratedResponse(
                text="I don't have enough context to answer your question. Please try again or rephrase.",
                sources=[],
                model="none",
                raw_response={},
            )

        context = self._build_context(chunks, query_type)
        system_prompt = _get_system_prompt_for_query_type(query_type)

        self_consistency_score = None
        samples = []
        if enable_self_consistency:
            self_consistency_score, samples = self._compute_self_consistency(
                query, context, system_prompt, query_type,
            )

        if samples:
            response = self._build_response_from_text(samples[0])
        else:
            response = self._generate_single(query, context, system_prompt, query_type)

        if enable_reflexion and response.text:
            critique = self._critique_response(query, context, response.text, system_prompt)
            if critique:
                response = self._regenerate(query, context, system_prompt, query_type, response.text, critique)

        verbalized_confidence = None
        if enable_self_consistency and response.text:
            verbalized_confidence = self._estimate_verbalized_confidence(query, context, response.text, system_prompt)

        grounding_score = None
        if enable_citation_grounding and response.text:
            grounding_score = _check_citations(response.text, chunks)

        cross_encoder_used = getattr(chunks[0], 'confidence_score', 0) > 0 if chunks else False

        return GeneratedResponse(
            text=_normalize_markdown_spacing(response.text),
            sources=chunks[:5],
            model=response.model,
            raw_response=response.raw_response,
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            self_consistency_score=self_consistency_score,
            verbalized_confidence=verbalized_confidence,
            grounding_score=grounding_score,
            critique_text=response.text if enable_reflexion else None,
            was_revised=enable_reflexion and bool(critique) if enable_reflexion else False,
            cross_encoder_used=cross_encoder_used,
        )

    def _generate_single(
        self,
        query: str,
        context: str,
        system_prompt: str,
        query_type: QueryType = QueryType.DIAGNOSTIC,
        temperature: Optional[float] = None,
    ) -> LLMResponse:
        """Generate a single response from the LLM."""
        prompt = self._build_prompt(query, context, query_type)
        try:
            return self.llm_client.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=temperature if temperature is not None else config.temperature,
            )
        except Exception as e:
            logger.error(f"Generation failed: {e}")
            fallback_text = self._generate_fallback(query, chunks=[], query_type=query_type)
            return LLMResponse(
                text=fallback_text,
                raw_response={},
                model="fallback-template",
                finish_reason="fallback",
            )

    def _build_response_from_text(self, text: str) -> LLMResponse:
        """Build an LLMResponse from pre-generated text."""
        return LLMResponse(
            text=text,
            raw_response={},
            model=config.primary_model or "unknown",
            finish_reason="STOP",
        )

    def _compute_self_consistency(
        self,
        query: str,
        context: str,
        system_prompt: str,
        query_type: QueryType,
        num_samples: int = 3,
    ) -> Tuple[Optional[float], list[str]]:
        """Compute self-consistency score by generating multiple samples in parallel.

        Uses the approach from Wang et al. 2022: generate N diverse responses,
        compute pairwise similarity, and return average. High similarity indicates
        high confidence; low similarity suggests ambiguous queries.

        Returns (score, sample_texts) where the first sample can be reused as the
        primary response to avoid a wasted 4th generation call.
        """
        samples: list[str] = []
        prompt = self._build_prompt(query, context, query_type)

        with ThreadPoolExecutor(max_workers=num_samples) as executor:
            futures = [
                executor.submit(
                    self.llm_client.generate,
                    prompt=prompt,
                    system_prompt=system_prompt,
                    temperature=0.7,
                )
                for _ in range(num_samples)
            ]
            for future in as_completed(futures):
                try:
                    result = future.result()
                    if result.text:
                        samples.append(result.text)
                except Exception:
                    continue

        if not samples:
            return None, samples

        logger.info(f"Generated {len(samples)} self-consistency samples in parallel")

        if len(samples) < 2:
            return None, samples

        pairwise_scores = []
        for i in range(len(samples)):
            for j in range(i + 1, len(samples)):
                score = _compute_text_similarity(samples[i], samples[j])
                pairwise_scores.append(score)

        consistency = sum(pairwise_scores) / len(pairwise_scores)
        logger.info(f"Self-consistency score: {consistency:.3f} across {len(samples)} samples ({len(pairwise_scores)} pairs)")
        return round(consistency, 3), samples

    def _estimate_verbalized_confidence(
        self,
        query: str,
        context: str,
        answer: str,
        system_prompt: str,
    ) -> Optional[float]:
        """Ask the LLM to rate its own confidence that the answer is supported by context."""
        confidence_prompt = f"""Based on the provided log context, rate your confidence that the following answer is fully supported by the context.

Context:
{context}

Question: {query}

Answer:
{answer}

On a scale of 0.0 to 1.0, how confident are you that every claim in the answer is directly supported by the log context?
Consider:
- 1.0 = All claims have direct evidence in the context
- 0.7 = Most claims supported, minor inferences
- 0.5 = Some claims supported, significant inference
- 0.3 = Few claims supported, mostly inference
- 0.0 = No claims supported by the context

Return ONLY a single number between 0.0 and 1.0. No explanation."""
        try:
            conf_response = self.llm_client.generate(
                prompt=confidence_prompt,
                system_prompt=system_prompt,
                temperature=0.1,
                max_tokens=10,
            )
            match = re.search(r'([01]\.\d+|0|1(?:\.0)?)', conf_response.text.strip())
            if match:
                confidence = float(match.group(1))
                confidence = max(0.0, min(1.0, confidence))
                logger.info(f"Verbalized confidence: {confidence:.3f}")
                return round(confidence, 3)
        except Exception as e:
            logger.warning(f"Verbalized confidence estimation failed: {e}")
        return None

    def _critique_response(
        self,
        query: str,
        context: str,
        answer: str,
        system_prompt: str,
    ) -> Optional[str]:
        """Critique the generated answer for unsupported claims.

        Returns critique text if issues found, None if answer looks sound.
        """
        critique_prompt = f"""You are a quality assurance reviewer for an ATM diagnostic system. Critically evaluate the following answer.

Context (source log data):
{context}

Question: {query}

Answer to review:
{answer}

Identify any claims, statements, or recommendations in the answer that are NOT directly supported by the provided context.
Be strict: if the context doesn't contain the evidence for a claim, flag it.

If ALL claims are supported by the context, respond with: "NO_ISSUES_FOUND"
If you find unsupported claims, list each one with:
- The unsupported claim
- Why it lacks evidence in the context"""
        try:
            critique_response = self.llm_client.generate(
                prompt=critique_prompt,
                system_prompt=system_prompt,
                temperature=0.2,
            )
            critique_text = critique_response.text.strip()
            if "NO_ISSUES_FOUND" in critique_text:
                logger.info("Reflexion: no issues found in generated answer")
                return None
            logger.warning(f"Reflexion: critique identified issues in answer")
            return critique_text
        except Exception as e:
            logger.warning(f"Self-critique failed: {e}")
            return None

    def _regenerate(
        self,
        query: str,
        context: str,
        system_prompt: str,
        query_type: QueryType,
        original_answer: str,
        critique: str,
    ) -> LLMResponse:
        """Regenerate an answer addressing the critique."""
        regenerate_prompt = f"""The previous answer had issues identified by quality review. Generate a corrected answer.

Context:
{context}

Question: {query}

Previous answer: {original_answer}

Critique of previous answer:
{critique}

Generate a corrected answer that addresses each issue in the critique. Ensure every claim is directly supported by the context.
If the context doesn't contain enough information to fully answer the question, acknowledge the limitation."""
        logger.info("Reflexion: regenerating answer based on critique")
        try:
            return self.llm_client.generate(
                prompt=regenerate_prompt,
                system_prompt=system_prompt,
                temperature=0.3,
            )
        except Exception as e:
            logger.warning(f"Regeneration failed: {e}. Using original answer.")
            return LLMResponse(
                text=original_answer,
                raw_response={},
                model=system_prompt,
                finish_reason="fallback",
            )

    def _generate_fallback(self, query: str, chunks: list[RetrievedChunk], query_type: QueryType = QueryType.DIAGNOSTIC) -> str:
        """Generate a basic response from chunks when LLM is unavailable."""
        if not chunks:
            return f"I don't have enough context to answer your question about \"{query}\". Please try again or rephrase."

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
    match = re.search(r'_anomaly_tag["\s:=]+([A-Z]\d+)', chunk.text)
    return match.group(1) if match else None


_generator: Optional[RAGGenerator] = None


def get_generator() -> RAGGenerator:
    """Get singleton generator instance."""
    global _generator
    if _generator is None:
        _generator = RAGGenerator()
    return _generator
