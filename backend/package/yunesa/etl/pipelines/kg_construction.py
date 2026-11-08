"""Airflow task handlers for Academic Knowledge Graph construction."""

from __future__ import annotations

import logging

from yunesa.etl.utils.logging import log_event, result_fields, timed_event

logger = logging.getLogger("etl-worker")


def _kg_load_data(config):
    """Fetch graph-ready source rows from PostgreSQL/Supabase into shared KG artifacts."""
    from yunesa.etl.services.kg_service import run_kg_data_load

    with timed_event(logger, "kg.load_data", mode=config.mode):
        result = run_kg_data_load(
            mode=config.mode,
            sample_size=config.sample_size,
        )
    log_event(logger, "kg.load_data.result", **result_fields(result))


def _kg_extract_entities(config):
    """Optionally run GLiNER extraction over publication text."""
    from yunesa.etl.services.kg_service import run_kg_entity_extraction

    with timed_event(logger, "kg.extract_entities", mode=config.mode):
        result = run_kg_entity_extraction(
            mode=config.mode,
            sample_size=config.sample_size,
        )
    log_event(logger, "kg.extract_entities.result", **result_fields(result))


def _kg_build_graph(config):
    """Build the NetworkX property graph and export KG artifacts."""
    from yunesa.etl.services.kg_service import run_kg_build

    with timed_event(logger, "kg.build_graph", mode=config.mode):
        result = run_kg_build(
            mode=config.mode,
            sample_size=config.sample_size,
        )
    validation = result.get("validation") or {}
    extraction = result.get("extraction") or {}
    resolution = ((result.get("entity_resolution") or {}).get("report") or {})
    suggestions = result.get("llm_suggestions") or {}
    input_rows = result.get("input_rows") or {}
    log_event(
        logger,
        "kg.build_graph.result",
        mode=result.get("mode"),
        graph_name=result.get("graph_name"),
        papers=input_rows.get("papers"),
        lecturers=input_rows.get("lecturers"),
        links=input_rows.get("links"),
        extracted_entities=extraction.get("entities"),
        extracted_keywords=extraction.get("keywords"),
        nodes=validation.get("total_nodes"),
        edges=validation.get("total_edges"),
        unresolved_concepts=resolution.get("unresolved_local_concepts"),
        duplicate_groups=resolution.get("duplicate_candidate_groups"),
        llm_suggestions=suggestions.get("suggestion_count"),
    )


def _kg_write_neo4j(config):
    """Write graph database (Memgraph/Neo4j) independently from vector indexing."""
    from yunesa.etl.services.kg_service import run_kg_write_neo4j

    with timed_event(logger, "kg.write_neo4j", mode=config.mode):
        result = run_kg_write_neo4j(mode=config.mode, sample_size=config.sample_size)
    payload = result.get("result") or {}
    log_event(
        logger,
        "kg.write_neo4j.result",
        status=result.get("status"),
        enabled=result.get("enabled"),
        clear_existing=result.get("clear_existing"),
        nodes_written=payload.get("nodes_written"),
        edges_written=payload.get("edges_written"),
    )


def _kg_write_milvus(config):
    """Write vector store (Qdrant/Milvus) with independent retry and persistent embedding cache."""
    from yunesa.etl.services.kg_service import run_kg_write_milvus

    with timed_event(logger, "kg.write_milvus", mode=config.mode):
        result = run_kg_write_milvus(mode=config.mode, sample_size=config.sample_size)
    payload = result.get("result") or {}
    collections = payload.get("collections") or {}
    log_event(
        logger,
        "kg.write_milvus.result",
        status=result.get("status"),
        enabled=result.get("enabled"),
        clear_existing=result.get("clear_existing"),
        collections=len(collections),
        inserted_rows=sum(item.get("inserted_rows", 0) for item in collections.values()),
    )


def _kg_write_stores(config):
    """Write the built graph into both graph and vector stores."""
    from yunesa.etl.services.kg_service import run_kg_write_stores

    with timed_event(logger, "kg.write_stores", mode=config.mode):
        result = run_kg_write_stores(
            mode=config.mode,
            sample_size=config.sample_size,
        )
    log_event(logger, "kg.write_stores.result", **result_fields(result))


KG_TASKS = {
    "kg_load_data": _kg_load_data,
    "kg_extract_entities": _kg_extract_entities,
    "kg_build_graph": _kg_build_graph,
    "kg_write_neo4j": _kg_write_neo4j,
    "kg_write_milvus": _kg_write_milvus,
    "kg_write_stores": _kg_write_stores,
}

TASKS = KG_TASKS
