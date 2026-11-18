from __future__ import annotations

import pytest

import sellbird.sales_discovery as discovery
from sellbird.collectors.discover import Business, DiscoveryQuery
from sellbird.sales_store import SalesStore


def _company(name="Seller"):
    return {"name": name, "description": "", "industry": "", "website": "",
            "company_size": "", "target_geography": "", "business_model": "",
            "existing_sales_information": ""}


def _product(company_id, name="Product"):
    return {"company_id": company_id, "name": name, "description": "", "features": [],
            "benefits": [], "target_market": "", "pricing": "", "value_proposition": "",
            "competitive_differentiation": "", "customer_pain_points": [], "sales_positioning": "",
            "icp_criteria": {}, "scoring_weights": {"industry_fit": 1.0}}


@pytest.mark.asyncio
async def test_openstreetmap_results_import_with_source_and_unknowns_preserved(tmp_path, monkeypatch):
    store = SalesStore(tmp_path / "discovery.sqlite3")
    await store.ensure()
    seller = await store.create_company(_company())
    product = await store.create_product(_product(seller["id"]))

    async def geocode(state, queries, radius_km=40, client=None):
        queries[0].coordinate = f"39.7392,-104.9903,{radius_km}"
        return queries

    results = [Business(name="Mile High Plumbing", website="https://milehigh.example",
                        phone="+1-303-555-0100", category="plumber", location="Denver, CO",
                        external_id="osm:way/42", source_url="https://www.openstreetmap.org/way/42")]

    async def fetch(self, client, env, query):
        assert query.coordinate == "39.7392,-104.9903,25"
        return results

    monkeypatch.setattr(discovery, "resolve_coordinates", geocode)
    monkeypatch.setattr(type(discovery.PROVIDERS["osm"]), "fetch", fetch)
    monkeypatch.setattr(discovery, "_last_geocode_at", 0)
    monkeypatch.setattr(discovery, "_last_overpass_at", 0)
    monkeypatch.setattr(discovery.OpenStreetMap, "MIN_INTERVAL", 0)

    report = await discovery.discover_osm_prospects(
        store, company_id=seller["id"], product_id=product["id"],
        term="plumber", location="Denver, CO", radius_km=25, limit=10,
    )
    assert report["found"] == report["imported"] == 1
    [prospect] = await store.prospects(seller["id"])
    assert prospect["company_name"] == "Mile High Plumbing"
    assert prospect["source_url"] == "https://www.openstreetmap.org/way/42"
    assert prospect["website"] == "https://milehigh.example"
    assert prospect["phone"] == "+1-303-555-0100"
    assert prospect["contact_name"] == prospect["business_email"] == ""
    assert prospect["employee_count"] is None and prospect["revenue_range"] == ""
    assert prospect["field_provenance"]["company_name"] == "extracted"
    assert prospect["research_status"] == "not_researched"

    second = await discovery.discover_osm_prospects(
        store, company_id=seller["id"], product_id=product["id"],
        term="plumber", location="Denver, CO", radius_km=25, limit=10,
    )
    assert second["imported"] == 0 and second["duplicates"] == 1
    assert len(await store.prospects(seller["id"])) == 1


@pytest.mark.asyncio
async def test_osm_discovery_rejects_unknown_categories_and_cross_business_products(tmp_path):
    store = SalesStore(tmp_path / "validation.sqlite3")
    await store.ensure()
    seller_a = await store.create_company(_company("Seller A"))
    seller_b = await store.create_company(_company("Seller B"))
    product_a = await store.create_product(_product(seller_a["id"]))
    product_b = await store.create_product(_product(seller_b["id"]))

    with pytest.raises(discovery.ProspectDiscoveryError, match="does not map"):
        await discovery.discover_osm_prospects(
            store, company_id=seller_a["id"], product_id=product_a["id"],
            term="B2B SaaS", location="Denver, CO",
        )
    with pytest.raises(discovery.ProspectDiscoveryError, match="does not belong"):
        await discovery.discover_osm_prospects(
            store, company_id=seller_a["id"], product_id=product_b["id"],
            term="plumber", location="Denver, CO",
        )
