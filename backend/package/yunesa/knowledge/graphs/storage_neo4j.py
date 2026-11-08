"""Bolt graph persistence and inspection for Neo4j/AuraDB and Memgraph."""

from __future__ import annotations

import os
import re
import logging
from collections import defaultdict
from collections.abc import Iterable
from typing import Any
import networkx as nx

from yunesa.knowledge.utils.text_processing import (
    safe_str,
    canonical_relation,
)
from yunesa.knowledge.graphs.builder import serialisable_graph_copy

logger = logging.getLogger(__name__)


def _neo4j_label(value: Any) -> str:
    label = re.sub(r"[^A-Za-z0-9_]", "", safe_str(value))
    if not label:
        return "KGNode"
    if label[0].isdigit():
        label = f"N{label}"
    return label


def _neo4j_relation(value: Any) -> str:
    relation = canonical_relation(value)
    relation = re.sub(r"[^A-Za-z0-9_]", "_", relation.upper()).strip("_")
    return relation or "RELATED_TO"


def neo4j_credential_status() -> dict[str, bool]:
    """Return non-secret Neo4j credential availability for notebook debugging."""
    return {
        "NEO4J_URI": bool(os.getenv("NEO4J_URI")),
        "NEO4J_USERNAME": bool(os.getenv("NEO4J_USERNAME")),
        "NEO4J_PASSWORD": bool(os.getenv("NEO4J_PASSWORD")),
        "NEO4J_DATABASE": bool(os.getenv("NEO4J_DATABASE")),
    }


def neo4j_uri_for_driver(uri: str | None = None) -> str:
    """Return Neo4j URI adjusted for local host execution or container environment."""
    uri = uri or os.getenv("NEO4J_URI") or "bolt://localhost:7687"
    if "graph:" in uri:
        import socket
        try:
            socket.gethostbyname("graph")
        except socket.gaierror:
            uri = uri.replace("://graph:", "://localhost:")

    trust_self_signed = os.getenv("NEO4J_TRUST_SELF_SIGNED", "0") == "1"
    if trust_self_signed:
        uri = uri.replace("neo4j+s://", "neo4j+ssc://").replace("bolt+s://", "bolt+ssc://")
    return uri


def _connection_settings(
    uri: str | None, username: str | None, password: str | None,
    database: str | None, backend: str | None,
) -> tuple[str, tuple[str, str], str, str]:
    backend = backend or os.getenv('YUNESA_GRAPH_BACKEND', 'neo4j')
    if backend not in ('neo4j', 'memgraph'):
        raise ValueError('YUNESA_GRAPH_BACKEND must be neo4j or memgraph')
    uri = neo4j_uri_for_driver(uri)
    username = username if username is not None else os.getenv('NEO4J_USERNAME', '')
    password = password if password is not None else os.getenv('NEO4J_PASSWORD', '')
    database = database or os.getenv('NEO4J_DATABASE') or ('memgraph' if backend == 'memgraph' else 'neo4j')
    if backend == 'neo4j' and (not username or not password):
        raise ValueError('Set NEO4J_USERNAME and NEO4J_PASSWORD for the Neo4j backend')
    if backend == 'memgraph' and username and not password:
        raise ValueError('An authenticated Memgraph user requires NEO4J_PASSWORD')
    # An empty Memgraph username selects its default unauthenticated connection.
    auth = (username, password) if username else ('', '')
    return uri, auth, database, backend


def _ensure_memgraph_schema(session: Any) -> None:
    constraints = session.run('SHOW CONSTRAINT INFO').data()
    exists = any(row.get('constraint type') == 'unique' and row.get('label') == 'KGNode'
                 and set(row.get('properties', [])) == {'id', 'graph_name'} for row in constraints)
    if not exists:
        session.run('CREATE CONSTRAINT ON (n:KGNode) ASSERT n.id, n.graph_name IS UNIQUE').consume()
    indices = session.run('SHOW INDEX INFO').data()
    for label, property_name in (('KGNode', 'id'), ('KGNode', 'graph_name'),
                                 ('Publication', 'year'), ('Concept', 'name')):
        if not any(row.get('label') == label and row.get('property') == property_name for row in indices):
            session.run(f'CREATE INDEX ON :{label}({property_name})').consume()


