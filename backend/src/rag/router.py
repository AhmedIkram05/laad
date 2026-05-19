"""FastAPI router for RAG diagnostic assistant."""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from datetime import datetime
from typing import Optional

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
from backend.src.rag.calibration import get_calibration_manager
from backend.src.rag.utils import sanitize_query, extract_atm_id_from_query
from backend.src.auth.auth_router import get_current_user, require_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/rag", tags=["RAG"])

RATE_LIMIT_WINDOW = 60
RATE_LIMIT_MAX_REQUESTS = 10
_query_timestamps: dict[str, list[float]] = defaultdict(list)


def _check_rate_limit(user_key: str) -> None:
    """Check if user has exceeded rate limit. Raises 429 if so."""
    now = time.time()
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

        retriever = get_retriever()
        generator = get_generator()
        uncertainty_estimator = get_uncertainty_estimator()
        calibration_manager = get_calibration_manager()

        sanitized_query = sanitize_query(request.query)
        atm_id = request.atm_id or extract_atm_id_from_query(request.query)

        chunks = retriever.retrieve(
            query=sanitized_query,
            atm_id=atm_id,
            top_k=request.top_k,
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

            if calibration_manager.params.is_fitted:
                calibrated = calibration_manager.apply(uncertainty.final_confidence)
                uncertainty.final_confidence = calibrated.calibrated_confidence
                uncertainty.is_uncertain = uncertainty.final_confidence < 0.5
                uncertainty.confidence_level = (
                    "high" if uncertainty.final_confidence >= 0.8
                    else "medium" if uncertainty.final_confidence >= 0.5
                    else "low"
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

        return RAGQueryResponse(
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
            is_calibrated=calibration_manager.params.is_fitted,
            is_uncertain=uncertainty.is_uncertain if uncertainty else False,
            recommendation=uncertainty.recommendation if uncertainty else "Review recommended",
            model_used=response.model,
        )

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
        calibration_manager = get_calibration_manager()

        user_id = _get_user_id_from_username(current_user.get("sub", ""))
        query_row = _get_query_by_id(request.query_id, user_id)
        if not query_row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Query not found",
            )

        if request.feedback == "helpful":
            is_correct = True
        elif request.feedback == "not_helpful":
            is_correct = False
        elif request.feedback == "uncertain":
            is_correct = None
            logger.info(f"User marked query {request.query_id} as uncertain")
        else:
            is_correct = None

        if is_correct is not None:
            calibration_manager.add_feedback(
                raw_confidence=query_row["uncertainty_score"],
                is_correct=is_correct,
            )

            calibration_manager.maybe_fit()

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
        calibration_manager = get_calibration_manager()

        collection_stats = retriever.get_collection_stats()
        calibration_status = calibration_manager.get_status()

        with get_cursor() as cur:
            cur.execute("SELECT COUNT(*) as total FROM rag_queries")
            total_queries = cur.fetchone()["total"]

        return RAGStatsResponse(
            collection_chunks=collection_stats.get("total_chunks", 0),
            calibration_status=calibration_status,
            total_queries=total_queries,
            calibration_samples=calibration_status.get("sample_size", 0),
            is_calibrated=calibration_status.get("is_calibrated", False),
        )

    except Exception as e:
        logger.error(f"Stats retrieval failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve stats",
        )


@router.post("/recalibrate")
async def recalibrate(
    current_user: dict = Depends(require_admin),
):
    """Trigger recalibration of confidence scores. Admin only."""
    try:
        calibration_manager = get_calibration_manager()
        result = calibration_manager.fit(min_samples=10)

        return {
            "success": True,
            "is_calibrated": result.is_calibrated,
            "ece_score": result.calibration_params.ece_score,
            "sample_size": result.calibration_params.sample_size,
        }

    except Exception as e:
        logger.error(f"Recalibration failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Recalibration failed",
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
