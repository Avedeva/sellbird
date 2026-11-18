"""Idempotently seed clearly labelled, synthetic local-sales demonstration data."""

from __future__ import annotations

import asyncio
import json

from sellbird.sales_store import SalesStore
from sellbird.workspace_home import current_home


async def initialize() -> dict:
    store = SalesStore(current_home().db_path)
    await store.ensure()
    for row in await store.companies():
        if row.get("website") == "demo://local/seller/sellbird-demo":
            return {"status": "already_initialized", "company_id": row["id"]}

    company = await store.create_company({
        "name": "SampleWorks Demo (synthetic)",
        "description": "Demonstration seller used to show multi-product sales workflows. All example firms and events are fictional.",
        "industry": "Sales technology", "website": "demo://local/seller/sellbird-demo",
        "company_size": "1-10 (sample)", "target_geography": "United States (sample)",
        "business_model": "B2B SaaS (sample)",
        "existing_sales_information": "Synthetic demo business. No customer claims or measured outcomes are supplied.",
    })
    bookings = await store.create_product({
        "company_id": company["id"], "name": "Appointment Flow (sample)",
        "description": "Sample scheduling tool context for local service businesses.",
        "features": ["Online scheduling", "Appointment reminders"],
        "benefits": ["Fewer missed appointment requests", "Clearer booking handoff"],
        "target_market": "Sample local roofing, HVAC and dental practices",
        "pricing": "Not provided in this sample", "value_proposition": "Make appointment requests easier to manage",
        "competitive_differentiation": "Not provided in this sample",
        "customer_pain_points": ["Missed booking requests", "Manual appointment coordination"],
        "sales_positioning": "A sample workflow assistant for appointment handling",
        "icp_criteria": {"target_industries": ["Roofing", "HVAC", "Dental"], "company_size": "5-100 employees"},
        "scoring_weights": {"industry_fit": .2, "company_size_fit": .15, "buying_signals": .2,
                            "pain_point_fit": .2, "product_alignment": .15, "data_completeness": .1},
    })
    followup = await store.create_product({
        "company_id": company["id"], "name": "Lead Follow-up Desk (sample)",
        "description": "Separate sample product context for responding to new service inquiries.",
        "features": ["Inquiry queue", "Follow-up reminders"],
        "benefits": ["More consistent lead follow-up", "Clearer inquiry ownership"],
        "target_market": "Sample service companies managing inbound quote requests",
        "pricing": "Not provided in this sample", "value_proposition": "Organize follow-up for incoming inquiries",
        "competitive_differentiation": "Not provided in this sample",
        "customer_pain_points": ["Slow inquiry follow-up", "Unassigned quote requests"],
        "sales_positioning": "A sample assistant for routing and tracking inquiries",
        "icp_criteria": {"target_industries": ["Home services", "Professional services"], "company_size": "10-250 employees"},
        "scoring_weights": {"industry_fit": .2, "company_size_fit": .15, "buying_signals": .25,
                            "pain_point_fit": .15, "product_alignment": .15, "data_completeness": .1},
    })
    await store.save_icp(bookings["id"], {
        "target_industries": ["Roofing", "HVAC", "Dental"], "company_size": "5-100 employees",
        "revenue_range": "Not provided", "geographic_markets": ["United States (sample)"],
        "buyer_personas": ["Owner/operator (sample)"], "decision_maker_roles": ["Owner", "Practice manager"],
        "technology_stack": [], "business_challenges": ["Missed booking requests (sample hypothesis)"],
        "purchase_motivations": ["Reduce manual appointment coordination"],
        "exclusion_criteria": ["No evidence of appointment handling needs"],
        "qualification_criteria": ["Sample criteria; regenerate with local Ollama for an actual seller context"],
        "demonstration_sample": True,
    })
    await store.save_icp(followup["id"], {
        "target_industries": ["Home services", "Professional services"], "company_size": "10-250 employees",
        "revenue_range": "Not provided", "geographic_markets": ["United States (sample)"],
        "buyer_personas": ["Operations lead (sample)"], "decision_maker_roles": ["Owner", "Operations manager"],
        "technology_stack": [], "business_challenges": ["Slow inquiry follow-up (sample hypothesis)"],
        "purchase_motivations": ["More consistent inquiry ownership"],
        "exclusion_criteria": ["No evidence of inbound quote activity"],
        "qualification_criteria": ["Sample criteria; regenerate with local Ollama for an actual seller context"],
        "demonstration_sample": True,
    })

    prospects = []
    sample_rows = [
        {"company_name": "Northwind Roofing (sample)", "website": "https://northwind-roofing.example",
         "industry": "Roofing", "location": "Oregon, US (sample)", "employee_count": 24,
         "contact_name": "Jordan Lee (sample)", "job_title": "Owner (sample)", "business_email": "jordan@northwind-roofing.example",
         "company_description": "Synthetic sample roofing contractor record; no real company or person.",
         "source_url": "demo://local/research/northwind-roofing", "field_provenance": {"all_fields": "demonstration_sample"}},
        {"company_name": "Brightpath Dental (sample)", "website": "https://brightpath-dental.example",
         "industry": "Dental", "location": "Ohio, US (sample)", "employee_count": 38,
         "contact_name": "Casey Morgan (sample)", "job_title": "Practice Manager (sample)",
         "company_description": "Synthetic sample dental practice record; no real company or person.",
         "source_url": "demo://local/research/brightpath-dental", "field_provenance": {"all_fields": "demonstration_sample"}},
        {"company_name": "Riverbend Mechanical (sample)", "website": "https://riverbend-mechanical.example",
         "industry": "HVAC", "location": "Georgia, US (sample)", "employee_count": 65,
         "contact_name": "Taylor Quinn (sample)", "job_title": "Operations Manager (sample)",
         "company_description": "Synthetic sample HVAC contractor record; no real company or person.",
         "source_url": "demo://local/research/riverbend-mechanical", "field_provenance": {"all_fields": "demonstration_sample"}},
    ]
    for item in sample_rows:
        item["company_id"] = company["id"]
        prospects.append(await store.create_prospect(item))

    research = [
        (prospects[0], "A synthetic planning note says the sample contractor is considering a second service area next quarter. The note is invented for this demonstration and is not a real public source."),
        (prospects[1], "A synthetic operations note says the sample practice handles appointment requests by phone. The note is invented for this demonstration and is not a real public source."),
        (prospects[2], "A synthetic hiring note says the sample contractor posted a service coordinator role. The note is invented for this demonstration and is not a real public source."),
    ]
    for prospect, text in research:
        source = await store.save_research_source(prospect["id"],
            f"demo://local/cached-research/{prospect['id']}", "Synthetic demonstration research", text, status="demo")
        product = bookings if prospect is not prospects[2] else followup
        category = "expansion" if prospect is prospects[0] else "operational_challenge" if prospect is prospects[1] else "hiring"
        await store.save_signals(product["id"], prospect["id"], [{
            "category": category,
            "supporting_evidence": text.split(" The note")[0], "source_url": source["url"],
            "confidence": .7, "product_relevance": "Synthetic example for product-context demonstration.",
            "business_implication": "Sample implication only.", "potential_opportunity": "Review with a real source before use.",
        }])
        await store.save_artifact(product["id"], prospect["id"], "demo_research",
                                  {"demonstration_sample": True, "notice": "Synthetic research. Not verified public intelligence.", "source_url": source["url"]},
                                  [source["url"]])

    await store.save_conversation(bookings["id"], prospects[0]["id"],
        "Thanks for reaching out. Could you send me a little more information about how this works?", {}, True)
    await store.save_conversation(followup["id"], prospects[1]["id"],
        "Please remove me from your list. I do not want to receive further emails.", {}, True)
    return {"status": "initialized", "company_id": company["id"],
            "product_ids": [bookings["id"], followup["id"]], "prospects": len(prospects),
            "notice": "All included prospect, research, signal, ICP and conversation records are synthetic demonstration data."}


if __name__ == "__main__":
    print(json.dumps(asyncio.run(initialize()), indent=2))
