import hashlib
import json
import os
import re
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import fsspec
import yaml


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_s3_uri(value: str | Path | None) -> bool:
    return isinstance(value, str) and value.startswith("s3://")


def _normalize_target(value: str | Path) -> str | Path:
    if _is_s3_uri(value):
        return str(value)
    return Path(value)


def _s3_storage_options() -> dict[str, Any]:
    endpoint = (
        os.getenv("AWS_ENDPOINT_URL")
        or os.getenv("MINIO_ENDPOINT")
        or os.getenv("MINIO_URI")
        or "http://minio:9000"
    ).strip()
    if endpoint and not endpoint.startswith(("http://", "https://")):
        endpoint = f"http://{endpoint}"
    key = (
        os.getenv("AWS_ACCESS_KEY_ID")
        or os.getenv("MINIO_ROOT_USER")
        or os.getenv("MINIO_ACCESS_KEY")
        or "yunesa"
    ).strip()
    secret = (
        os.getenv("AWS_SECRET_ACCESS_KEY")
        or os.getenv("MINIO_ROOT_PASSWORD")
        or os.getenv("MINIO_SECRET_KEY")
        or os.getenv("GLOBAL_PASSWORD")
        or ""
    ).strip()
    options: dict[str, Any] = {"client_kwargs": {"endpoint_url": endpoint}}
    if key:
        options["key"] = key
    if secret:
        options["secret"] = secret
    return options


def _get_s3_fs() -> Any:
    return fsspec.filesystem("s3", **_s3_storage_options())


def _s3_path(uri: str) -> str:
    return uri[len("s3://"):]


def _ensure_s3_bucket(fs: Any, uri: str) -> None:
    parts = _s3_path(uri).split("/", 1)
    bucket = parts[0] if parts else ""
    if bucket and not fs.exists(bucket):
        fs.makedirs(bucket, exist_ok=True)


def _target_exists(target: str | Path) -> bool:
    if _is_s3_uri(target):
        fs = _get_s3_fs()
        return bool(fs.exists(_s3_path(str(target))))
    return Path(target).exists()


def _read_text(target: str | Path) -> str:
    if _is_s3_uri(target):
        fs = _get_s3_fs()
        with fs.open(_s3_path(str(target)), "r", encoding="utf-8") as handle:
            return handle.read()
    return Path(target).read_text(encoding="utf-8")


def _write_text(target: str | Path, content: str) -> None:
    if _is_s3_uri(target):
        fs = _get_s3_fs()
        uri = str(target)
        _ensure_s3_bucket(fs, uri)
        with fs.open(_s3_path(uri), "w", encoding="utf-8") as handle:
            handle.write(content)
        return
    path = Path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _workspace_root() -> Path:
    docker_data = Path("/app/data")
    if docker_data.is_dir():
        return Path("/app")
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "backend").exists():
            return parent
    return current.parents[4]


def _s3_er_base_uri() -> str:
    bucket = (os.getenv("AWS_S3_BUCKET") or "yunesa-etl").strip().strip("/")
    prefix = (os.getenv("AWS_S3_PATH") or "etl/data").strip().strip("/")
    if prefix:
        return f"s3://{bucket}/{prefix}/kg/entity_resolution"
    return f"s3://{bucket}/kg/entity_resolution"


def _default_paths() -> dict[str, str | Path]:
    if os.getenv("ETL_STORAGE_TYPE", "local").strip().lower() == "s3":
        base = _s3_er_base_uri()
        return {
            "store": _normalize_target(os.getenv("YUNESA_ALIAS_CURATION_STORE") or f"{base}/alias_curation_store.json"),
            "suggestions": _normalize_target(os.getenv("YUNESA_ALIAS_SUGGESTIONS_PATH") or f"{base}/concept_alias_suggestions.json"),
            "base_aliases": _normalize_target(os.getenv("YUNESA_BASE_CONCEPT_ALIASES_PATH") or f"{base}/concept_aliases.yml"),
            "approved_aliases": _normalize_target(os.getenv("YUNESA_APPROVED_CONCEPT_ALIASES_PATH") or f"{base}/concept_aliases.approved.yml"),
        }

    root = _workspace_root()
    er_dir = root / "data" / "kg" / "entity_resolution"
    suggestion_candidates = [
        _normalize_target(os.getenv("YUNESA_ALIAS_SUGGESTIONS_PATH", "")) if os.getenv("YUNESA_ALIAS_SUGGESTIONS_PATH") else None,
        er_dir / "concept_alias_suggestions.json",
        root / "data" / "kg_pipeline_test" / "kg" / "output" / "concept_alias_suggestions.json",
        root / "notebooks" / "build-graph" / "outputs" / "entity_resolution" / "concept_alias_suggestions.json",
    ]
    suggestion_path = next((path for path in suggestion_candidates if path and _target_exists(path)), suggestion_candidates[1])
    return {
        "store": _normalize_target(os.getenv("YUNESA_ALIAS_CURATION_STORE") or (er_dir / "alias_curation_store.json")),
        "suggestions": _normalize_target(suggestion_path),
        "base_aliases": _normalize_target(os.getenv("YUNESA_BASE_CONCEPT_ALIASES_PATH") or (er_dir / "concept_aliases.yml")),
        "approved_aliases": _normalize_target(os.getenv("YUNESA_APPROVED_CONCEPT_ALIASES_PATH") or (er_dir / "concept_aliases.approved.yml")),
    }


