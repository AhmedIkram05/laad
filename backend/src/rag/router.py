"""FastAPI router for RAG diagnostic assistant."""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from datetime import datetime
from typing import Optional

import redis
from fastapi import APIRouter, Depends, HTTPException, Request, status

from backend.src.database.connection import get_cursor
from backend.src.rag.schemas import (
    RAGQueryRequest,
    RAGQueryResponse,
    RAGFeedbackRequest,
    RAGFeedbackResponse,
    RAGHistoryResponse,
    RAGStatsResponse,
    SourceChunk,
)
from backend.src.rag.retriever import get_retriever
from backend.src.rag.generator import get_generator
from backend.src.rag.uncertainty import get_uncertainty_estimator
from backend.src.rag.cache import get_cached_response, set_cached_response
from backend.src.rag.utils import sanitize_query, extract_atm_id_from_query, detect_query_intent
from backend.src.auth.auth_router import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/rag", tags=["RAG"])

RATE_LIMIT_WINDOW = 60
RATE_LIMIT_MAX_REQUESTS = 10
_query_timestamps: dict[str, list[float]] = defaultdict(list)

_redis_rate_limit_client: Optional[redis.Redis] = None


def _get_redis_client() -> Optional[redis.Redis]:
    """Get Redis client for distributed rate limiting."""
    global _redis_rate_limit_client
    if _redis_rate_limit_client is None:
        try:
            _redis_rate_limit_client = redis.Redis(
                host=config.redis_host,
                port=config.redis_port,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            _redis_rate_limit_client.ping()
        except Exception:
            _redis_rate_limit_client = None
    return _redis_rate_limit_client


def _check_rate_limit(user_key: str) -> None:
    """Check if user has exceeded rate limit. Uses Redis if available, falls back to in-memory."""
    client = _get_redis_client()
    now = time.time()

    if client is not None:
        try:
            key = f"rag:ratelimit:{user_key}"
            count = client.incr(key)
            if count == 1:
                client.expire(key, RATE_LIMIT_WINDOW)
            if count > RATE_LIMIT_MAX_REQUESTS:
                ttl = client.ttl(key)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Rate limit exceeded ({RATE_LIMIT_MAX_REQUESTS} requests per minute). Please wait {ttl}s before trying again.",
                )
            return
        except HTTPException:
            raise
        except Exception:
            pass

    cutoff = now - RATE_LIMIT_WINDOW
    _query_timestamps[user_key] = [t for t in _query_timestamps[user_key] if t > cutoff]
    if len(_query_timestamps[user_key]) >= RATE_LIMIT_MAX_REQUESTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded ({RATE_LIMIT_MAX_REQUESTS} requests per minute). Please wait before trying again.",
        )
    _query_timestamps[user_key].append(now)


