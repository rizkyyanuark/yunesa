from __future__ import annotations

import httpx
import pytest

from yunesa.graphrag.academic_graphrag import AcademicGraphRAGService
from yunesa.graphrag.storage.qdrant_storage import QdrantVectorStorage


@pytest.mark.asyncio
async def test_qdrant_dense_search_success():
    records = [
        {
            "id": "uuid-1",
            "score": 0.89,
            "payload": {
                "graphName": "yunesa_academic_kg",
                "title": "Machine Learning in Higher Education",
                "content": "Deep learning models for student evaluation...",
                "year": 2024,
            },
        },
        {
            "id": "uuid-2",
            "score": 0.75,
            "payload": {
                "graphName": "yunesa_academic_kg",
                "title": "Natural Language Processing for Indonesian",
                "content": "IndoBERT fine-tuning results...",
                "year": 2023,
            },
        },
    ]

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/collections/PaperChunk/points/search"
        assert request.headers.get("api-key") == "test-key"
        return httpx.Response(200, json={"result": records})

    client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler), base_url="http://vector:6333")
    storage = QdrantVectorStorage(
        uri="http://vector:6333",
        api_key="test-key",
        client=client,
    )

    results = await storage.query(
        query_text="machine learning",
        collection_name="PaperChunk",
        output_fields=["title", "content", "year"],
        text_fields=["title", "content"],
        top_k=2,
        graph_name="yunesa_academic_kg",
        query_vector=[0.1, 0.2, 0.3],
    )

    assert len(results) == 2
    assert results[0]["title"] == "Machine Learning in Higher Education"
    assert results[0]["id"] == "uuid-1"
    assert results[0]["distance"] == 0.89
    await storage.close()


@pytest.mark.asyncio
async def test_qdrant_collection_not_found_returns_empty():
    async def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"status": {"error": "Collection not found"}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler), base_url="http://vector:6333")
    storage = QdrantVectorStorage(
        uri="http://vector:6333",
        client=client,
    )

    results = await storage.query(
        query_text="missing query",
        collection_name="NonExistentCollection",
        output_fields=["title"],
        text_fields=["title"],
        top_k=5,
        graph_name="yunesa_academic_kg",
        query_vector=[0.1, 0.2],
    )

    assert results == []
    await storage.close()


@pytest.mark.asyncio
async def test_qdrant_lexical_scroll_fallback():
    records = [
        {
            "id": "uuid-1",
            "payload": {
                "graphName": "yunesa_academic_kg",
                "title": "Deep Learning for Computer Vision",
                "content": "Image processing techniques",
            },
        },
        {
            "id": "uuid-2",
            "payload": {
                "graphName": "yunesa_academic_kg",
                "title": "Graph Algorithms",
                "content": "Shortest path and centrality",
            },
        },
    ]

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/collections/PaperChunk/points/scroll"
        return httpx.Response(200, json={"result": {"points": records}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler), base_url="http://vector:6333")
    storage = QdrantVectorStorage(
        uri="http://vector:6333",
        client=client,
    )

    results = await storage.query(
        query_text="deep learning vision",
        collection_name="PaperChunk",
        output_fields=["title", "content"],
        text_fields=["title", "content"],
        top_k=1,
        graph_name="yunesa_academic_kg",
        query_vector=None,
        embed_if_missing=False,
    )

    assert len(results) == 1
    assert results[0]["title"] == "Deep Learning for Computer Vision"
    await storage.close()


@pytest.mark.asyncio
async def test_qdrant_upsert_batches_and_provisions_collection():
    upserted_batches = []

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/collections/PaperChunk":
            # Simulate collection missing initially
            return httpx.Response(404)
        if request.method == "PUT" and request.url.path == "/collections/PaperChunk":
            return httpx.Response(200, json={"result": True})
        if request.method == "PUT" and request.url.path == "/collections/PaperChunk/points":
            data = request.read().decode("utf-8")
            upserted_batches.append(data)
            return httpx.Response(200, json={"result": {"status": "completed"}})
        return httpx.Response(400)

    client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler), base_url="http://vector:6333")
    storage = QdrantVectorStorage(uri="http://vector:6333", client=client)

    test_items = [
        {"id": f"p-{i}", "embedding": [0.1, 0.2, 0.3], "title": f"Paper {i}"}
        for i in range(150)
    ]

    count = await storage.upsert("PaperChunk", test_items, batch_size=64)
    assert count == 150
    # 150 items with batch_size 64 produces 3 batch requests (64 + 64 + 22)
    assert len(upserted_batches) == 3
    await storage.close()


@pytest.mark.asyncio
async def test_qdrant_health_check():
    async def mock_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/readyz":
            return httpx.Response(200)
        return httpx.Response(500)

    client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler), base_url="http://vector:6333")
    storage = QdrantVectorStorage(uri="http://vector:6333", client=client)

    is_healthy = await storage.health_check()
    assert is_healthy is True
    await storage.close()


def test_academic_graphrag_resolves_qdrant(monkeypatch):
    monkeypatch.setenv("YUNESA_VECTOR_BACKEND", "qdrant")
    monkeypatch.setenv("QDRANT_URI", "http://custom-vector:6333")
    monkeypatch.setenv("QDRANT_API_KEY", "secret-key")

    storage = AcademicGraphRAGService._resolve_vector_storage()
    assert isinstance(storage, QdrantVectorStorage)
    assert storage.uri == "http://custom-vector:6333"
    assert storage.api_key == "secret-key"
