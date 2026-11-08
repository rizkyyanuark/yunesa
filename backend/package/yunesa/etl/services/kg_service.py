"""Compatibility facade re-exporting Knowledge Graph construction services for ETL worker tasks."""

from __future__ import annotations

from yunesa.knowledge.services.kg_service import (
    run_kg_build,
    run_kg_data_load,
    run_kg_entity_extraction,
)
from yunesa.knowledge.services.kg_storage_service import (
    run_kg_write_milvus,
    run_kg_write_neo4j,
    run_kg_write_stores,
)

__all__ = [
    "run_kg_build",
    "run_kg_data_load",
    "run_kg_entity_extraction",
    "run_kg_write_milvus",
    "run_kg_write_neo4j",
    "run_kg_write_stores",
]
