"""RAG retriever with confidence scoring for ATM log data."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

import chromadb
from chromadb.config import Settings

from backend.src.rag.config import config

try:
    from sentence_transformers import CrossEncoder

    _HAS_CROSS_ENCODER = True
except ImportError:
    _HAS_CROSS_ENCODER = False

logger = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    """A retrieved document chunk with metadata."""

    text: str
    chunk_id: str
    atm_id: Optional[str]
    timestamp: Optional[str]
    distance: float
    confidence_score: float


class RAGRetriever:
    """Retrieves relevant ATM log chunks from ChromaDB with confidence scoring."""

    def __init__(self):
        try:
            self.client = self._build_client()
            self.collection = self._get_collection()
        except Exception as e:
            logger.warning("ChromaDB unavailable: %s — RAG retrieval disabled", e)
            self.client = None
            self.collection = None
        self._cross_encoder = None

    def _load_cross_encoder(self) -> None:
        """Lazy-load cross-encoder for reranking. Gracefully degrades if unavailable."""
        if self._cross_encoder is not None:
            return
        if not _HAS_CROSS_ENCODER:
            logger.warning(
                "sentence-transformers not installed — cross-encoder reranking disabled. Install with: pip install sentence-transformers"
            )
            return
        if not config.cross_encoder_enabled:
            return
        try:
            model_name = config.cross_encoder_model
            logger.info(f"Loading cross-encoder: {model_name}")
            self._cross_encoder = CrossEncoder(model_name)
            logger.info(f"Cross-encoder loaded successfully: {model_name}")
        except Exception as e:
            logger.warning(
                f"Failed to load cross-encoder {config.cross_encoder_model}: {e}. Reranking disabled."
            )

    def _rerank_with_cross_encoder(
        self, query: str, chunks: list[RetrievedChunk]
    ) -> list[RetrievedChunk]:
        """Rerank chunks using cross-encoder for precise relevance scoring.

        Cross-encoders jointly attend to query + chunk text, producing more accurate
        relevance scores than bi-encoder cosine distance alone.
        """
        if self._cross_encoder is None:
            return chunks

        pairs = [(query, c.text[:512]) for c in chunks]
        try:
            scores = self._cross_encoder.predict(pairs)
        except Exception as e:
            logger.warning(
                f"Cross-encoder reranking failed: {e}. Falling back to original order."
            )
            return chunks

        for i, chunk in enumerate(chunks):
            ce_score = float(scores[i])
            chunk.distance = max(0.0, 1.0 - ce_score)
            chunk.confidence_score = self._calculate_confidence(chunk.distance)

        chunks.sort(key=lambda c: c.distance)
        return chunks

    def _build_client(self) -> chromadb.HttpClient:
        """Build ChromaDB client."""
        return chromadb.HttpClient(
            host=config.chroma_host,
            port=config.chroma_port,
            settings=Settings(anonymized_telemetry=False),
        )

    def _get_collection(self) -> chromadb.Collection:
        """Get or create the ATM logs collection."""
        try:
            collection = self.client.get_collection(name=config.chroma_collection)
            logger.info(
                f"Found existing ChromaDB collection: {config.chroma_collection}"
            )
            return collection
        except Exception as e:
            logger.warning(
                f"Collection {config.chroma_collection} not found, creating: {e}"
            )
            return self.client.create_collection(
                name=config.chroma_collection,
                metadata={"hnsw:space": "cosine"},
            )

    def retrieve(
        self,
        query: str,
        atm_id: Optional[str] = None,
        top_k: Optional[int] = None,
        anomaly_type: Optional[str] = None,
        temporal_boost: bool = True,
        error_only: Optional[bool] = None,
        most_recent_first: Optional[bool] = None,
    ) -> list[RetrievedChunk]:
        """Retrieve relevant chunks for a query.

        Args:
            query: The search query
            atm_id: Filter by specific ATM ID
            top_k: Number of results to return
            anomaly_type: Filter by anomaly type (A1-A7)
            temporal_boost: Boost recent chunks
            error_only: If True, filter for ERROR/FATAL severity or anomaly types
            most_recent_first: If True, sort by timestamp descending (for "most recent" queries)
        """
        if self.collection is None:
            logger.debug("ChromaDB unavailable — returning empty retrieval")
            return []

        if top_k is None:
            top_k = config.retrieval_top_k
        if error_only is None:
            error_only = config.error_only
        if most_recent_first is None:
            most_recent_first = config.most_recent_first

        try:
            where_filter = None
            filter_parts = []

            if atm_id:
                filter_parts.append({"atm_id": atm_id})

            if anomaly_type:
                # A7 has sub-tags (A7_OUT_OF_ORDER, A7_MALFORMED) — match all of them.
                if anomaly_type == "A7":
                    filter_parts.append(
                        {"_anomaly_tag": {"$in": ["A7", "A7_OUT_OF_ORDER", "A7_MALFORMED"]}}
                    )
                else:
                    filter_parts.append({"_anomaly_tag": anomaly_type})

            if error_only:
                severity_filter = {
                    "$or": [
                        {"severity": "ERROR"},
                        {"severity": "FATAL"},
                        {"_anomaly_tag": {"$in": config.anomaly_types}},
                    ]
                }
                filter_parts.append(severity_filter)

            if len(filter_parts) > 1:
                where_filter = {"$and": filter_parts}
            elif len(filter_parts) == 1:
                where_filter = filter_parts[0]

            results = self.collection.query(
                query_texts=[query],
                n_results=top_k * 3,
                where=where_filter,
                include=["documents", "metadatas", "distances"],
            )

            chunks = []
            if results["documents"] and results["documents"][0]:
                doc_ids = results.get("ids", [[]])[0] if results.get("ids") else []
                for i, doc in enumerate(results["documents"][0]):
                    distance = (
                        results["distances"][0][i] if results["distances"] else 0.0
                    )
                    metadata = (
                        results["metadatas"][0][i] if results["metadatas"] else {}
                    )

                    confidence = self._calculate_confidence(distance)
                    chunk_id = doc_ids[i] if i < len(doc_ids) else f"chunk_{i}"

                    chunks.append(
                        RetrievedChunk(
                            text=doc,
                            chunk_id=chunk_id,
                            atm_id=metadata.get("atm_id"),
                            timestamp=metadata.get("last_timestamp"),
                            distance=distance,
                            confidence_score=confidence,
                        )
                    )

            if temporal_boost and chunks:
                chunks = self._apply_temporal_boost(chunks)

            if config.cross_encoder_enabled and chunks:
                self._load_cross_encoder()
                chunks = self._rerank_with_cross_encoder(query, chunks)

            if most_recent_first and chunks:
                chunks = self._sort_by_most_recent(chunks)

            chunks = chunks[:top_k]

            ce_used = self._cross_encoder is not None
            logger.info(
                f"Retrieved {len(chunks)} chunks for query (atm_id={atm_id}, anomaly_type={anomaly_type}, ce_rerank={ce_used})"
            )
            return chunks

        except Exception as e:
            logger.error(f"Retrieval failed: {e}")
            return []

    def _calculate_confidence(self, distance: float) -> float:
        """Calculate confidence score from distance metric."""
        if distance is None:
            return 0.5
        confidence = 1.0 - min(distance, 1.0)
        return round(confidence, 3)

    def _apply_temporal_boost(
        self, chunks: list[RetrievedChunk]
    ) -> list[RetrievedChunk]:
        """Boost relevance of recent chunks (last 6 hours).

        Applies decay scoring: newer chunks get lower distance (higher confidence).
        Returns a new list to avoid mutating original chunks.
        """
        now = datetime.now(timezone.utc)
        six_hours_ago = now.timestamp() - 6 * 3600

        boosted_chunks = []
        for chunk in chunks:
            new_distance = chunk.distance
            new_confidence = chunk.confidence_score

            if chunk.timestamp:
                try:
                    ts = chunk.timestamp
                    if isinstance(ts, str):
                        ts = ts.replace("Z", "+00:00")
                        chunk_ts = datetime.fromisoformat(ts).timestamp()
                    else:
                        chunk_ts = float(ts)

                    if chunk_ts >= six_hours_ago:
                        age_hours = (now.timestamp() - chunk_ts) / 3600
                        boost = max(0.0, 0.1 * (1 - age_hours / 6))
                        new_distance = max(0.0, chunk.distance - boost)
                        new_confidence = self._calculate_confidence(new_distance)
                except (ValueError, TypeError):
                    pass

            from dataclasses import replace

            boosted_chunks.append(
                replace(
                    chunk,
                    distance=new_distance,
                    confidence_score=new_confidence,
                )
            )

        boosted_chunks.sort(key=lambda c: c.distance)
        return boosted_chunks

    def _sort_by_most_recent(
        self, chunks: list[RetrievedChunk]
    ) -> list[RetrievedChunk]:
        """Sort chunks by timestamp descending (most recent first).

        Chunks without valid timestamps are placed at the end.
        """

        def get_timestamp_key(chunk: RetrievedChunk) -> float:
            if not chunk.timestamp:
                return 0.0
            try:
                ts = chunk.timestamp
                if isinstance(ts, str):
                    ts = ts.replace("Z", "+00:00")
                    return datetime.fromisoformat(ts).timestamp()
                return float(ts)
            except (ValueError, TypeError):
                return 0.0

        sorted_chunks = sorted(chunks, key=get_timestamp_key, reverse=True)
        return sorted_chunks

    def retrieve_by_atm(self, atm_id: str, limit: int = 10) -> list[RetrievedChunk]:
        """Retrieve recent chunks for a specific ATM."""
        if self.collection is None:
            logger.debug("ChromaDB unavailable — returning empty ATM retrieval")
            return []

        try:
            results = self.collection.get(
                where={"atm_id": atm_id},
                limit=limit,
                include=["documents", "metadatas"],
            )

            chunks = []
            if results["documents"]:
                for i, doc in enumerate(results["documents"]):
                    metadata = results["metadatas"][i] if results["metadatas"] else {}
                    chunks.append(
                        RetrievedChunk(
                            text=doc,
                            chunk_id=results["ids"][i]
                            if results["ids"]
                            else f"chunk_{i}",
                            atm_id=atm_id,
                            timestamp=metadata.get("last_timestamp"),
                            distance=0.0,
                            confidence_score=0.8,
                        )
                    )

            return chunks

        except Exception as e:
            logger.error(f"Retrieval by ATM failed: {e}")
            return []

    def get_collection_stats(self) -> dict[str, Any]:
        """Get collection statistics."""
        if self.collection is None:
            logger.debug("ChromaDB unavailable — returning empty stats")
            return {"error": "ChromaDB unavailable"}

        try:
            count = self.collection.count()
            return {
                "total_chunks": count,
                "collection_name": config.chroma_collection,
            }
        except Exception as e:
            logger.error("Failed to get collection stats: %s", str(e))
            return {"error": str(e)}

    def clear_collection(self) -> dict[str, Any]:
        """Clear all documents from the collection."""
        if self.client is None or self.collection is None:
            logger.debug("ChromaDB unavailable — cannot clear collection")
            return {"error": "ChromaDB unavailable"}

        try:
            self.client.delete_collection(config.chroma_collection)
            self.collection = self.client.create_collection(
                name=config.chroma_collection,
                metadata={"hnsw:space": "cosine"},
            )
            logger.warning(
                "Cleared and recreated ChromaDB collection: %s",
                config.chroma_collection,
            )
            return {
                "success": True,
                "message": f"Cleared collection: {config.chroma_collection}",
            }
        except Exception as e:
            logger.error("Failed to clear collection: %s", str(e))
            return {"error": str(e)}

    def rebuild_collection(self, new_client: bool = False) -> dict[str, Any]:
        """Rebuild the collection (clear and reinitialize).

        Args:
            new_client: If True, creates a new client (useful when ChromaDB was restarted)
        """
        if self.client is None:
            logger.debug("ChromaDB unavailable — cannot rebuild collection")
            return {"error": "ChromaDB unavailable"}

        global _retriever
        try:
            if new_client:
                self.client = self._build_client()
            self.client.delete_collection(config.chroma_collection)
            self.collection = self.client.create_collection(
                name=config.chroma_collection,
                metadata={"hnsw:space": "cosine"},
            )
            logger.info("Rebuilt ChromaDB collection: %s", config.chroma_collection)
            return {
                "success": True,
                "message": f"Rebuilt collection: {config.chroma_collection}",
            }
        except Exception as e:
            logger.error("Failed to rebuild collection: %s", str(e))
            return {"error": str(e)}


_retriever: Optional[RAGRetriever] = None


def get_retriever() -> RAGRetriever:
    """Get singleton retriever instance."""
    global _retriever
    if _retriever is None:
        _retriever = RAGRetriever()
    return _retriever


def reset_retriever() -> None:
    """Reset the retriever singleton (useful for testing or after ChromaDB restart)."""
    global _retriever
    _retriever = None
