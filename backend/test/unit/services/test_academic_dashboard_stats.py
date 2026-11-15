from __future__ import annotations

import asyncio
import sys
import types
from unittest.mock import AsyncMock

from yunesa.services.academic_dashboard_service import AcademicDashboardService


def test_postgres_stats_report_error_when_connection_fails(monkeypatch):
    fake_asyncpg = types.ModuleType("asyncpg")

    async def failing_connect(**kwargs):
        raise ConnectionRefusedError("postgres unreachable")

    fake_asyncpg.connect = failing_connect
    monkeypatch.setitem(sys.modules, "asyncpg", fake_asyncpg)

    service = AcademicDashboardService()
    result = asyncio.run(service._collect_postgres())

    assert result["papers_count"] == 0
    assert result["source_status"]["status"] == "error"


def test_collect_keeps_storage_layers_separate(monkeypatch):
    service = AcademicDashboardService(graph_name="yunesa_academic_kg")
    monkeypatch.setattr(
        service,
        "_collect_postgres",
        AsyncMock(
            return_value={
                "papers_count": 50,
                "lecturers_count": 116,
                "authorship_links_count": 125,
                "papers_with_abstract": 48,
                "papers_with_keywords": 45,
                "papers_with_tldr": 50,
                "source_status": {"status": "ready", "detail": "ok"},
            }
        ),
    )
    monkeypatch.setattr(
        service,
        "_collect_neo4j",
        AsyncMock(
            return_value={
                "total_nodes": 687,
                "total_edges": 900,
                "entity_distribution": {"Publication": 50, "Lecturer": 116},
                "relationship_distribution": {"HAS_AUTHOR": 125},
                "source_status": {"status": "ready", "detail": "ok"},
            }
        ),
    )
    monkeypatch.setattr(
        service,
        "_collect_milvus",
        AsyncMock(
            return_value={
                "total_records": 1090,
                "collections": {
                    "PaperChunk": 50,
                    "EntityEmbedding": 687,
                    "ContentKeyword": 50,
                },
                "database": "default",
                "source_status": {"status": "ready", "detail": "ok"},
            }
        ),
    )

    result = asyncio.run(service.collect())

    assert result["papers_count"] == 50
    assert result["kg_nodes_count"] == 687
    assert result["vector_records_count"] == 1090
    assert result["graph_name"] == "yunesa_academic_kg"
    assert result["embedding_dimension"] == 1024
    assert result["source_status"]["postgres"]["status"] == "ready"
    assert result["storage_consistency"]["status"] == "in_sync"


def test_storage_consistency_reports_cross_store_drift():
    result = AcademicDashboardService._storage_consistency(
        postgres={
            "papers_count": 51,
            "lecturers_count": 128,
            "authorship_links_count": 140,
            "source_status": {"status": "ready"},
        },
        neo4j={
            "entity_distribution": {"Publication": 50, "Lecturer": 128},
            "relationship_distribution": {"HAS_AUTHOR": 139},
            "source_status": {"status": "ready"},
        },
        milvus={
            "collections": {"ContentKeyword": 49},
            "source_status": {"status": "ready"},
        },
    )

    assert result["status"] == "drift_detected"
    assert result["checks"]["publications"]["gap"] == 1
    assert result["checks"]["authorship_links"]["gap"] == 1
    assert result["checks"]["content_keywords"]["gap"] == 2