def _stable_id(item: dict[str, Any]) -> str:
    raw = "|".join(
        str(item.get(key, "") or "")
        for key in ("raw_label", "suggested_canonical_label", "suggested_canonical_key", "action")
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _safe_alias_key(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "_", (value or "").strip().lower()).strip("_")
    return text or "alias"


def _unique_strings(values: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


class EntityResolutionCurationStore:
    """File- or S3-backed curation store for KG concept alias suggestions.

    Keeps alias review outside the relational schema while producing a YAML
    artifact consumable by the ingestion pipeline over local storage or MinIO S3.
    """

    def __init__(self, store_path: str | Path | None = None) -> None:
        paths = _default_paths()
        self.paths = paths
        self.store_path: str | Path = _normalize_target(store_path if store_path is not None else paths["store"])

    def _empty_store(self) -> dict[str, Any]:
        return {
            "version": 1,
            "updated_at": _utc_now(),
            "suggestions": {},
        }

    def _load_store(self) -> dict[str, Any]:
        if not _target_exists(self.store_path):
            return self._empty_store()
        try:
            data = json.loads(_read_text(self.store_path))
        except Exception:
            return self._empty_store()
        if not isinstance(data, dict):
            return self._empty_store()
        data.setdefault("version", 1)
        data.setdefault("updated_at", _utc_now())
        data.setdefault("suggestions", {})
        if not isinstance(data["suggestions"], dict):
            data["suggestions"] = {}
        return data

    def _save_store(self, data: dict[str, Any]) -> None:
        data["updated_at"] = _utc_now()
        _write_text(self.store_path, json.dumps(data, ensure_ascii=False, indent=2))

    def _normalize_suggestion(self, item: dict[str, Any], source_path: str | Path) -> dict[str, Any]:
        suggestion = deepcopy(item)
        suggestion_id = str(suggestion.get("id") or _stable_id(suggestion))
        suggestion["id"] = suggestion_id
        suggestion["raw_label"] = str(suggestion.get("raw_label") or "").strip()
        suggestion["suggested_canonical_label"] = str(suggestion.get("suggested_canonical_label") or "").strip()
        suggestion["suggested_canonical_key"] = str(suggestion.get("suggested_canonical_key") or "").strip()
        suggestion["concept_type"] = str(suggestion.get("concept_type") or "ResearchTopic").strip()
        suggestion["action"] = str(suggestion.get("action") or "").strip()
        suggestion["aliases"] = _unique_strings(suggestion.get("aliases") or [])
        suggestion["source_path"] = str(source_path)
        suggestion.setdefault("confidence", 0)
        suggestion.setdefault("review_status", "needs_review")
        suggestion.setdefault("rationale", "")
        return suggestion

    def sync_suggestions(self, source_path: str | Path | None = None) -> dict[str, Any]:
        source = _normalize_target(source_path if source_path is not None else self.paths["suggestions"])
        data = self._load_store()
        imported = 0
        updated = 0

        if not _target_exists(source):
            self._save_store(data)
            return {
                "imported": imported,
                "updated": updated,
                "source_path": str(source),
                "store_path": str(self.store_path),
                "missing_source": True,
            }

        payload = json.loads(_read_text(source))
        suggestions = payload.get("suggestions", []) if isinstance(payload, dict) else []
        if not isinstance(suggestions, list):
            suggestions = []

        store_suggestions = data["suggestions"]
        for raw_item in suggestions:
            if not isinstance(raw_item, dict):
                continue
            item = self._normalize_suggestion(raw_item, source)
            existing = store_suggestions.get(item["id"])
            if existing is None:
                item["created_at"] = _utc_now()
                item["updated_at"] = _utc_now()
                item["decision"] = {
                    "status": "pending",
                    "reviewed_at": "",
                    "reviewer": "",
                }
                store_suggestions[item["id"]] = item
                imported += 1
                continue

            decision = existing.get("decision") or {"status": "pending"}
            existing.update(item)
            existing["decision"] = decision
            existing["updated_at"] = _utc_now()
            updated += 1

        self._save_store(data)
        return {
            "imported": imported,
            "updated": updated,
            "source_path": str(source),
            "store_path": str(self.store_path),
            "missing_source": False,
        }

    def list_suggestions(self, status: str | None = None) -> dict[str, Any]:
        data = self._load_store()
        if not data["suggestions"] and _target_exists(self.paths["suggestions"]):
            self.sync_suggestions()
            data = self._load_store()

        items = list(data["suggestions"].values())
        if status and status != "all":
            items = [
                item
                for item in items
                if (item.get("decision") or {}).get("status", "pending") == status
            ]

        items.sort(
            key=lambda item: (
                (item.get("decision") or {}).get("status", "pending") != "pending",
                -float(item.get("confidence") or 0),
                item.get("raw_label", "").casefold(),
            )
        )

        counts = {"pending": 0, "approved": 0, "rejected": 0}
        for item in data["suggestions"].values():
            item_status = (item.get("decision") or {}).get("status", "pending")
            counts[item_status] = counts.get(item_status, 0) + 1

        return {
            "items": items,
            "counts": counts,
            "total": len(data["suggestions"]),
            "store_path": str(self.store_path),
            "suggestions_path": str(self.paths["suggestions"]),
            "export_path": str(self.paths["approved_aliases"]),
        }

    def approve(
        self,
        suggestion_id: str,
        *,
        canonical_label: str | None = None,
        canonical_key: str | None = None,
        concept_type: str | None = None,
        aliases: list[str] | None = None,
        rationale: str | None = None,
        reviewer: str = "",
    ) -> dict[str, Any]:
        data = self._load_store()
        item = data["suggestions"].get(suggestion_id)
        if item is None:
            raise KeyError(suggestion_id)

        label = (canonical_label or item.get("suggested_canonical_label") or item.get("raw_label") or "").strip()
        key = (canonical_key or item.get("suggested_canonical_key") or _safe_alias_key(label)).strip()
        item_aliases = _unique_strings([item.get("raw_label"), *(item.get("aliases") or []), *(aliases or []), label])
        item["decision"] = {
            "status": "approved",
            "canonical_label": label,
            "canonical_key": key,
            "concept_type": (concept_type or item.get("concept_type") or "ResearchTopic").strip(),
            "aliases": item_aliases,
            "rationale": (rationale if rationale is not None else item.get("rationale", "")),
            "reviewed_at": _utc_now(),
            "reviewer": reviewer,
        }
        item["updated_at"] = _utc_now()
        self._save_store(data)
        return item

    def reject(self, suggestion_id: str, *, reason: str = "", reviewer: str = "") -> dict[str, Any]:
        data = self._load_store()
        item = data["suggestions"].get(suggestion_id)
        if item is None:
            raise KeyError(suggestion_id)
        item["decision"] = {
            "status": "rejected",
            "reason": reason,
            "reviewed_at": _utc_now(),
            "reviewer": reviewer,
        }
        item["updated_at"] = _utc_now()
        self._save_store(data)
        return item

    def _load_base_aliases(self, path: str | Path) -> dict[str, Any]:
        if not _target_exists(path):
            return {"aliases": {}}
        data = yaml.safe_load(_read_text(path)) or {}
        if not isinstance(data, dict):
            return {"aliases": {}}
        aliases = data.get("aliases", data)
        if not isinstance(aliases, dict):
            aliases = {}
        return {"aliases": deepcopy(aliases)}

    def export_aliases(
        self,
        output_path: str | Path | None = None,
        base_path: str | Path | None = None,
    ) -> dict[str, Any]:
        data = self._load_store()
        base_alias_path = _normalize_target(base_path if base_path is not None else self.paths["base_aliases"])
        export_path = _normalize_target(output_path if output_path is not None else self.paths["approved_aliases"])
        payload = self._load_base_aliases(base_alias_path)
        aliases = payload.setdefault("aliases", {})
        approved_count = 0

        for item in data["suggestions"].values():
            decision = item.get("decision") or {}
            if decision.get("status") != "approved":
                continue
            canonical_label = str(decision.get("canonical_label") or "").strip()
            if not canonical_label:
                continue
            canonical_key = _safe_alias_key(str(decision.get("canonical_key") or canonical_label))
            aliases[canonical_key] = {
                "canonical_label": canonical_label,
                "canonical_key": str(decision.get("canonical_key") or canonical_key),
                "concept_type": str(decision.get("concept_type") or "ResearchTopic"),
                "aliases": _unique_strings(decision.get("aliases") or []),
                "source": "ui_approved_alias",
            }
            approved_count += 1

        _write_text(export_path, yaml.safe_dump(payload, allow_unicode=True, sort_keys=False))
        return {
            "approved_count": approved_count,
            "export_path": str(export_path),
            "base_aliases_path": str(base_alias_path),
        }


entity_resolution_curation_store = EntityResolutionCurationStore()
