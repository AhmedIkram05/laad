"""Vector-search tool: search_knowledge wraps the production RAGRetriever."""
from __future__ import annotations

from backend.src.rag.retriever import get_retriever


def search_knowledge(
    query: str,
    atm_id: str | None = None,
    anomaly_type: str | None = None,
    top_k: int = 5,
    error_only: bool = True,
    temporal_boost: bool = True,
) -> dict:
    """Search the indexed ATM log corpus (Chroma) and return reranked evidence chunks.

    This is the primary retrieval tool. Use it FIRST, in parallel with at most one
    structured tool. Pass the ATM id from the conversation scope when the user's
    question concerns a specific machine; pass anomaly_type (A1-A7) when the user
    asks about a specific anomaly class. Results are reranked by a cross-encoder
    and include a confidence_score per chunk.

    Args:
        query: The natural-language search question.
        atm_id: Optional ATM id to scope results to (e.g. ATM-GB-0001).
        anomaly_type: Optional anomaly class filter (A1..A7).
        top_k: Number of chunks to return (1-20, default 5).
        error_only: Only return error/fault-related chunks (default True).
        temporal_boost: Boost recency when scoring (default True).

    Returns:
        {"chunks": [{"text", "chunk_id", "atm_id", "timestamp", "confidence_score"}], "count": N}
    """
    retriever = get_retriever()
    if retriever is None or retriever.collection is None:
        return {"error": "vector store unavailable", "chunks": [], "count": 0}
    chunks = retriever.retrieve(
        query,
        atm_id=atm_id,
        top_k=max(1, min(top_k, 20)),
        anomaly_type=anomaly_type,
        error_only=error_only,
        temporal_boost=temporal_boost,
    )
    return {
        "chunks": [
            {
                "text": c.text,
                "chunk_id": c.chunk_id,
                "atm_id": c.atm_id,
                "timestamp": c.timestamp,
                "confidence_score": c.confidence_score,
            }
            for c in chunks
        ],
        "count": len(chunks),
    }