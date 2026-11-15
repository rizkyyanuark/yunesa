import json

import yaml

from yunesa.services.entity_resolution_service import EntityResolutionCurationStore


def test_entity_resolution_store_sync_approve_and_export(tmp_path):
    source_path = tmp_path / "suggestions.json"
    store_path = tmp_path / "store.json"
    base_aliases_path = tmp_path / "concept_aliases.yml"
    export_path = tmp_path / "concept_aliases.approved.yml"

    source_path.write_text(
        json.dumps(
            {
                "suggestions": [
                    {
                        "raw_label": "SVM",
                        "suggested_canonical_label": "Support Vector Machine",
                        "suggested_canonical_key": "support_vector_machine",
                        "concept_type": "Model",
                        "action": "exact_synonym",
                        "confidence": 0.99,
                        "aliases": ["SVM"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    base_aliases_path.write_text(
        yaml.safe_dump(
            {
                "aliases": {
                    "auc": {
                        "canonical_label": "AUC",
                        "concept_type": "Metric",
                        "aliases": ["AUC", "area under the curve"],
                    }
                }
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    store = EntityResolutionCurationStore(store_path=store_path)
    result = store.sync_suggestions(source_path=source_path)

    assert result["imported"] == 1
    listed = store.list_suggestions()
    assert listed["total"] == 1
    suggestion = listed["items"][0]

    approved = store.approve(
        suggestion["id"],
        canonical_label="Support Vector Machine",
        canonical_key="support_vector_machine",
        concept_type="Model",
        aliases=["SVM", "support vector machine"],
        reviewer="pytest",
    )

    assert approved["decision"]["status"] == "approved"
    export = store.export_aliases(output_path=export_path, base_path=base_aliases_path)
    exported = yaml.safe_load(export_path.read_text(encoding="utf-8"))

    assert export["approved_count"] == 1
    assert "auc" in exported["aliases"]
    assert exported["aliases"]["support_vector_machine"]["source"] == "ui_approved_alias"
    assert "SVM" in exported["aliases"]["support_vector_machine"]["aliases"]


def test_entity_resolution_store_s3_roundtrip(monkeypatch):
    import fsspec
    from fsspec.implementations.memory import MemoryFileSystem
    from yunesa.services import entity_resolution_service as ers

    MemoryFileSystem.store.clear()
    mem_fs = fsspec.filesystem("memory")
    captured: dict[str, object] = {}

    def fake_filesystem(proto, **kwargs):
        captured["proto"] = proto
        captured["kwargs"] = kwargs
        return mem_fs

    monkeypatch.setattr(ers.fsspec, "filesystem", fake_filesystem)
    monkeypatch.setenv("ETL_STORAGE_TYPE", "s3")
    monkeypatch.setenv("AWS_ENDPOINT_URL", "http://minio:9000")
    monkeypatch.setenv("AWS_S3_BUCKET", "yunesa-etl")
    monkeypatch.setenv("AWS_S3_PATH", "etl/data")
    monkeypatch.setenv("MINIO_ROOT_USER", "yunesa")
    monkeypatch.setenv("MINIO_ROOT_PASSWORD", "minio-secret")
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)

    base = "s3://yunesa-etl/etl/data/kg/entity_resolution"
    suggestions_key = "yunesa-etl/etl/data/kg/entity_resolution/concept_alias_suggestions.json"
    base_aliases_key = "yunesa-etl/etl/data/kg/entity_resolution/concept_aliases.yml"
    approved_key = "yunesa-etl/etl/data/kg/entity_resolution/concept_aliases.approved.yml"

    with mem_fs.open(suggestions_key, "w", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "suggestions": [
                        {
                            "raw_label": "CNN",
                            "suggested_canonical_label": "Convolutional Neural Network",
                            "suggested_canonical_key": "convolutional_neural_network",
                            "concept_type": "Model",
                            "action": "exact_synonym",
                            "confidence": 0.97,
                            "aliases": ["CNN"],
                        }
                    ]
                }
            )
        )

    with mem_fs.open(base_aliases_key, "w", encoding="utf-8") as handle:
        handle.write(
            yaml.safe_dump(
                {
                    "aliases": {
                        "auc": {
                            "canonical_label": "AUC",
                            "concept_type": "Metric",
                            "aliases": ["AUC"],
                        }
                    }
                },
                sort_keys=False,
            )
        )

    store = ers.EntityResolutionCurationStore()
    assert store.store_path == f"{base}/alias_curation_store.json"

    sync_res = store.sync_suggestions()
    assert sync_res["imported"] == 1
    assert captured["proto"] == "s3"
    assert captured["kwargs"]["key"] == "yunesa"
    assert captured["kwargs"]["secret"] == "minio-secret"
    assert captured["kwargs"]["client_kwargs"] == {"endpoint_url": "http://minio:9000"}

    listed = store.list_suggestions()
    assert listed["total"] == 1
    assert listed["suggestions_path"] == f"{base}/concept_alias_suggestions.json"
    suggestion_id = listed["items"][0]["id"]

    approved = store.approve(
        suggestion_id,
        canonical_label="Convolutional Neural Network",
        aliases=["CNN", "ConvNet"],
        reviewer="s3-pytest",
    )
    assert approved["decision"]["status"] == "approved"

    export = store.export_aliases()
    assert export["approved_count"] == 1
    assert export["export_path"] == f"{base}/concept_aliases.approved.yml"

    with mem_fs.open(approved_key, "r", encoding="utf-8") as handle:
        exported = yaml.safe_load(handle.read())
    assert "auc" in exported["aliases"]
    assert exported["aliases"]["convolutional_neural_network"]["source"] == "ui_approved_alias"
    assert "ConvNet" in exported["aliases"]["convolutional_neural_network"]["aliases"]

    rejected = store.reject(suggestion_id, reason="superseded", reviewer="s3-pytest")
    assert rejected["decision"]["status"] == "rejected"
