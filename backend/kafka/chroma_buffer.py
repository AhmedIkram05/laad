"""ChromaDB write buffer for the Kafka consumer.

Accumulates events per ATM in a window buffer. When the window
reaches WINDOW_SIZE events for a given ATM, it flushes:
  1. Concatenates the event texts into a single document
  2. Uses LangChain SemanticChunker with nomic-embed-text to chunk
  3. Upserts chunks into the ChromaDB collection

The ChromaDB collection name is "atm_logs" — consistent with the
existing RAG assistant configuration.

Usage:
    buffer = ChromaBuffer()
    buffer.add_event(atm_id="ATM-GB-0001", text="Transaction completed...", timestamp="...")
    buffer.flush_all()
"""
from __future__ import annotations

import logging
import os
from collections import defaultdict
from uuid import uuid4

log = logging.getLogger(__name__)

CHROMA_HOST     = os.getenv("CHROMA_HOST", "localhost")
CHROMA_PORT     = int(os.getenv("CHROMA_PORT", "8001"))
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
WINDOW_SIZE     = int(os.getenv("CHROMA_WINDOW_SIZE", "10"))
COLLECTION_NAME = "atm_logs"


def _build_chroma_client():
    import chromadb
    return chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)


def _build_embeddings():
    from langchain_ollama import OllamaEmbeddings
    return OllamaEmbeddings(model="nomic-embed-text", base_url=OLLAMA_BASE_URL)


def _build_chunker(embeddings):
    from langchain_experimental.text_splitter import SemanticChunker
    return SemanticChunker(embeddings)


class ChromaBuffer:
    def __init__(self):
        self._buffers: dict[str, list[tuple[str, str]]] = defaultdict(list)
        self._client     = None
        self._collection = None
        self._embeddings = None
        self._chunker    = None
        self._ready      = False
        self._init()

    def _init(self) -> None:
        try:
            self._client     = _build_chroma_client()
            self._embeddings = _build_embeddings()
            self._chunker    = _build_chunker(self._embeddings)
            self._collection = self._client.get_or_create_collection(
                name=COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
            )
            self._ready = True
            log.info("ChromaBuffer initialised. Collection: %s", COLLECTION_NAME)
        except Exception as exc:
            log.warning("ChromaBuffer init failed — ChromaDB writes disabled: %s", exc)
            self._ready = False

    def add_event(self, atm_id: str, text: str, timestamp: str) -> None:
        if not self._ready:
            return
        self._buffers[atm_id].append((text, timestamp))
        if len(self._buffers[atm_id]) >= WINDOW_SIZE:
            self._flush_atm(atm_id)

    def _flush_atm(self, atm_id: str) -> None:
        events = self._buffers.pop(atm_id, [])
        if not events:
            return
        try:
            text = "\n".join(t for t, _ in events)
            last_ts = events[-1][1]
            chunks = self._chunker.create_documents([text])
            if not chunks:
                return
            self._collection.upsert(
                documents=[c.page_content for c in chunks],
                ids=[f"{atm_id}_{uuid4()}" for _ in chunks],
                metadatas=[{"atm_id": atm_id, "last_timestamp": last_ts} for _ in chunks],
            )
            log.debug("Flushed %d chunks to ChromaDB for %s", len(chunks), atm_id)
        except Exception as exc:
            log.warning("ChromaDB flush failed for %s: %s", atm_id, exc)

    def flush_all(self) -> None:
        for atm_id in list(self._buffers.keys()):
            self._flush_atm(atm_id)


def format_event_text(msg: dict) -> str:
    parts = [
        f"{msg.get('timestamp', '')}",
        f"[{msg.get('source', 'UNKNOWN')}]",
        f"{msg.get('event_type', '')}:",
        msg.get("message", ""),
    ]
    payload = msg.get("payload") or {}
    if isinstance(payload, dict) and payload:
        kv = ", ".join(f"{k}={v}" for k, v in list(payload.items())[:5])
        parts.append(f"| {kv}")
    return " ".join(str(p) for p in parts if p)