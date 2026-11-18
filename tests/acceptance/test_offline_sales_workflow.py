"""Real local-model acceptance test; mocked inference is not success evidence."""

from __future__ import annotations

import ipaddress
import os
from urllib.parse import urlsplit

import httpx
import pytest

from sellbird.local_ai import OllamaService
from sellbird.sales_store import SalesStore
from sellbird.sales_workflows import SalesWorkflows


pytestmark = pytest.mark.skipif(
    os.environ.get("SELLBIRD_RUN_LOCAL_ACCEPTANCE") != "1",
    reason="Set SELLBIRD_RUN_LOCAL_ACCEPTANCE=1 to run against a real installed local Ollama model",
)


def _is_private_host(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address.is_private or address.is_loopback or address.is_link_local


@pytest.mark.asyncio
async def test_complete_offline_product_sales_workflow(tmp_path, monkeypatch):
    # Reject any application/model HTTP request that leaves loopback or a
    # private self-hosted endpoint, even if configuration changes mid-test.
    real_send = httpx.AsyncClient.send
    outbound_attempts = []

    async def local_only_send(client, request, *args, **kwargs):
        if not _is_private_host(request.url.host):
            outbound_attempts.append(str(request.url))
            raise AssertionError(f"Offline acceptance blocked an external request to {request.url.host}")
        return await real_send(client, request, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "send", local_only_send)
    monkeypatch.setenv("SELLBIRD_OFFLINE", "1")
    store = SalesStore(tmp_path / "acceptance.sqlite3")
    await store.ensure()
    ai = OllamaService(store)
    health = await ai.health()
    if not health["model_available"]:
        pytest.fail("Real local integration was requested, but Ollama and the configured model are unavailable")

    company = await store.create_company({
        "name": "Offline Acceptance Sample", "description": "Synthetic local acceptance seller.",
        "industry": "Business software", "website": "", "company_size": "1-10",
        "target_geography": "US", "business_model": "B2B SaaS",
        "existing_sales_information": "No measured customer results are supplied.",
    })
    products = []
    for name, market, pain in (("Appointment Flow", "Dental practices", "manual appointment requests"),
                               ("Quote Follow-up", "Roofing companies", "unanswered quote requests")):
        products.append(await store.create_product({
            "company_id": company["id"], "name": name, "description": f"Sample context for {name}.",
            "features": ["request management"], "benefits": ["clearer follow-up"],
            "target_market": market, "pricing": "Not supplied", "value_proposition": "Organize requests",
            "competitive_differentiation": "Not supplied", "customer_pain_points": [pain],
            "sales_positioning": name, "icp_criteria": {},
            "scoring_weights": {"industry_fit": .2, "company_size_fit": .1, "buying_signals": .2,
                                "pain_point_fit": .2, "product_alignment": .2, "data_completeness": .1},
        }))

    workflows = SalesWorkflows(store, ai)
    await workflows.generate_profile(company["id"])
    for product in products:
        await workflows.generate_icp(product["id"])

    prospect = await store.create_prospect({
        "company_id": company["id"], "company_name": "Example Dental (synthetic)",
        "website": "", "industry": "Dental", "location": "US", "employee_count": 18,
        "company_description": "Synthetic sample practice record for the offline acceptance workflow.",
        "contact_name": "Sample Practice Manager", "job_title": "Practice Manager",
        "business_email": "manager@example.test", "source_url": "demo://acceptance/prospect",
        "field_provenance": {"all_fields": "demonstration_sample"},
    })
    await store.save_research_source(
        prospect["id"], "demo://acceptance/cached-research", "Synthetic cached source",
        "Synthetic demonstration note: the sample practice says appointment requests are handled by phone and "
        "staff may not return every call the same day. This is not verified public intelligence.", status="demo",
    )

    research = await workflows.summarize_research(products[0]["id"], prospect["id"])
    signals = await workflows.classify_signals(products[0]["id"], prospect["id"])
    problem = await workflows.generate_problem(products[0]["id"], prospect["id"])
    score = await workflows.score(products[0]["id"], prospect["id"])
    email = await workflows.generate_email(products[0]["id"], prospect["id"], "concise")
    reply = await workflows.classify_reply(products[0]["id"],
        "Could you send me a little more information?", sample=True)

    assert research["findings"] or research["insufficient_evidence"]
    # The fixture source is explicitly synthetic (status=demo), so it must not
    # be promoted into a real buying signal even if the model suggests one.
    assert signals == {"insufficient_evidence": True, "signals": []}
    assert problem["problem_hypothesis"]
    assert 0 <= score["score"] <= 100
    assert email["subject"] and email["body"]
    assert reply["sample"] is True
    logs = await store.inference_logs(limit=100)
    assert len([row for row in logs if row["status"] == "ok"]) >= 7
    assert all(_is_private_host(urlsplit(row["endpoint"]).hostname or "") for row in logs)
    assert outbound_attempts == []

