from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path


class ReadinessError(RuntimeError):
    pass


def request(
    url: str,
    *,
    method: str = "GET",
    payload: dict | None = None,
    form: dict | None = None,
    token: str = "",
    expected: tuple[int, ...] = (200,),
):
    headers = {"Accept": "application/json"}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, data=data, headers=headers, method=method), timeout=90
        ) as response:
            status, body = response.status, response.read()
    except urllib.error.HTTPError as error:
        status, body = error.code, b""
    except (urllib.error.URLError, TimeoutError) as error:
        raise ReadinessError("HTTP transport unavailable") from error
    if status not in expected:
        raise ReadinessError(f"Unexpected HTTP status {status}")
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return body


async def storage_probe() -> dict:
    import asyncpg
    import redis.asyncio as redis
    from neo4j import GraphDatabase
    from yunesa.storage.minio.client import MinIOClient

    database = await asyncpg.connect(
        os.environ["POSTGRES_URL"].replace("postgresql+asyncpg://", "postgresql://"), timeout=15
    )
    try:
        if await database.fetchval("SELECT 1") != 1:
            raise ReadinessError("PostgreSQL round trip failed")
        await database.fetchval("SELECT count(*) FROM users")
    finally:
        await database.close()
    queue = redis.from_url(os.environ["REDIS_URL"])
    key = f"yunesa:readiness:{uuid.uuid4().hex}"
    try:
        await queue.set(key, "ready", ex=60)
        if await queue.get(key) != b"ready":
            raise ReadinessError("Redis round trip failed")
        await queue.delete(key)
    finally:
        await queue.aclose()
    username = os.environ.get("NEO4J_USERNAME", "")
    auth = (username, os.environ.get("NEO4J_PASSWORD", "")) if username else None
    with GraphDatabase.driver(os.environ["NEO4J_URI"], auth=auth, connection_timeout=15) as driver:
        with driver.session(database=os.environ.get("NEO4J_DATABASE") or None) as session:
            row = session.run("RETURN 1 AS value").single()
            if row is None or row["value"] != 1:
                raise ReadinessError("Memgraph round trip failed")
    vector_request = urllib.request.Request(
        os.environ["QDRANT_URI"].rstrip("/") + "/collections", headers={"api-key": os.environ["QDRANT_API_KEY"]}
    )
    with urllib.request.urlopen(vector_request, timeout=15) as response:
        vector = json.load(response)
    if vector.get("status") != "ok":
        raise ReadinessError("Qdrant collection listing failed")
    storage = MinIOClient()
    object_name = f"deployment-readiness/{uuid.uuid4().hex}.txt"
    content = b"Yunesa object storage readiness\n"
    uploaded = storage.upload_file("public", object_name, content, "text/plain")
    try:
        if storage.download_file("public", object_name) != content:
            raise ReadinessError("MinIO object round trip failed")
        if request(uploaded.url) != content:
            raise ReadinessError("Public object response differs from uploaded bytes")
        public_base = os.environ["MINIO_PUBLIC_BASE_URL"].rstrip("/")
        request(public_base + "/knowledgebases/" + object_name, expected=(404,))
        request(public_base + "/public/", expected=(404,))
    finally:
        if not storage.delete_file("public", object_name):
            raise ReadinessError("Readiness object could not be removed")
    if storage.file_exists("public", object_name):
        raise ReadinessError("Readiness object remains after delete")
    return {
        "postgres": "passed",
        "redis_write_read": "passed",
        "memgraph_query": "passed",
        "qdrant": "passed",
        "qdrant_collections": len(vector["result"]["collections"]),
        "minio_upload_download_delete": "passed",
        "public_object_bytes": "passed",
        "private_bucket_proxy_denied": "passed",
        "public_bucket_listing_denied": "passed",
    }


async def provider_probe() -> dict:
    from yunesa import config
    from yunesa.models.chat import test_chat_model_status
    from yunesa.models.embed import test_embedding_model_status

    provider, model = config.default_model.split("/", 1)
    if provider != "gemini" or not config.embed_model.startswith("siliconflow/"):
        raise ReadinessError("Configured provider roles do not match Gemini/SiliconFlow")
    chat = await test_chat_model_status(provider, model)
    embed = await test_embedding_model_status(config.embed_model)
    if chat.get("status") != "available" or embed.get("status") != "available":
        raise ReadinessError("Configured provider invocation failed; inspect restricted application logs")
    return {
        "chat_provider": provider,
        "chat_model": model,
        "chat": "passed",
        "embedding_model": config.embed_model,
        "embedding": "passed",
    }


