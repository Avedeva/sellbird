from __future__ import annotations

import json

import httpx
import pytest

from sellbird.local_ai import OllamaService
from sellbird.sales_store import SalesStore
from sellbird.sales_workflows import SalesWorkflows


def company_payload():
    return {"name": "Northstar Systems", "description": "B2B operations software.",
            "industry": "Software", "website": "https://northstar.example",
            "company_size": "12", "target_geography": "US", "business_model": "SaaS",
            "existing_sales_information": "No measured customer outcomes supplied."}


def product_payload(company_id, name, industry, pains):
    return {"company_id": company_id, "name": name, "description": f"{name} description",
            "features": [f"{name} feature"], "benefits": [f"{name} benefit"],
            "target_market": industry, "pricing": "Not supplied",
            "value_proposition": f"{name} value", "competitive_differentiation": "Not supplied",
            "customer_pain_points": pains, "sales_positioning": name,
            "icp_criteria": {}, "scoring_weights": {"industry_fit": .2, "company_size_fit": .1,
                "buying_signals": .2, "pain_point_fit": .2, "product_alignment": .2, "data_completeness": .1}}


@pytest.mark.asyncio
async def test_score_is_deterministic_and_uses_selected_product_context(tmp_path):
    store = SalesStore(tmp_path / "workflows.sqlite3")
    await store.ensure()
    seller = await store.create_company(company_payload())
    product_a = await store.create_product(product_payload(seller["id"], "Appointment Flow", "Dental",
                                                           ["manual appointment scheduling"]))
    product_b = await store.create_product(product_payload(seller["id"], "Quote Follow-up", "Roofing",
                                                           ["slow quote follow up"]))
    await store.save_icp(product_a["id"], {"target_industries": ["Dental"], "company_size": "5-100"})
    await store.save_icp(product_b["id"], {"target_industries": ["Roofing"], "company_size": "5-100"})
    prospect = await store.create_prospect({
        "company_id": seller["id"], "company_name": "Example Dental", "industry": "Dental",
        "company_description": "Manual appointment scheduling for a local dental practice.",
        "employee_count": 12, "field_provenance": {"industry": "user_provided"},
    })
    workflows = SalesWorkflows(store, None)
    appointment_score = await workflows.score(product_a["id"], prospect["id"])
    roofing_score = await workflows.score(product_b["id"], prospect["id"])
    assert appointment_score["factors"]["industry_fit"] > roofing_score["factors"]["industry_fit"]
    assert appointment_score == await workflows.score(product_a["id"], prospect["id"])
    assert {row["product_id"] for row in await store.artifacts(prospect_id=prospect["id"], workflow="score")} == {
        product_a["id"], product_b["id"]}


