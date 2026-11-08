import os
from importlib import import_module
from yunesa import config as global_config
from .factory import KnowledgeBaseFactory
from .manager import KnowledgeBaseManager

_LITE_MODE = os.environ.get("LITE_MODE", "").lower() in ("true", "1")
_SKIP_APP_INIT = os.environ.get("YUNESA_SKIP_APP_INIT") == "1"

if not _LITE_MODE:
    from .graphs.core_graph_service import CoreGraphService
    from .implementations.milvus import MilvusKB, AcademicKGVectorStore

    KnowledgeBaseFactory.register(
        "milvus", MilvusKB, {
            "description": (
                "Production-grade vector knowledge base based on Milvus "
                "for UNESA Academic Knowledge Graph deployment"
            )}
    )

work_dir = os.path.join(global_config.save_dir, "knowledge_base_data")
knowledge_base = KnowledgeBaseManager(work_dir)

if _LITE_MODE or _SKIP_APP_INIT:
    from ..utils import logger

    class _LiteGraphStub:
        """Graph database placeholder in Lite mode; all operations report unavailable."""

        def is_running(self):
            return False

        def get_graph_info(self, *args, **kwargs):
            return None

    graph_base = _LiteGraphStub()
    GraphDatabase = _LiteGraphStub
    if _LITE_MODE:
        logger.info("LITE_MODE enabled, knowledge graph services disabled")
    else:
        logger.info(
            "YUNESA_SKIP_APP_INIT enabled, knowledge graph services disabled for current process")
else:
    class _LazyGraphBaseProxy:
        """Lazy proxy for CoreGraphService to avoid network calls on module import."""

        def __init__(self):
            self._service = None

        def _get_service(self):
            if self._service is None:
                self._service = CoreGraphService()
            return self._service

        def __getattr__(self, name):
            return getattr(self._get_service(), name)

    graph_base = _LazyGraphBaseProxy()
    GraphDatabase = CoreGraphService

__all__ = [
    "GraphDatabase",
    "knowledge_base",
    "graph_base",
    "AcademicKGBuilder",
    "AcademicKGVectorStore",
    "KGConfig",
    "AcademicExtractionConfig",
    "MilvusVectorIndexConfig",
    "run_kg_build",
    "write_graph_to_neo4j",
    "write_vector_index_to_milvus",
]

_PIPELINE_EXPORTS = {
    'AcademicKGBuilder': 'graphs.builder',
    'AcademicKGVectorStore': 'implementations.milvus',
    'KGConfig': 'config',
    'AcademicExtractionConfig': 'config',
    'MilvusVectorIndexConfig': 'config',
    'run_kg_build': 'services.kg_service',
    'write_graph_to_neo4j': 'graphs.storage_neo4j',
    'write_vector_index_to_milvus': 'implementations.milvus',
    'IeeeSemanticIndex': 'utils.ieee_semantic',
    'AcademicConceptResolver': 'utils.concept_resolver',
    'graph_to_frames': 'graphs.builder',
    'serialisable_graph_copy': 'graphs.builder',
    'graph_quality_report': 'eval.quality_gates',
    'entity_resolution_report': 'eval.entity_resolution',
    'write_llm_alias_suggestions': 'eval.entity_resolution',
    'summarize_extracted_elements': 'parser.ner_extraction',
    'extract_academic_elements_with_gliner_glirel': 'parser.ner_extraction',
    'DEFAULT_GLINER_MODEL': 'constants',
    'DEFAULT_GLIREL_MODEL': 'constants',
    'LLMAliasSuggestionConfig': 'config',
}
__all__ += list(_PIPELINE_EXPORTS)


def __getattr__(name: str):
    module = _PIPELINE_EXPORTS.get(name)
    if module is None:
        raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
    value = getattr(import_module(f'{__name__}.{module}'), name)
    globals()[name] = value
    return value
