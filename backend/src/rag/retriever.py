"""RAG retriever with confidence scoring for ATM log data."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
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
            return self.client.get_collection(name=config.chroma_collection)
        except Exception as e:
            logger.warning(f"Collection {config.chroma_collection} not found: {e}")
            return self.client.create_collection(
                name=config.chroma_collection,
                metadata={"hnsw:space": "cosine"},
            )

    def retrieve(
        self,
        query: str,
        atm_id: Optional[str] = None,
        top_k: int = config.retrieval_top_k,
    ) -> list[RetrievedChunk]:
        """Retrieve relevant chunks for a query."""
        try:
            where_filter = {"atm_id": atm_id} if atm_id else None

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

            logger.info(f"Retrieved {len(chunks)} chunks for query (atm_id={atm_id})")
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