def http_probe(base_url: str, credentials: Path, initialize: bool, chat: bool) -> dict:
    base = base_url.rstrip("/")
    deadline = time.monotonic() + 240
    while True:
        try:
            health = request(base + "/api/system/health")
            if not isinstance(health, dict) or health.get("status") != "ok":
                raise ReadinessError("API liveness response invalid")
            break
        except ReadinessError:
            if time.monotonic() >= deadline:
                raise ReadinessError("API startup deadline exceeded")
            time.sleep(5)
    page = request(base + "/")
    if not isinstance(page, bytes) or b"<html" not in page.lower():
        raise ReadinessError("Frontend HTML unavailable through proxy")
    login = json.loads(credentials.read_text(encoding="utf-8"))
    first = request(base + "/api/auth/check-first-run")
    if first.get("first_run"):
        if not initialize:
            raise ReadinessError("Application admin must be initialized before authenticated readiness")
        request(
            base + "/api/auth/initialize",
            method="POST",
            payload={"user_id": login["username"], "password": login["password"]},
        )
    token_response = request(base + "/api/auth/token", method="POST", form=login)
    token = token_response.get("access_token", "")
    if not token:
        raise ReadinessError("Login returned no access token")
    user = request(base + "/api/auth/me", token=token)
    if user.get("user_id") != login["username"]:
        raise ReadinessError("Authenticated profile does not match readiness account")
    request(base + "/api/auth/me", expected=(401,))
    agents = request(base + "/api/chat/default_agent", token=token)
    agent = agents.get("default_agent_id", "")
    if not agent:
        raise ReadinessError("No application agent available")
    thread = request(
        base + "/api/chat/thread",
        method="POST",
        token=token,
        payload={"agent_id": agent, "title": "Deployment readiness", "metadata": {"purpose": "deployment-readiness"}},
    )
    thread_id = thread.get("id", "")
    if not thread_id:
        raise ReadinessError("Conversation persistence returned no ID")
    chat_result = {}
    try:
        threads = request(base + "/api/chat/threads", token=token)
        if not any(item.get("id") == thread_id for item in threads):
            raise ReadinessError("Persisted conversation could not be read")
        request(base + "/api/chat/threads", expected=(401,))
        if chat:
            configs = request(base + f"/api/chat/agent/{agent}/configs", token=token).get("configs", [])
            if not configs:
                raise ReadinessError("Application agent configuration unavailable")
            configuration = next((item for item in configs if item.get("is_default")), configs[0])
            created = request(
                base + "/api/chat/runs",
                method="POST",
                token=token,
                payload={
                    "query": "Balas satu kalimat pendek dalam bahasa Indonesia untuk memastikan chat aktif.",
                    "agent_config_id": configuration["id"],
                    "thread_id": thread_id,
                    "meta": {"request_id": str(uuid.uuid4()), "purpose": "deployment-readiness"},
                },
            )
            run_id = created.get("run_id")
            if not run_id:
                raise ReadinessError("Async chat did not return a run ID")
            deadline = time.monotonic() + 180
            while True:
                run = request(base + f"/api/chat/runs/{run_id}", token=token).get("run", {})
                if run.get("status") == "completed":
                    break
                if run.get("status") in {"failed", "cancelled", "interrupted"}:
                    raise ReadinessError("Async chat finished without a completed response")
                if time.monotonic() >= deadline:
                    request(base + f"/api/chat/runs/{run_id}/cancel", method="POST", token=token)
                    raise ReadinessError("Async chat completion deadline exceeded")
                time.sleep(3)
            history = request(base + f"/api/chat/thread/{thread_id}/history", token=token).get("history", [])
            if not any(
                item.get("type") == "ai" and item.get("content") and not item.get("error_type") for item in history
            ):
                raise ReadinessError("Completed chat has no persisted assistant response")
            chat_result = {"async_chat": "passed", "run_id": run_id, "assistant_response_persisted": "passed"}
    finally:
        request(base + f"/api/chat/thread/{thread_id}", method="DELETE", token=token)
    threads = request(base + "/api/chat/threads", token=token)
    if any(item.get("id") == thread_id for item in threads):
        raise ReadinessError("Deleted readiness conversation still active")
    return {
        "frontend": "passed",
        "login": "passed",
        "authorization": "passed",
        "conversation_write_read_delete": "passed",
        "version": health.get("version"),
        **chat_result,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inside-storage", action="store_true")
    parser.add_argument("--inside-provider", action="store_true")
    parser.add_argument("--initialize-admin", action="store_true")
    parser.add_argument("--base-url", default="http://127.0.0.1:8088")
    parser.add_argument("--credentials", type=Path)
    parser.add_argument("--initialize", action="store_true")
    parser.add_argument("--chat", action="store_true")
    args = parser.parse_args()
    try:
        if args.initialize_admin:
            credentials = json.load(sys.stdin)
            base = "http://127.0.0.1:5050/api/auth"
            first = request(base + "/check-first-run")
            if first.get("first_run"):
                request(
                    base + "/initialize",
                    method="POST",
                    payload={"user_id": credentials["username"], "password": credentials["password"]},
                )
            logged_in = request(base + "/token", method="POST", form=credentials)
            request(base + "/me", token=logged_in["access_token"])
            result = {"admin_initialized": "passed"}
        elif args.inside_storage:
            result = asyncio.run(storage_probe())
        elif args.inside_provider:
            result = asyncio.run(provider_probe())
        elif args.credentials:
            result = http_probe(args.base_url, args.credentials, args.initialize, args.chat)
        else:
            parser.error("--credentials is required for the HTTP/auth probe")
        print(json.dumps(result, sort_keys=True))
        return 0
    except (TimeoutError, ReadinessError, OSError, ValueError, urllib.error.URLError) as error:
        print(f"Readiness failed ({type(error).__name__}); raw dependency output suppressed", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