@router.post("/query", response_model=RAGQueryResponse)
async def query(
    request: RAGQueryRequest,
    req: Request,
    current_user: dict = Depends(get_current_user),
):
    """Query the diagnostic assistant with uncertainty estimation."""
    try:
        user_key = current_user.get("sub", "anonymous")
        _check_rate_limit(user_key)

        sanitized_query = sanitize_query(request.query)
        atm_id = request.atm_id or extract_atm_id_from_query(request.query)
        anomaly_type = _extract_anomaly_type_from_query(request.query)
        
        query_intent = detect_query_intent(request.query)
        error_only = query_intent.error_only if request.error_only is None else request.error_only
        most_recent_first = query_intent.most_recent_first if request.most_recent_first is None else request.most_recent_first

        cached = get_cached_response(sanitized_query)
        if cached:
            return RAGQueryResponse(
                query_id=cached.get("query_id", 0),
                answer=cached["answer"],
                sources=[
                    SourceChunk(
                        text=s["text"],
                        chunk_id=s["chunk_id"],
                        atm_id=s["atm_id"],
                        timestamp=s["timestamp"],
                        confidence_score=s["confidence_score"],
                    )
                    for s in cached.get("sources", [])
                ],
                uncertainty_score=cached.get("uncertainty_score", 0.5),
                confidence_level=cached.get("confidence_level", "medium"),
                is_calibrated=cached.get("is_calibrated", False),
                is_uncertain=cached.get("is_uncertain", False),
                recommendation=cached.get("recommendation", "Review recommended"),
                model_used="cache",
            )

        retriever = get_retriever()
        generator = get_generator()
        uncertainty_estimator = get_uncertainty_estimator()

        chunks = retriever.retrieve(
            query=sanitized_query,
            atm_id=atm_id,
            top_k=request.top_k,
            anomaly_type=anomaly_type,
            temporal_boost=True,
            error_only=error_only,
            most_recent_first=most_recent_first,
        )

        if not chunks:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No relevant logs found for your query. Try rephrasing or check if the data generator is running.",
            )

        response = generator.generate(
            query=request.query,
            chunks=chunks,
        )

        uncertainty = None
        if request.include_uncertainty:
            uncertainty = uncertainty_estimator.estimate(
                query=request.query,
                chunks=chunks,
            )

        user_id = _get_user_id_from_username(current_user.get("sub", ""))
        query_id = _save_query_history(
            user_id=user_id,
            query=request.query,
            answer=response.text,
            uncertainty_score=uncertainty.final_confidence if uncertainty else 0.5,
        )

        if query_id is None:
            query_id = _save_query_history_fallback(
                query=request.query,
                answer=response.text,
                uncertainty_score=uncertainty.final_confidence if uncertainty else 0.5,
            )

        result = RAGQueryResponse(
            query_id=query_id,
            answer=response.text,
            sources=[
                SourceChunk(
                    text=c.text,
                    chunk_id=c.chunk_id,
                    atm_id=c.atm_id,
                    timestamp=c.timestamp,
                    confidence_score=c.confidence_score,
                )
                for c in response.sources
            ],
            uncertainty_score=uncertainty.final_confidence if uncertainty else 0.5,
            confidence_level=uncertainty.confidence_level if uncertainty else "medium",
            is_uncertain=uncertainty.is_uncertain if uncertainty else False,
            recommendation=uncertainty.recommendation if uncertainty else "Review recommended",
            model_used=response.model,
        )

        cache_payload = {
            "query_id": query_id,
            "answer": response.text,
            "sources": [
                {
                    "text": c.text,
                    "chunk_id": c.chunk_id,
                    "atm_id": c.atm_id,
                    "timestamp": c.timestamp,
                    "confidence_score": c.confidence_score,
                }
                for c in response.sources
            ],
            "uncertainty_score": uncertainty.final_confidence if uncertainty else 0.5,
            "confidence_level": uncertainty.confidence_level if uncertainty else "medium",
            "is_uncertain": uncertainty.is_uncertain if uncertainty else False,
            "recommendation": uncertainty.recommendation if uncertainty else "Review recommended",
            "model_used": response.model,
        }
        set_cached_response(sanitized_query, cache_payload)

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"RAG query failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Query processing failed: {str(e)}",
        )


@router.post("/feedback", response_model=RAGFeedbackResponse)
async def provide_feedback(
    request: RAGFeedbackRequest,
    current_user: dict = Depends(get_current_user),
):
    """Provide feedback on a RAG response for calibration."""
    try:
        user_id = _get_user_id_from_username(current_user.get("sub", ""))
        query_row = _get_query_by_id(request.query_id, user_id)
        if not query_row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Query not found",
            )

        logger.info(f"User feedback for query {request.query_id}: {request.feedback}")

        return RAGFeedbackResponse(
            success=True,
            message="Feedback recorded. Thank you for helping improve accuracy.",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Feedback submission failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to submit feedback",
        )


