"""RAG retriever with confidence scoring for ATM log data."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

import chromadb
from chromadb.config import Settings

from backend.src.rag.config import config

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
        self.client = self._build_client()
        self.collection = self._get_collection()

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
            logger.info(f"Found existing ChromaDB collection: {config.chroma_collection}")
            return collection
        except Exception as e:
            logger.warning(f"Collection {config.chroma_collection} not found, creating: {e}")
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
    ) -> list[RetrievedChunk]:
        """Retrieve relevant chunks for a query."""
        if top_k is None:
            top_k = config.retrieval_top_k
        try:
            where_filter = None
            if atm_id and anomaly_type:
                where_filter = {"$and": [{"atm_id": atm_id}, {"_anomaly_tag": anomaly_type}]}
            elif atm_id:
                where_filter = {"atm_id": atm_id}
            elif anomaly_type:
                where_filter = {"_anomaly_tag": anomaly_type}

            results = self.collection.query(
                query_texts=[query],
                n_results=top_k,
                where=where_filter,
                include=["documents", "metadatas", "distances"],
            )

            chunks = []
            if results["documents"] and results["documents"][0]:
                doc_ids = results.get("ids", [[]])[0] if results.get("ids") else []
                for i, doc in enumerate(results["documents"][0]):
                    distance = results["distances"][0][i] if results["distances"] else 0.0
                    metadata = results["metadatas"][0][i] if results["metadatas"] else {}

                    confidence = self._calculate_confidence(distance)
                    chunk_id = doc_ids[i] if i < len(doc_ids) else f"chunk_{i}"

                    chunks.append(RetrievedChunk(
                        text=doc,
                        chunk_id=chunk_id,
                        atm_id=metadata.get("atm_id"),
                        timestamp=metadata.get("last_timestamp"),
                        distance=distance,
                        confidence_score=confidence,
                    ))

            if temporal_boost and chunks:
                chunks = self._apply_temporal_boost(chunks)

            logger.info(f"Retrieved {len(chunks)} chunks for query (atm_id={atm_id}, anomaly_type={anomaly_type})")
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

    def _apply_temporal_boost(self, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        """Boost relevance of recent chunks (last 6 hours).
        
        Applies decay scoring: newer chunks get lower distance (higher confidence).
        """
        now = datetime.now(timezone.utc)
        six_hours_ago = now.timestamp() - 6 * 3600

        for chunk in chunks:
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
                        chunk.distance = max(0.0, chunk.distance - boost)
                        chunk.confidence_score = self._calculate_confidence(chunk.distance)
                except (ValueError, TypeError):
                    pass

        chunks.sort(key=lambda c: c.distance)
        return chunks

    def retrieve_by_atm(self, atm_id: str, limit: int = 10) -> list[RetrievedChunk]:
        """Retrieve recent chunks for a specific ATM."""
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
                    chunks.append(RetrievedChunk(
                        text=doc,
                        chunk_id=results["ids"][i] if results["ids"] else f"chunk_{i}",
                        atm_id=atm_id,
                        timestamp=metadata.get("last_timestamp"),
                        distance=0.0,
                        confidence_score=0.8,
                    ))

            return chunks

        except Exception as e:
            logger.error(f"Retrieval by ATM failed: {e}")
            return []

    def get_collection_stats(self) -> dict[str, Any]:
        """Get collection statistics."""
        try:
            count = self.collection.count()
            return {
                "total_chunks": count,
                "collection_name": config.chroma_collection,
            }
        except Exception as e:
            logger.error(f"Failed to get collection stats: {e}")
            return {"error": str(e)}


_retriever: Optional[RAGRetriever] = None


def get_retriever() -> RAGRetriever:
    """Get singleton retriever instance."""
    global _retriever
    if _retriever is None:
        _retriever = RAGRetriever()
    return _retriever