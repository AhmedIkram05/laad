"""RAG retriever with confidence scoring for ATM log data."""

from __future__ import annotations

import heapq
import logging
import math
import re
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

_TOKEN_RE = re.compile(r"[a-z0-9]+")

_MAX_HYBRID_DOCS = 5000
_SPARSE_CACHE_MAX = 5
_TOKEN_CACHE_MAX = 5000


@dataclass
class _SparsePool:
    """Cached sparse-pool snapshot for one where_filter, with BM25 stats
    (df/avgdl) derived from the token cache instead of recomputed per query."""

    ids: list
    docs: list
    metas: list
    df: dict
    avgdl: float


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall((text or "").lower())


def _bm25_scores(
    query_tokens: list[str],
    docs_tokens: list[list[str]],
    k1: float = 1.5,
    b: float = 0.75,
    df: Optional[dict[str, int]] = None,
    avgdl: Optional[float] = None,
) -> list[float]:
    n = len(docs_tokens)
    if n == 0:
        return []
    if df is None:
        df = {}
        for toks in docs_tokens:
            for t in set(toks):
                df[t] = df.get(t, 0) + 1
    if avgdl is None:
        avgdl = sum(len(t) for t in docs_tokens) / n
    scores = []
    for toks in docs_tokens:
        dl = len(toks)
        tf: dict[str, int] = {}
        for t in toks:
            tf[t] = tf.get(t, 0) + 1
        s = 0.0
        for t in set(query_tokens):
            f = tf.get(t, 0)
            if not f:
                continue
            df_t = df.get(t, 0)
            idf = math.log(1 + (n - df_t + 0.5) / (df_t + 0.5))
            denom = f + k1 * (1 - b + b * (dl / avgdl if avgdl else 1))
            s += idf * (f * (k1 + 1) / denom)
        scores.append(s)
    return scores


def _rrf_scores(ranked_lists: list[list[str]], k: int = 60) -> dict[str, float]:
    fused: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, cid in enumerate(ranked, start=1):
            fused[cid] = fused.get(cid, 0.0) + 1.0 / (k + rank)
    return fused


def _rrf_fuse(ranked_lists: list[list[str]], k: int = 60) -> list[str]:
    fused = _rrf_scores(ranked_lists, k)
    return sorted(fused, key=lambda c: fused[c], reverse=True)


