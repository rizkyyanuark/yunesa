"""Qdrant vector storage adapter implementing the BaseVectorStorage interface."""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import Callable
from typing import Any

import httpx

from yunesa.utils import logger

from ..base import BaseVectorStorage

VectorEmbedder = Callable[[str], list[float]]


class QdrantVectorStorage(BaseVectorStorage):
    """Deep module vector storage adapter backed by Qdrant REST API.

    Hides connection lifecycle, payload filtering, batch ingestion, and network error
    handling behind a minimal interface conforming to BaseVectorStorage.
    """

    def __init__(
        self,
        uri: str | None = None,
        *,
        api_key: str | None = None,
        timeout: float = 12.0,
        embedder: VectorEmbedder | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.uri = (uri or os.getenv("QDRANT_URI") or "http://vector:6333").rstrip("/")
        self.api_key = api_key or os.getenv("QDRANT_API_KEY")
        self.timeout = timeout
        self.embedder = embedder
        self._client = client

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["api-key"] = self.api_key
        return headers

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is not None and not self._client.is_closed:
            return self._client
        self._client = httpx.AsyncClient(
            base_url=self.uri,
            headers=self._headers(),
            timeout=self.timeout,
        )
        return self._client

    async def close(self) -> None:
        """Close underlying HTTP client connections."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def health_check(self) -> bool:
        """Probe Qdrant readiness without leaking raw transport exceptions."""
        try:
            client = await self._get_client()
            response = await client.get("/readyz", headers=self._headers())
            return response.status_code == 200
        except Exception as exc:
            logger.debug(f"Qdrant health check failed: {type(exc).__name__}: {exc}")
            return False

    async def query(
        self,
        query_text: str,
        *,
        collection_name: str,
        output_fields: list[str],
        text_fields: list[str],
        top_k: int,
        graph_name: str,
        query_vector: list[float] | None = None,
        embed_if_missing: bool = True,
    ) -> list[dict[str, Any]]:
        """Query vector collection with dense vector search and keyword fallback.

        Encapsulates payload extraction, graph scoping, and error locality so callers
        never encounter unhandled Qdrant transport errors.
        """
        vector = query_vector
        if vector is None and embed_if_missing and self.embedder is not None:
            try:
                vector = await asyncio.to_thread(self.embedder, query_text)
            except Exception as exc:
                logger.warning(f"Failed to embed query text '{query_text}': {exc}")

        if vector is not None:
            return await self._dense_search(
                collection_name=collection_name,
                vector=vector,
                output_fields=output_fields,
                top_k=top_k,
                graph_name=graph_name,
            )

        return await self._lexical_scroll(
            query_text=query_text,
            collection_name=collection_name,
            output_fields=output_fields,
            text_fields=text_fields,
            top_k=top_k,
            graph_name=graph_name,
        )

    async def upsert(
        self,
        collection_name: str,
        records: list[dict[str, Any]],
        *,
        vector_field: str = "embedding",
        id_field: str = "id",
        batch_size: int = 64,
        vector_size: int = 1024,
    ) -> int:
        """Batch upsert points into Qdrant, provisioning collection if missing.

        Encapsulates payload batching, auto-provisioning, ID generation, and error locality.
        Returns the count of successfully upserted points.
        """
        if not records:
            return 0

        client = await self._get_client()
        await self._ensure_collection(client, collection_name, vector_size=vector_size)

        total_upserted = 0
        for i in range(0, len(records), batch_size):
            batch = records[i : i + batch_size]
            points: list[dict[str, Any]] = []
            for item in batch:
                vector = item.get(vector_field)
                if not vector:
                    continue
                point_id = item.get(id_field) or uuid.uuid4().hex
                payload = {k: v for k, v in item.items() if k != vector_field}
                points.append({
                    "id": point_id,
                    "vector": vector,
                    "payload": payload,
                })

            if not points:
                continue

            try:
                response = await client.put(
                    f"/collections/{collection_name}/points?wait=true",
                    json={"points": points},
                    headers=self._headers(),
                )
                response.raise_for_status()
                total_upserted += len(points)
            except Exception as exc:
                logger.warning(
                    f"Qdrant batch upsert failed for {collection_name} (batch {i // batch_size}): "
                    f"{type(exc).__name__}: {exc}"
                )

        return total_upserted

    @staticmethod
    def _build_filter(graph_name: str, collection_name: str) -> dict[str, Any] | None:
        if not graph_name or collection_name == "community_summaries":
            return None
        return {
            "must": [
                {
                    "key": "graphName",
                    "match": {"value": graph_name},
                }
            ]
        }

    async def _ensure_collection(
        self,
        client: httpx.AsyncClient,
        collection_name: str,
        *,
        vector_size: int = 1024,
        distance: str = "Cosine",
    ) -> None:
        try:
            res = await client.get(f"/collections/{collection_name}", headers=self._headers())
            if res.status_code == 200:
                return
            create_payload = {
                "vectors": {
                    "size": vector_size,
                    "distance": distance,
                }
            }
            create_res = await client.put(
                f"/collections/{collection_name}",
                json=create_payload,
                headers=self._headers(),
            )
            create_res.raise_for_status()
        except Exception as exc:
            logger.debug(f"Qdrant collection ensure skipped for {collection_name}: {exc}")

    async def _dense_search(
        self,
        *,
        collection_name: str,
        vector: list[float],
        output_fields: list[str],
        top_k: int,
        graph_name: str,
    ) -> list[dict[str, Any]]:
        client = await self._get_client()
        search_payload: dict[str, Any] = {
            "vector": vector,
            "limit": top_k,
            "with_payload": output_fields if output_fields else True,
        }
        filter_clause = self._build_filter(graph_name, collection_name)
        if filter_clause:
            search_payload["filter"] = filter_clause

        try:
            response = await client.post(
                f"/collections/{collection_name}/points/search",
                json=search_payload,
                headers=self._headers(),
            )
            if response.status_code == 404:
                logger.debug(f"Qdrant collection {collection_name} does not exist")
                return []
            response.raise_for_status()
            hits = response.json().get("result") or []
            return [self._point_to_row(hit) for hit in hits]
        except Exception as exc:
            logger.warning(
                f"Qdrant vector search failed for {collection_name}: {type(exc).__name__}: {exc}"
            )
            return []

    async def _lexical_scroll(
        self,
        *,
        query_text: str,
        collection_name: str,
        output_fields: list[str],
        text_fields: list[str],
        top_k: int,
        graph_name: str,
    ) -> list[dict[str, Any]]:
        client = await self._get_client()
        scroll_payload: dict[str, Any] = {
            "limit": max(top_k * 5, 50),
            "with_payload": output_fields if output_fields else True,
        }
        filter_clause = self._build_filter(graph_name, collection_name)
        if filter_clause:
            scroll_payload["filter"] = filter_clause

        try:
            response = await client.post(
                f"/collections/{collection_name}/points/scroll",
                json=scroll_payload,
                headers=self._headers(),
            )
            if response.status_code == 404:
                return []
            response.raise_for_status()
            points = response.json().get("result", {}).get("points") or []
            rows = [self._point_to_row(point) for point in points]

            terms = [term.lower() for term in query_text.split() if len(term) > 2]
            if not terms or not text_fields:
                return rows[:top_k]

            ranked: list[tuple[int, dict[str, Any]]] = []
            for row in rows:
                haystack = " ".join(str(row.get(field) or "") for field in text_fields).lower()
                matches = sum(1 for term in terms if term in haystack)
                if matches > 0:
                    ranked.append((matches, row))
            ranked.sort(key=lambda item: item[0], reverse=True)
            return [row for _, row in ranked[:top_k]]
        except Exception as exc:
            logger.warning(
                f"Qdrant lexical scroll failed for {collection_name}: {type(exc).__name__}: {exc}"
            )
            return []

    @staticmethod
    def _point_to_row(point: dict[str, Any]) -> dict[str, Any]:
        row = dict(point.get("payload") or {})
        row["id"] = point.get("id")
        score = point.get("score")
        if score is not None:
            row["distance"] = score
        return row


# Backward-compatible alias for existing imports
QdrantStorage = QdrantVectorStorage

__all__ = [
    "QdrantStorage",
    "QdrantVectorStorage",
    "VectorEmbedder",
]

