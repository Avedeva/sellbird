from __future__ import annotations

import pytest
from fastapi import HTTPException
from sellbird import sales_routes
from sellbird.local_ai import LocalAIError
from sellbird.sales_schemas import ReplyInput

from sellbird.sales_routes import _retry_ai_task, _run_ai
from sellbird.sales_store import SalesStore


@pytest.mark.asyncio
async def test_local_ai_failure_is_persisted_and_can_be_retried(tmp_path):
    store = SalesStore(tmp_path / "queue.sqlite3")
    await store.ensure()

    # `_run_ai` queues only local inference errors; simulate the gateway's
    # error type so this verifies the same API failure path.
    async def ollama_unavailable():
        raise LocalAIError("Ollama is not reachable; no cloud fallback was attempted")

    with pytest.raises(HTTPException) as caught:
        await _run_ai(store, "business_profile", {"company_id": "company-1"}, ollama_unavailable)
    assert caught.value.status_code == 503
    task_id = caught.value.detail["task_id"]
    queued = await store.get_task(task_id)
    assert queued["status"] == "queued"
    assert queued["result"] == {"company_id": "company-1"}

    class AvailableWorkflows:
        async def generate_profile(self, company_id):
            assert company_id == "company-1"
            return {"positioning": "Locally generated after retry"}

    result = await _retry_ai_task(store, AvailableWorkflows(), queued)
    assert result["status"] == "completed"
    saved = await store.get_task(task_id)
    assert saved["status"] == "completed"
    assert saved["result"] == result["result"]


@pytest.mark.asyncio
async def test_reply_route_maps_reply_text_to_workflow_reply_argument(monkeypatch):
    expected = {"product_id": "product-1", "reply": "Please remove me.",
                "sample": True, "prospect_id": "prospect-1"}

    class Workflows:
        async def classify_reply(self, *, product_id, reply, sample, prospect_id):
            assert {"product_id": product_id, "reply": reply,
                    "sample": sample, "prospect_id": prospect_id} == expected
            return {"classification": "unsubscribe", "sample": sample}

    async def ready(_request):
        return object(), Workflows(), object()

    monkeypatch.setattr(sales_routes, "_ready", ready)
    payload = ReplyInput(product_id="product-1", reply_text="Please remove me.",
                         sample=True, prospect_id="prospect-1")
    result = await sales_routes.classify_reply(payload, object())

    assert result == {"classification": "unsubscribe", "sample": True}