@dataclass
class RetrievedChunk:
    """A retrieved document chunk with metadata."""

    text: str
    chunk_id: str
    atm_id: Optional[str]
    timestamp: Optional[str]
    distance: float
    confidence_score: float
    # Reciprocal-rank-fusion score from hybrid retrieval (None when the chunk
    # was not fused). Kept separate from `distance` so the true cosine
    # distance is never overwritten by a rank-derived pseudo-distance.
    rrf_score: Optional[float] = None
    # Set when the cross-encoder actually reranked this chunk.
    cross_encoder_used: bool = False


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
        self._sparse_cache: dict[str, _SparsePool] = {}
        self._token_cache: dict[str, list[str]] = {}

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
            chunk.cross_encoder_used = True

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

    def _tokens_for(self, cid: str, doc: str) -> list[str]:
        """Tokenized doc body for cid, cached by doc id and size-capped so each
        document is tokenized once instead of once per query."""
        toks = self._token_cache.get(cid)
        if toks is None:
            toks = _tokenize(doc)
            self._token_cache[cid] = toks
            while len(self._token_cache) > _TOKEN_CACHE_MAX:
                self._token_cache.pop(next(iter(self._token_cache)))
        return toks

    def _sparse_pool(self, where_filter: Any) -> tuple[list, list, list, dict, float]:
        try:
            try:
                total = self.collection.count()
            except Exception as e:
                logger.debug("Sparse pool count failed: %s", e)
                total = -1
            if not isinstance(total, int) or isinstance(total, bool):
                total = -1
            if total > _MAX_HYBRID_DOCS:
                logger.warning(
                    "Hybrid disabled: collection size %d exceeds limit %d",
                    total,
                    _MAX_HYBRID_DOCS,
                )
                return [], [], [], {}, 0.0
            if not isinstance(getattr(self, "_sparse_cache", None), dict):
                self._sparse_cache = {}
            if not isinstance(getattr(self, "_token_cache", None), dict):
                self._token_cache = {}
            key = repr(where_filter)
            entry = self._sparse_cache.get(key)
            # Probe live membership without pulling document payloads — the id
            # list, not collection.count(), is the invalidation signal.
            probe = self.collection.get(
                where=where_filter, include=[], limit=_MAX_HYBRID_DOCS
            )
            if not isinstance(probe, dict):
                return [], [], [], {}, 0.0
            live_ids = probe.get("ids") or []
            if not isinstance(live_ids, list):
                return [], [], [], {}, 0.0
            if entry is not None and live_ids == entry.ids:
                return entry.ids, entry.docs, entry.metas, entry.df, entry.avgdl

            # Refresh: fetch full documents only for ids the pool has never
            # stored; everything else is served from the cached entry.
            known = {cid: i for i, cid in enumerate(entry.ids)} if entry else {}
            new_ids = [cid for cid in live_ids if cid not in known]
            docs_by_id: dict = {}
            metas_by_id: dict = {}
            if new_ids:
                try:
                    fetched = self.collection.get(
                        ids=new_ids,
                        where=where_filter,
                        include=["documents", "metadatas"],
                        limit=_MAX_HYBRID_DOCS,
                    )
                except Exception as e:
                    logger.debug("Sparse pool document fetch failed: %s", e)
                    fetched = None
                if isinstance(fetched, dict):
                    f_ids = fetched.get("ids") or []
                    f_docs = fetched.get("documents") or []
                    f_metas = fetched.get("metadatas") or []
                    if not isinstance(f_ids, list) or not isinstance(f_docs, list):
                        f_ids, f_docs = [], []
                    if not isinstance(f_metas, list):
                        f_metas = [{}] * len(f_ids)
                    for cid, doc, meta in zip(f_ids, f_docs, f_metas):
                        docs_by_id[cid] = doc or ""
                        metas_by_id[cid] = meta if isinstance(meta, dict) else {}
            ids: list = []
            docs: list = []
            metas: list = []
            for cid in live_ids:
                if cid in known:
                    i = known[cid]
                    ids.append(cid)
                    docs.append(entry.docs[i])
                    metas.append(entry.metas[i])
                elif cid in docs_by_id:
                    ids.append(cid)
                    docs.append(docs_by_id[cid])
                    metas.append(metas_by_id[cid])
            # Opportunistically drop tokenized docs that vanished from every
            # cached pool.
            if entry is not None:
                live_set = set(live_ids)
                vanished = [cid for cid in entry.ids if cid not in live_set]
                if vanished:
                    kept_elsewhere = set(live_ids)
                    for other in self._sparse_cache.values():
                        if other is not entry:
                            kept_elsewhere.update(other.ids)
                    for cid in vanished:
                        if cid not in kept_elsewhere:
                            self._token_cache.pop(cid, None)
            pool_tokens = [self._tokens_for(cid, doc) for cid, doc in zip(ids, docs)]
            df: dict[str, int] = {}
            for toks in pool_tokens:
                for t in set(toks):
                    df[t] = df.get(t, 0) + 1
            avgdl = (
                sum(len(toks) for toks in pool_tokens) / len(pool_tokens)
                if pool_tokens
                else 0.0
            )
            self._sparse_cache[key] = _SparsePool(
                ids=ids, docs=docs, metas=metas, df=df, avgdl=avgdl
            )
            while len(self._sparse_cache) > _SPARSE_CACHE_MAX:
                self._sparse_cache.pop(next(iter(self._sparse_cache)))
            return ids, docs, metas, df, avgdl
        except Exception as e:
            logger.debug("Sparse pool fetch failed: %s", e)
            return [], [], [], {}, 0.0

    def _fuse_hybrid(
        self,
        query: str,
        dense_chunks: list[RetrievedChunk],
        where_filter: Any,
        pool_n: int,
    ) -> list[RetrievedChunk]:
        from dataclasses import replace

        ids, docs, metas, df, avgdl = self._sparse_pool(where_filter)
        if not docs:
            return dense_chunks
        scores = _bm25_scores(
            _tokenize(query),
            [self._tokens_for(cid, doc) for cid, doc in zip(ids, docs)],
            df=df,
            avgdl=avgdl,
        )
        pool_n = max(1, min(pool_n, len(scores)))
        top = heapq.nlargest(pool_n, range(len(scores)), key=scores.__getitem__)
        sparse_ids = [ids[i] for i in top if scores[i] > 0]
        if not sparse_ids:
            return dense_chunks
        dense_ids = [c.chunk_id for c in dense_chunks]
        fused_scores = _rrf_scores([dense_ids, sparse_ids])
        if not fused_scores:
            return dense_chunks
        peak = max(fused_scores.values())
        fused_order = sorted(fused_scores, key=lambda c: fused_scores[c], reverse=True)
        dense_by_id = {c.chunk_id: c for c in dense_chunks}
        id_to_index = {cid: i for i, cid in enumerate(ids)}
        out: list[RetrievedChunk] = []
        for cid in fused_order:
            rrf = fused_scores[cid]
            if cid in dense_by_id:
                # Keep the true vector distance and its confidence — the RRF
                # rank position must not overwrite the semantic similarity
                # signal downstream consumers read as confidence.
                out.append(replace(dense_by_id[cid], rrf_score=rrf))
                continue
            i = id_to_index.get(cid)
            if i is None:
                continue
            meta = metas[i] if i < len(metas) and isinstance(metas[i], dict) else {}
            # Sparse-only chunk: no vector distance exists, so the
            # RRF-normalized pseudo-distance is its only relevance signal.
            distance = 1.0 - (rrf / peak) if peak else 1.0
            confidence = self._calculate_confidence(distance)
            out.append(
                RetrievedChunk(
                    text=docs[i] or "",
                    chunk_id=cid,
                    atm_id=meta.get("atm_id"),
                    timestamp=meta.get("last_timestamp"),
                    distance=distance,
                    confidence_score=confidence,
                    rrf_score=rrf,
                )
            )
        return out or dense_chunks

    def retrieve(
        self,
        query: str,
        atm_id: Optional[str] = None,
        top_k: Optional[int] = None,
        anomaly_type: Optional[str] = None,
        temporal_boost: bool = True,
        error_only: Optional[bool] = None,
        most_recent_first: Optional[bool] = None,
        enable_hybrid: bool = True,
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
                        {
                            "_anomaly_tag": {
                                "$in": ["A7", "A7_OUT_OF_ORDER", "A7_MALFORMED"]
                            }
                        }
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

            if enable_hybrid:
                try:
                    chunks = self._fuse_hybrid(query, chunks, where_filter, top_k * 3)
                except Exception as e:
                    logger.warning("Hybrid fusion failed, using dense results: %s", e)

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
            if isinstance(getattr(self, "_sparse_cache", None), dict):
                self._sparse_cache.clear()
            if isinstance(getattr(self, "_token_cache", None), dict):
                self._token_cache.clear()
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
            if isinstance(getattr(self, "_sparse_cache", None), dict):
                self._sparse_cache.clear()
            if isinstance(getattr(self, "_token_cache", None), dict):
                self._token_cache.clear()
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
