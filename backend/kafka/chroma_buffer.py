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

Metadata stored per chunk:
  - atm_id: The ATM identifier
  - last_timestamp: Timestamp of the most recent event in the chunk
  - severity: Extracted from event (ERROR, FATAL, WARNING, INFO, CRITICAL)
  - _anomaly_tag: Extracted from payload (_anomaly_tag field, e.g., A1-A7)
"""
from __future__ import annotations

import logging
import os
from collections import defaultdict
from typing import Any, Optional
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
        self._buffers: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._client     = None
        self._collection = None
        self._embeddings = None
        self._chunker    = None
        self._ready      = False
        self._init()

    def _init(self) -> None:
        try:
            self._client     = _build_chroma_client()
            try:
                self._embeddings = _build_embeddings()
                self._chunker    = _build_chunker(self._embeddings)
            except Exception as embed_exc:
                log.warning("Ollama embeddings unavailable, using simple chunking fallback: %s", embed_exc)
                self._embeddings = None
                self._chunker    = None
            self._collection = self._client.get_or_create_collection(
                name=COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
            )
            self._ready = True
            log.info("ChromaBuffer initialised. Collection: %s", COLLECTION_NAME)
        except Exception as exc:
            log.warning("ChromaBuffer init failed — ChromaDB writes disabled: %s", exc)
            self._ready = False

    def add_event(
        self,
        atm_id: str,
        text: str,
        timestamp: str,
        severity: Optional[str] = None,
        anomaly_tag: Optional[str] = None,
    ) -> None:
        if not self._ready:
            return
        self._buffers[atm_id].append({
            "text": text,
            "timestamp": timestamp,
            "severity": severity,
            "anomaly_tag": anomaly_tag,
        })
        if len(self._buffers[atm_id]) >= WINDOW_SIZE:
            self._flush_atm(atm_id)

    def _flush_atm(self, atm_id: str) -> None:
        events = self._buffers.pop(atm_id, [])
        if not events:
            return
        try:
            last_ts = events[-1]["timestamp"]
            severities = [e.get("severity") for e in events if e.get("severity")]
            anomaly_tags = [e.get("anomaly_tag") for e in events if e.get("anomaly_tag")]
            dominant_severity = self._get_dominant_severity(severities) if severities else None
            dominant_anomaly = max(set(anomaly_tags), key=anomaly_tags.count) if anomaly_tags else None

            text_with_prefix = "\n".join(
                f"ATM: {atm_id} | {e['text']}" for e in events
            )

            if self._chunker:
                chunks = self._chunker.create_documents([text_with_prefix])
                if not chunks:
                    return
                documents = [c.page_content for c in chunks]
            else:
                max_chunk = 500
                words = text_with_prefix.split()
                documents = []
                for i in range(0, len(words), max_chunk):
                    chunk = " ".join(words[i:i + max_chunk])
                    if chunk.strip():
                        documents.append(chunk)
                if not documents:
                    return

            metadata_list = []
            for _ in documents:
                meta = {"atm_id": atm_id, "last_timestamp": last_ts}
                if dominant_severity:
                    meta["severity"] = dominant_severity
                if dominant_anomaly:
                    meta["_anomaly_tag"] = dominant_anomaly
                metadata_list.append(meta)

            self._collection.upsert(
                documents=documents,
                ids=[f"{atm_id}_{uuid4()}" for _ in documents],
                metadatas=metadata_list,
            )
            log.debug("Flushed %d chunks to ChromaDB for %s (severity=%s, anomaly_tag=%s)", 
                      len(documents), atm_id, dominant_severity, dominant_anomaly)
        except Exception as exc:
            log.warning("ChromaDB flush failed for %s: %s", atm_id, exc)

    def _get_dominant_severity(self, severities: list[str]) -> Optional[str]:
        priority = {"FATAL": 5, "CRITICAL": 4, "ERROR": 3, "WARNING": 2, "INFO": 1}
        max_priority = 0
        dominant = None
        for sev in severities:
            p = priority.get(sev.upper(), 0)
            if p > max_priority:
                max_priority = p
                dominant = sev
        return dominant

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