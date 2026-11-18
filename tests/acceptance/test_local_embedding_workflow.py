"""Opt-in local-only embedding acceptance; requires cached model weights."""

from __future__ import annotations

import os

import pytest

from sellbird.sales_routes import index_research
from sellbird.sales_store import SalesStore
from sellbird.workspace_home import Home, use_home


pytestmark = pytest.mark.skipif(
    os.environ.get("SELLBIRD_RUN_EMBEDDING_ACCEPTANCE") != "1",
    reason="Set SELLBIRD_RUN_EMBEDDING_ACCEPTANCE=1 with a cached local model path",
)


@pytest.mark.asyncio
async def test_cached_sentence_transformer_indexes_research_without_network(tmp_path, monkeypatch):
    model_path = os.environ.get("SELLBIRD_EMBEDDING_MODEL_PATH", "").strip()
    if not model_path:
        pytest.fail("Set SELLBIRD_EMBEDDING_MODEL_PATH to the cached model directory")
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")

    home = Home.for_root(tmp_path)
    store = SalesStore(home.db_path)
    await store.ensure()
    company = await store.create_company({
        "name": "Synthetic embedding acceptance",
        "description": "", "industry": "", "website": "", "company_size": "",
        "target_geography": "", "business_model": "", "existing_sales_information": "",
    })
    prospect = await store.create_prospect({
        "company_id": company["id"], "company_name": "Sample Clinic",
    })
    await store.save_research_source(
        prospect["id"], "demo://embedding/source", "Synthetic cached note",
        "The sample clinic handles appointment requests by phone and follows up manually.", status="demo",
    )

    with use_home(home):
        result = await index_research(prospect["id"], None)
        indexed = await store.research_index(prospect["id"])

    assert result["indexed"] == 1
    assert result["network_downloads"] is False
    assert len(indexed) == 1
    assert indexed[0]["model_path"] == model_path
    assert len(indexed[0]["vector"]) == 384
    norm = sum(value * value for value in indexed[0]["vector"]) ** 0.5
    assert abs(norm - 1.0) < 1e-5