def write_graph_to_neo4j(
    graph: nx.MultiDiGraph,
    *,
    uri: str | None = None,
    username: str | None = None,
    password: str | None = None,
    database: str | None = None,
    graph_name: str = "yunesa_academic_kg",
    clear_existing: bool = False,
    batch_size: int = 500,
    backend: str | None = None,
) -> dict[str, int]:
    """Write a graph using the explicitly selected Bolt backend."""
    try:
        from neo4j import GraphDatabase
    except ImportError as exc:
        raise ImportError("Install neo4j first: pip install neo4j") from exc

    uri, auth, database, backend = _connection_settings(uri, username, password, database, backend)
    if batch_size < 1 or not graph_name.strip():
        raise ValueError('A nonempty graph_name and positive batch_size are required')

    serialisable = serialisable_graph_copy(graph)
    node_rows_by_label_pair: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for node_id, data in serialisable.nodes(data=True):
        node_type = _neo4j_label(data.get("node_type", "KGNode"))
        raw_concept_type = data.get("concept_type", "")
        concept_sublabel = ""
        if node_type == "Concept" and raw_concept_type:
            from yunesa.knowledge.utils.text_processing import canonical_concept_type
            concept_sublabel = canonical_concept_type(raw_concept_type)
        props = {**data, "id": node_id, "graph_name": graph_name}
        node_rows_by_label_pair[(node_type, concept_sublabel)].append(props)

    edge_rows_by_relation: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for source, target, key, data in serialisable.edges(keys=True, data=True):
        relation = _neo4j_relation(data.get("relation", "RELATED_TO"))
        edge_rows_by_relation[relation].append(
            {
                "source": source,
                "target": target,
                "edge_key": str(key),
                "graph_name": graph_name,
                "props": {**data, "graph_name": graph_name, "edge_key": str(key)},
            }
        )

    def chunks(rows: list[dict[str, Any]]) -> Iterable[list[dict[str, Any]]]:
        for start in range(0, len(rows), batch_size):
            yield rows[start : start + batch_size]

    driver = GraphDatabase.driver(uri, auth=auth)
    try:
        with driver.session(database=database) as session:
            if backend == 'memgraph':
                _ensure_memgraph_schema(session)
            else:
                session.run(
                    "CREATE CONSTRAINT kg_node_id IF NOT EXISTS FOR (n:KGNode) REQUIRE n.id IS UNIQUE"
                ).consume()
                session.run(
                    "CREATE INDEX kg_node_graph_name IF NOT EXISTS "
                    "FOR (n:KGNode) ON (n.graph_name)"
                ).consume()
                session.run(
                    "CREATE INDEX kg_publication_year IF NOT EXISTS "
                    "FOR (n:Publication) ON (n.year)"
                ).consume()
                session.run(
                    "CREATE INDEX kg_concept_name IF NOT EXISTS "
                    "FOR (n:Concept) ON (n.name)"
                ).consume()
                session.run(
                    "CREATE FULLTEXT INDEX kgnode_fts_idx IF NOT EXISTS "
                    "FOR (n:Lecturer|Publication|Concept|Venue|Department|Faculty|Institution|KGNode) "
                    "ON EACH [n.label, n.name, n.title, n.nama_dosen, n.nama_norm, "
                    "n.description, n.abstract, n.keywords, n.tldr]"
                ).consume()

            if clear_existing:
                session.run(
                    "MATCH (n:KGNode {graph_name: $graph_name}) DETACH DELETE n",
                    graph_name=graph_name,
                ).consume()

            nodes_written = 0
            for (label, sub_label), rows in node_rows_by_label_pair.items():
                label_expr = f":{label}:{sub_label}" if sub_label else f":{label}"
                identity = '{id: row.id, graph_name: row.graph_name}' if backend == 'memgraph' else '{id: row.id}'
                query = (
                    f"UNWIND $rows AS row MERGE (n:KGNode{label_expr} {identity}) SET n += row"
                )
                for batch in chunks(rows):
                    session.run(query, rows=batch).consume()
                    nodes_written += len(batch)

            edges_written = 0
            for relation, rows in edge_rows_by_relation.items():
                query = (
                    f"UNWIND $rows AS row "
                    f"MATCH (s:KGNode {{id: row.source, graph_name: row.graph_name}}) "
                    f"MATCH (t:KGNode {{id: row.target, graph_name: row.graph_name}}) "
                    f"MERGE (s)-[r:{relation} {{edge_key: row.edge_key, graph_name: row.graph_name}}]->(t) "
                    f"SET r += row.props"
                )
                for batch in chunks(rows):
                    session.run(query, rows=batch).consume()
                    edges_written += len(batch)

        return {"nodes_written": nodes_written, "edges_written": edges_written}
    finally:
        driver.close()


def inspect_neo4j_graph(
    *,
    uri: str | None = None,
    username: str | None = None,
    password: str | None = None,
    database: str | None = None,
    graph_name: str | None = None,
    backend: str | None = None,
) -> dict[str, Any]:
    """Read storage counts from Neo4j/AuraDB without mutating data."""
    try:
        from neo4j import GraphDatabase
    except ImportError as exc:
        raise ImportError("Install neo4j first: pip install neo4j") from exc

    uri, auth, database, backend = _connection_settings(uri, username, password, database, backend)

    graph_filter = "WHERE n.graph_name = $graph_name" if graph_name else ""
    publication_filter = "WHERE p.graph_name = $graph_name" if graph_name else ""
    rel_filter = "WHERE r.graph_name = $graph_name" if graph_name else ""
    params = {"graph_name": graph_name}

    driver = GraphDatabase.driver(uri, auth=auth)
    try:
        with driver.session(database=database) as session:
            node_count = session.run(
                f"MATCH (n:KGNode) {graph_filter} RETURN count(n) AS count",
                **params,
            ).single()["count"]
            rel_count = session.run(
                f"MATCH (:KGNode)-[r]->(:KGNode) {rel_filter} RETURN count(r) AS count",
                **params,
            ).single()["count"]
            label_rows = session.run(
                f"""
                MATCH (n:KGNode)
                {graph_filter}
                UNWIND labels(n) AS label
                WITH label, count(*) AS count
                WHERE label <> 'KGNode'
                RETURN label, count
                ORDER BY count DESC, label
                """,
                **params,
            ).data()
            relationship_rows = session.run(
                f"""
                MATCH (:KGNode)-[r]->(:KGNode)
                {rel_filter}
                RETURN type(r) AS relation, count(*) AS count
                ORDER BY count DESC, relation
                """,
                **params,
            ).data()
            sample_publications = session.run(
                f"""
                MATCH (p:KGNode:Publication)
                {publication_filter}
                RETURN p.id AS id, p.title AS title, p.tldr AS tldr, p.keywords AS keywords
                LIMIT 5
                """,
                **params,
            ).data()
        return {
            "backend": backend,
            "database": database,
            "graph_name": graph_name or "",
            "nodes": node_count,
            "relationships": rel_count,
            "label_counts": label_rows,
            "relationship_counts": relationship_rows,
            "sample_publications": sample_publications,
        }
    finally:
        driver.close()
