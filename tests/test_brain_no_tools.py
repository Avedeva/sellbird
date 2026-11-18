"""The active Brain sends plain prompts only to its local Ollama service."""

import json

import httpx
import pytest
import pytest_asyncio

from sellbird.brain import Brain
from sellbird.local_ai import OllamaService
from sellbird.state import StateManager


@pytest_asyncio.fixture
async def brain(tmp_path):
    state = StateManager(str(tmp_path / "state.sqlite3"))
    await state.init_db()
    value = Brain(state)
    await value.store.ensure()
    return value


@pytest.mark.asyncio
async def test_brain_sends_plain_prompt_only_to_local_ollama(brain, monkeypatch):
    seen = []

    def handler(request):
        seen.append(request)
        assert request.url.host == "127.0.0.1"
        return httpx.Response(200, json={"message": {"content": "ok"}})

    brain.ai = OllamaService(brain.store, transport_factory=lambda: httpx.MockTransport(handler))

    async def forbidden_subprocess(*args, **kwargs):
        raise AssertionError("Brain must not launch a cloud CLI")

    monkeypatch.setattr("sellbird.brain.asyncio.create_subprocess_exec", forbidden_subprocess)
    prompt = "Private prospect reply: our budget is $40k"
    assert await brain.think(prompt) == "ok"

    assert len(seen) == 1
    payload = json.loads(seen[0].content)
    assert payload["messages"] == [{"role": "user", "content": prompt}]
    assert "tools" not in payload
    logs = await brain.store.inference_logs()
    assert logs[0]["status"] == "ok"
    assert prompt not in json.dumps(logs)


@pytest.mark.asyncio
async def test_brain_pauses_when_local_ollama_is_unavailable(brain):
    brain.ai = OllamaService(brain.store, transport_factory=lambda: httpx.MockTransport(
        lambda request: httpx.Response(503, json={"error": "offline"})))
    assert await brain.preflight()
    assert await brain.think("private data") == ""
    status = json.loads(await brain.state.get_setting("brain_status"))
    assert status["provider"] == "ollama"
    assert status["status"] == "paused"