@pytest.mark.asyncio
async def test_product_workflow_context_and_evidence_validation(tmp_path):
    store = SalesStore(tmp_path / "workflows.sqlite3")
    await store.ensure()
    seller = await store.create_company(company_payload())
    product_a = await store.create_product(product_payload(seller["id"], "Appointment Flow", "Dental", ["manual scheduling"]))
    product_b = await store.create_product(product_payload(seller["id"], "Quote Follow-up", "Roofing", ["slow quotes"]))
    prospect = await store.create_prospect({"company_id": seller["id"], "company_name": "Example Dental",
                                            "industry": "Dental", "company_description": "Appointment requests arrive by phone.",
                                            "field_provenance": {"industry": "user_provided"}})
    source_text = "The synthetic cached note says appointment requests arrive by phone and some calls go unanswered."
    source = await store.save_research_source(prospect["id"], "https://example.test/about", "Cached example", source_text)
    outputs = [
        {"positioning": "B2B systems for the recorded target market.", "target_customers": ["Businesses"],
         "customer_problems": ["Recorded manual work"], "value_proposition": "Not provided", "competitive_advantages": [], "missing_information": []},
        {"target_industries": ["Dental"], "company_size": "5-100", "revenue_range": "", "geographic_markets": ["US"],
         "buyer_personas": ["Practice manager"], "decision_maker_roles": ["Owner"], "technology_stack": [],
         "business_challenges": ["Manual booking"], "purchase_motivations": ["Efficiency"],
         "exclusion_criteria": [], "qualification_criteria": ["Verify need"]},
        {"overview": "Cached synthetic example text.", "findings": [{"finding": "Appointment requests arrive by phone.",
          "source_url": source["url"], "evidence_excerpt": "appointment requests arrive by phone", "evidence_type": "extracted", "confidence": .8}],
         "hypotheses": ["Calls may be missed."], "insufficient_evidence": False},
        {"insufficient_evidence": False, "signals": [{"category": "operational_challenge",
          "supporting_evidence": "some calls go unanswered", "source_url": source["url"], "confidence": .8,
          "product_relevance": "Could be relevant to appointment handling.", "business_implication": "May leave requests without follow-up.",
          "potential_opportunity": "Ask whether they need a booking workflow."}]},
        {"problem_hypothesis": "The recorded phone-based request process may require manual follow-up.",
         "evidence": ["prospect:company_description"], "why_it_matters": "Requests may need attention.",
         "product_fit": "The selected product covers appointment handling.", "assumptions_to_verify": ["Unanswered calls are frequent."]},
        {"subject": "appointment requests", "body": "Hi, I saw your note about appointment requests. Would it help to compare ways to organize them?",
         "evidence_used": [source["url"]], "assumptions": ["The note is accurate."]},
        {"classification": "needs_more_information", "confidence": .91,
         "supporting_text": "Could you send more details?", "intent": "Asks for information.",
         "recommended_next_action": "Send concise product details.", "suggested_response": "Certainly; what would be most useful?"},
    ]
    prompts = []

    def handler(request):
        payload = json.loads(request.content)
        prompts.append(payload["messages"][1]["content"])
        return httpx.Response(200, json={"message": {"content": json.dumps(outputs.pop(0))}})

    ai = OllamaService(store, transport_factory=lambda: httpx.MockTransport(handler))
    workflows = SalesWorkflows(store, ai)
    assert (await workflows.generate_profile(seller["id"]))["positioning"]
    assert (await workflows.generate_icp(product_a["id"]))["target_industries"] == ["Dental"]
    summary = await workflows.summarize_research(product_a["id"], prospect["id"])
    assert summary["findings"][0]["evidence_excerpt"] in source_text
    signals = await workflows.classify_signals(product_a["id"], prospect["id"])
    assert signals["signals"][0]["source_url"] == source["url"]
    problem = await workflows.generate_problem(product_a["id"], prospect["id"])
    assert problem["evidence"] == ["prospect:company_description"]
    problem_prompt = prompts[4]
    assert '"allowed_evidence_references"' in problem_prompt
    assert "prospect:company_description" in problem_prompt
    assert source["url"] in problem_prompt
    score = await workflows.score(product_a["id"], prospect["id"])
    assert 0 <= score["score"] <= 100
    email = await workflows.generate_email(product_a["id"], prospect["id"], "concise")
    assert email["evidence_used"] == [source["url"]]
    reply = await workflows.classify_reply(product_a["id"], "Could you send more details?", True)
    assert reply["sample"] is True
    assert all("Appointment Flow" in prompt or "appointment" in prompt.lower() for prompt in prompts[1:])
    assert not any("Quote Follow-up" in prompt for prompt in prompts)
    assert outputs == []


@pytest.mark.asyncio
async def test_buying_signal_classifier_discards_non_ok_sources(tmp_path):
    store = SalesStore(tmp_path / "demo-signal.sqlite3")
    await store.ensure()
    seller = await store.create_company(company_payload())
    product = await store.create_product(product_payload(seller["id"], "Appointment Flow", "Dental",
                                                          ["manual appointment scheduling"]))
    prospect = await store.create_prospect({"company_id": seller["id"], "company_name": "Example Dental"})
    source_text = "Sample practice states that appointment requests are handled by phone."
    source = await store.save_research_source(
        prospect["id"], "demo://acceptance/source", "Synthetic demonstration data", source_text, status="demo"
    )

    def handler(request):
        prompt = json.loads(request.content)["messages"][1]["content"]
        assert '"status": "demo"' in prompt
        result = {"insufficient_evidence": False, "signals": [{
            "category": "product_launch", "supporting_evidence": source_text,
            "source_url": source["url"], "confidence": .9,
            "product_relevance": "The sample is related to appointments.",
            "business_implication": "A demo record is not a public buying signal.",
            "potential_opportunity": "Ask whether appointment management is relevant.",
        }]}
        return httpx.Response(200, json={"message": {"content": json.dumps(result)}})

    ai = OllamaService(store, transport_factory=lambda: httpx.MockTransport(handler))
    workflows = SalesWorkflows(store, ai)
    result = await workflows.classify_signals(product["id"], prospect["id"])

    assert result == {"insufficient_evidence": True, "signals": []}
    assert await store.signals(product["id"], prospect["id"]) == []

