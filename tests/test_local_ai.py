from __future__ import annotations

import json

import httpx
import pytest
import pytest_asyncio
from pydantic import BaseModel

from sellbird.local_ai import LocalAIError, OllamaService
from sellbird.sales_store import SalesStore


class Result(BaseModel):
    answer: str
    count: int


@pytest_asyncio.fixture
async def store(tmp_path):
    db = SalesStore(tmp_path / "logs.sqlite3")
    await db.ensure()
    return db


@pytest.mark.asyncio
async def test_structured_local_generation_and_content_free_inference_log(store):
    seen = []

    def handler(request):
        seen.append(request)
        assert request.url.host == "127.0.0.1"
        payload = json.loads(request.content)
        assert payload["model"] == "qwen3:4b"
        assert "format" in payload
        return httpx.Response(200, json={"message": {"content": '{"answer":"ok","count":2}'}})

    ai = OllamaService(store, transport_factory=lambda: httpx.MockTransport(handler))
    result = await ai.generate_json("test", "private prompt text", Result)
    assert result == Result(answer="ok", count=2)
    assert len(seen) == 1
    logs = await store.inference_logs()
    assert logs[0]["status"] == "ok"
    assert logs[0]["endpoint"] == "http://127.0.0.1:11434"
    assert "private prompt text" not in json.dumps(logs)


@pytest.mark.asyncio
@pytest.mark.parametrize("content", ["not json", '{"answer":"ok","count":"wrong"}'])
async def test_invalid_json_is_reported_and_logged(store, content):
    ai = OllamaService(store, transport_factory=lambda: httpx.MockTransport(
        lambda request: httpx.Response(200, json={"message": {"content": content}})))
    with pytest.raises(LocalAIError, match="malformed or schema-invalid"):
        await ai.generate_json("bad_json", "prompt", Result)
    assert (await store.inference_logs())[0]["status"] == "error"


@pytest.mark.asyncio
async def test_missing_model_and_timeout_have_clear_errors(store):
    missing = OllamaService(store, transport_factory=lambda: httpx.MockTransport(
        lambda request: httpx.Response(404, json={"error": "model not found"})))
    with pytest.raises(LocalAIError, match="unavailable"):
        await missing.generate_text("email", "prompt")

    def timeout(request):
        raise httpx.ReadTimeout("slow local model", request=request)

    slow = OllamaService(store, timeout=0.01, transport_factory=lambda: httpx.MockTransport(timeout))
    with pytest.raises(LocalAIError, match="timed out"):
        await slow.generate_json("timeout", "prompt", Result)
    logs = await store.inference_logs()
    assert {row["workflow"] for row in logs} == {"email", "timeout"}


@pytest.mark.asyncio
async def test_transient_local_server_error_retries_once_and_reports_daemon_detail(store):
    requests = 0

    def handler(request):
        nonlocal requests
        requests += 1
        if requests == 1:
            return httpx.Response(500, json={"error": "model runner is starting"})
        return httpx.Response(200, json={"message": {"content": '{"answer":"ready","count":1}'}})

    ai = OllamaService(store, transport_factory=lambda: httpx.MockTransport(handler))
    result = await ai.generate_json("profile", "prompt", Result)
    assert result == Result(answer="ready", count=1)
    assert requests == 2
    assert (await store.inference_logs())[0]["status"] == "ok"


@pytest.mark.asyncio
async def test_permanent_local_server_error_includes_bounded_daemon_detail(store):
    detail = "model requires more memory " + ("x" * 400)
    ai = OllamaService(store, transport_factory=lambda: httpx.MockTransport(
        lambda request: httpx.Response(500, json={"error": detail})))
    with pytest.raises(LocalAIError, match="HTTP 500: model requires more memory") as caught:
        await ai.generate_text("profile", "prompt")
    assert len(str(caught.value)) < 300
    assert (await store.inference_logs())[0]["status"] == "error"


def test_cloud_ollama_endpoint_is_rejected():
    with pytest.raises(ValueError, match="loopback or a private self-hosted"):
        OllamaService(SalesStore("unused.sqlite3"), endpoint="https://api.example.com")


@pytest.mark.asyncio
async def test_transient_local_connection_failure_retries_once_then_fails_closed(store):
    requests = 0

    def handler(request):
        nonlocal requests
        requests += 1
        raise httpx.ConnectError("connection refused", request=request)

    ai = OllamaService(store, transport_factory=lambda: httpx.MockTransport(handler))
    with pytest.raises(LocalAIError, match="no cloud fallback"):
        await ai.generate_text("profile", "prompt")
    assert requests == 2
    assert (await store.inference_logs())[0]["status"] == "error"

