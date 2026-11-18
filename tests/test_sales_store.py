from __future__ import annotations

import pytest

from sellbird.sales_store import DuplicateProspect, SalesStore


def company_input(name="Seller"):
    return {"name": name, "description": "", "industry": "", "website": "",
            "company_size": "", "target_geography": "", "business_model": "",
            "existing_sales_information": ""}


def product_input(company_id, name):
    return {"company_id": company_id, "name": name, "description": "", "features": [],
            "benefits": [], "target_market": "", "pricing": "", "value_proposition": "",
            "competitive_differentiation": "", "customer_pain_points": [], "sales_positioning": "",
            "icp_criteria": {}, "scoring_weights": {"industry_fit": 1.0}}


@pytest.mark.asyncio
async def test_company_products_persistence_and_product_scoping(tmp_path):
    db_path = tmp_path / "sales.sqlite3"
    store = SalesStore(db_path)
    await store.ensure()
    seller = await store.create_company(company_input())
    product_a = await store.create_product(product_input(seller["id"], "Booking"))
    product_b = await store.create_product(product_input(seller["id"], "Lead follow-up"))
    await store.save_icp(product_a["id"], {"target_industries": ["Roofing"]})
    await store.save_icp(product_b["id"], {"target_industries": ["Dental"]})

    # A new store instance proves data survives connection and app restarts.
    reopened = SalesStore(db_path)
    await reopened.ensure()
    assert len(await reopened.companies()) == 1
    assert {x["name"] for x in await reopened.products(seller["id"])} == {"Booking", "Lead follow-up"}
    assert (await reopened.get_product(product_a["id"]))["icp"]["target_industries"] == ["Roofing"]
    assert (await reopened.get_product(product_b["id"]))["icp"]["target_industries"] == ["Dental"]


@pytest.mark.asyncio
async def test_prospect_duplicate_detection_csv_validation_and_foreign_keys(tmp_path):
    store = SalesStore(tmp_path / "sales.sqlite3")
    await store.ensure()
    seller = await store.create_company(company_input())
    prospect = {"company_id": seller["id"], "company_name": "Example Co", "contact_name": "Pat Example",
                "business_email": "PAT@example.com", "field_provenance": {"company_name": "imported"}}
    created = await store.create_prospect(prospect)
    assert created["business_email"] == "PAT@example.com"  # storage preserves case; API schema normalizes it
    with pytest.raises(DuplicateProspect):
        await store.create_prospect({**prospect, "business_email": "pat@example.com"})

    report = await store.import_prospects(
        "company_name,industry,employees\nValid Ltd,Roofing,12\n,Roofing,22\nValid Ltd,Roofing,12\n",
        seller["id"],
    )
    assert report["imported"] == 1
    assert report["skipped"] == 1
    assert report["errors"] == [{"row": 3, "error": "missing company name"}]
    assert (await store.get_prospect(created["id"]))["company_id"] == seller["id"]
    with pytest.raises(KeyError):
        await store.create_product(product_input("missing-company", "Not linked"))


@pytest.mark.asyncio
async def test_external_discovery_ids_dedupe_places_without_merging_same_named_branches(tmp_path):
    store = SalesStore(tmp_path / "external-identity.sqlite3")
    await store.ensure()
    seller = await store.create_company(company_input())
    first = await store.create_prospect({
        "company_id": seller["id"], "company_name": "Neighborhood Dental", "location": "North",
        "external_id": "osm:node/1", "source_url": "https://www.openstreetmap.org/node/1",
    })
    second = await store.create_prospect({
        "company_id": seller["id"], "company_name": "Neighborhood Dental", "location": "South",
        "external_id": "osm:node/2", "source_url": "https://www.openstreetmap.org/node/2",
    })
    assert first["id"] != second["id"]
    with pytest.raises(DuplicateProspect):
        await store.create_prospect({
            "company_id": seller["id"], "company_name": "Neighborhood Dental",
            "external_id": "osm:node/1",
        })


@pytest.mark.asyncio
async def test_prospect_list_prioritizes_using_only_selected_products_scores(tmp_path):
    store = SalesStore(tmp_path / "priority.sqlite3")
    await store.ensure()
    seller = await store.create_company(company_input())
    first_product = await store.create_product(product_input(seller["id"], "First"))
    second_product = await store.create_product(product_input(seller["id"], "Second"))
    alpha = await store.create_prospect({"company_id": seller["id"], "company_name": "Alpha"})
    beta = await store.create_prospect({"company_id": seller["id"], "company_name": "Beta"})
    await store.save_artifact(first_product["id"], alpha["id"], "score", {"score": 72})
    await store.save_artifact(first_product["id"], beta["id"], "score", {"score": 91})
    await store.save_artifact(second_product["id"], alpha["id"], "score", {"score": 98})

    first_order = await store.prospects(seller["id"], first_product["id"])
    second_order = await store.prospects(seller["id"], second_product["id"])
    assert [row["company_name"] for row in first_order] == ["Beta", "Alpha"]
    assert [row["company_name"] for row in second_order] == ["Alpha", "Beta"]
    assert second_order[0]["priority_score"] == 98
    assert second_order[1]["priority_score"] is None

    await store.save_artifact(first_product["id"], beta["id"], "score", {"score": 32})
    metrics = await store.dashboard_stats()
    assert metrics["qualified_prospects"] == 1
    assert metrics["high_priority_prospects"] == 1