@router.get("/history", response_model=RAGHistoryResponse)
async def get_history(
    limit: int = 20,
    offset: int = 0,
    current_user: dict = Depends(get_current_user),
):
    """Get query history for current user."""
    try:
        user_id = _get_user_id_from_username(current_user.get("sub", ""))
        with get_cursor() as cur:
            cur.execute(
                """
                SELECT id, query_text, answer_text, uncertainty_score, created_at
                FROM rag_queries
                WHERE user_id = %s
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
                """,
                (user_id, limit, offset),
            )
            rows = cur.fetchall()

            cur.execute(
                "SELECT COUNT(*) as total FROM rag_queries WHERE user_id = %s",
                (user_id,),
            )
            total = cur.fetchone()["total"]

        history = [
            {
                "id": row["id"],
                "query_text": row["query_text"],
                "answer_text": row["answer_text"],
                "uncertainty_score": row["uncertainty_score"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else "",
            }
            for row in rows
        ]

        return RAGHistoryResponse(history=history, total=total)

    except Exception as e:
        logger.error(f"History retrieval failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve history",
        )


@router.get("/stats", response_model=RAGStatsResponse)
async def get_stats(
    current_user: dict = Depends(get_current_user),
):
    """Get RAG system statistics."""
    try:
        retriever = get_retriever()

        collection_stats = retriever.get_collection_stats()

        with get_cursor() as cur:
            cur.execute("SELECT COUNT(*) as total FROM rag_queries")
            total_queries = cur.fetchone()["total"]

        return RAGStatsResponse(
            collection_chunks=collection_stats.get("total_chunks", 0),
            total_queries=total_queries,
        )

    except Exception as e:
        logger.error(f"Stats retrieval failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve stats",
        )


def _get_user_id_from_username(username: str) -> Optional[int]:
    """Look up the database user ID from a username."""
    if not username:
        return None
    try:
        with get_cursor() as cur:
            cur.execute("SELECT id FROM users WHERE username = %s", (username,))
            row = cur.fetchone()
            return row["id"] if row else None
    except Exception as e:
        logger.warning(f"Failed to resolve user_id for '{username}': {e}")
        return None


def _save_query_history(
    user_id: Optional[int],
    query: str,
    answer: str,
    uncertainty_score: float,
) -> Optional[int]:
    """Save query to history. Returns the inserted query_id or None."""
    if user_id is None:
        return None
    try:
        with get_cursor(commit=True) as cur:
            cur.execute(
                """
                INSERT INTO rag_queries (user_id, query_text, answer_text, uncertainty_score)
                VALUES (%s, %s, %s, %s)
                RETURNING id
                """,
                (user_id, query, answer, uncertainty_score),
            )
            row = cur.fetchone()
            return row["id"] if row else None
    except Exception as e:
        logger.warning(f"Failed to save query history: {e}")
        return None


def _save_query_history_fallback(
    query: str,
    answer: str,
    uncertainty_score: float,
) -> Optional[int]:
    """Save query history without user_id (fallback for anonymous/unresolved users)."""
    try:
        with get_cursor() as cur:
            cur.execute("SELECT id FROM users WHERE username = 'admin' LIMIT 1")
            row = cur.fetchone()
            user_id = row["id"] if row else None

        if user_id is None:
            return None

        with get_cursor(commit=True) as cur:
            cur.execute(
                """
                INSERT INTO rag_queries (user_id, query_text, answer_text, uncertainty_score)
                VALUES (%s, %s, %s, %s)
                RETURNING id
                """,
                (user_id, query, answer, uncertainty_score),
            )
            row = cur.fetchone()
            return row["id"] if row else None
    except Exception as e:
        logger.warning(f"Fallback query history save failed: {e}")
        return None


def _get_query_by_id(query_id: int, user_id: Optional[int]) -> Optional[dict]:
    """Get query by ID. Falls back to global lookup if user_id is None."""
    if query_id is None:
        return None
    try:
        with get_cursor() as cur:
            if user_id is not None:
                cur.execute(
                    """
                    SELECT id, query_text, answer_text, uncertainty_score
                    FROM rag_queries
                    WHERE id = %s AND user_id = %s
                    """,
                    (query_id, user_id),
                )
            else:
                cur.execute(
                    """
                    SELECT id, query_text, answer_text, uncertainty_score
                    FROM rag_queries
                    WHERE id = %s
                    """,
                    (query_id,),
                )
            row = cur.fetchone()
            return dict(row) if row else None
    except Exception:
        return None


def _extract_anomaly_type_from_query(query: str) -> Optional[str]:
    """Extract anomaly type (A1-A7) from query text if mentioned."""
    import re
    match = re.search(r'\b(A[1-7])\b', query, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    anomaly_keywords = {
        "network timeout": "A1",
        "cassette": "A2",
        "jvm memory": "A3",
        "oom": "A3",
        "restart": "A4",
        "response time": "A5",
        "os memory": "A6",
        "malformed": "A7",
        "out-of-order": "A7",
    }
    query_lower = query.lower()
    for keyword, anomaly_type in anomaly_keywords.items():
        if keyword in query_lower:
            return anomaly_type
    return None
