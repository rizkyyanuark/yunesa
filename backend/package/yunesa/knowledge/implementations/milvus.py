"""Runtime Milvus vector knowledge base and retrieval configuration."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from typing import Any

try:
    from pymilvus import MilvusClient, connections

    MILVUS_AVAILABLE = True
except ImportError:
    MILVUS_AVAILABLE = False
    MilvusClient = Any

from yunesa.knowledge.base import KnowledgeBase
from yunesa.utils import hashstr, logger

DEFAULT_MILVUS_DB_NAME = "default"
VECTOR_METRIC_TYPE = "COSINE"
CONTENT_SPARSE_FIELD = "content_sparse"


@dataclass(kw_only=True)
class MilvusRetrievalConfig:
    """Retrieval configuration options for Milvus vector queries."""

    search_mode: str = field(
        default="vector",
        metadata={
            "label": "Search Mode",
            "type": "select",
            "options": [
                {"value": "vector", "label": "Vector Search", "description": "Dense vector similarity search"},
                {"value": "keyword", "label": "BM25 Search", "description": "Milvus BM25 sparse keyword search"},
                {"value": "hybrid", "label": "Hybrid Search", "description": "Combined vector + BM25 search"},
            ],
            "description": "Select retrieval algorithm mode",
        },
    )
    final_top_k: int = field(
        default=10,
        metadata={
            "label": "Final Top K",
            "type": "number",
            "min": 1,
            "max": 100,
            "description": "Number of top results returned to client",
        },
    )
    similarity_threshold: float = field(
        default=0.0,
        metadata={
            "label": "Similarity Threshold (0-1)",
            "type": "number",
            "min": 0.0,
            "max": 1.0,
            "step": 0.1,
            "description": "Minimum vector similarity score cutoff",
        },
    )
    vector_weight: float = field(
        default=0.7,
        metadata={
            "label": "Vector Search Weight",
            "type": "number",
            "min": 0.0,
            "max": 1.0,
            "step": 0.1,
            "description": "Weight of vector search in hybrid ranking",
        },
    )
    bm25_weight: float = field(
        default=0.3,
        metadata={
            "label": "BM25 Weight",
            "type": "number",
            "min": 0.0,
            "max": 1.0,
            "step": 0.1,
            "description": "Weight of BM25 search in hybrid ranking",
        },
    )


class MilvusKB(KnowledgeBase):
    """Milvus knowledge base implementation for runtime vector retrieval."""

    def __init__(self, work_dir: str, **kwargs: Any):
        super().__init__(work_dir)
        if not MILVUS_AVAILABLE:
            raise ImportError("pymilvus is not installed. Please install with: pip install pymilvus")

        self.milvus_token = kwargs.get("milvus_token", os.getenv("MILVUS_TOKEN") or "")
        self.milvus_uri = kwargs.get("milvus_uri", os.getenv("MILVUS_URI") or "http://localhost:19530")
        self.milvus_db = kwargs.get("milvus_db") or os.getenv("MILVUS_DB_NAME") or DEFAULT_MILVUS_DB_NAME
        self.connection_alias = f"milvus_{hashstr(work_dir, 6)}"
        self.collections: dict[str, Any] = {}
        self.chunk_size = kwargs.get("chunk_size", 1000)
        self.chunk_overlap = kwargs.get("chunk_overlap", 200)
        self._metadata_lock = asyncio.Lock()
        self._init_connection()
        logger.info("MilvusKB initialized | uri=%s | db=%s", self.milvus_uri, self.milvus_db)

    @property
    def kb_type(self) -> str:
        return "milvus"

    def _init_connection(self) -> None:
        """Initialize connection to Milvus standalone server or Zilliz Cloud cluster."""
        try:
            candidates: list[str | None] = []
            configured_db = str(self.milvus_db or "").strip()
            if configured_db and configured_db != DEFAULT_MILVUS_DB_NAME:
                candidates.append(configured_db)
            candidates.append(None)
            if DEFAULT_MILVUS_DB_NAME not in candidates:
                candidates.append(DEFAULT_MILVUS_DB_NAME)

            last_error: Exception | None = None
            self._using_implicit_database = False
            for candidate_db in candidates:
                try:
                    connect_kwargs: dict[str, Any] = {
                        "alias": self.connection_alias,
                        "uri": self.milvus_uri,
                    }
                    if self.milvus_token:
                        connect_kwargs["token"] = self.milvus_token
                    if candidate_db:
                        connect_kwargs["db_name"] = candidate_db
                    connections.connect(**connect_kwargs)
                    if candidate_db is None:
                        self._using_implicit_database = True
                    break
                except Exception as exc:
                    last_error = exc
                    continue
            else:
                if last_error:
                    raise last_error
        except Exception as exc:
            logger.error("Failed to connect to Milvus at %s: %s", self.milvus_uri, exc)
            raise

    async def aquery(self, query_text: str, kb_id: str, **kwargs: Any) -> list[dict[str, Any]]:
        """Perform semantic search against Milvus vector store."""
        client = MilvusClient(uri=self.milvus_uri, token=self.milvus_token or "")
        collection_name = kwargs.get("collection_name", "PaperChunk")
        return client.search(
            collection_name=collection_name,
            data=[query_text],
            limit=kwargs.get("top_k", 10),
            output_fields=["*"],
        )

    def get_query_params_config(self) -> dict[str, Any]:
        """Return UI query parameter options schema."""
        return {
            "type": "milvus",
            "options": [
                {"key": "search_mode", "label": "Search Mode", "type": "select", "default": "vector"},
                {"key": "top_k", "label": "Top K", "type": "number", "default": 10},
            ],
        }

    def __del__(self) -> None:
        """Safely disconnect connection alias on object deletion."""
        try:
            if hasattr(self, "connection_alias"):
                connections.disconnect(self.connection_alias)
        except Exception:
            pass
