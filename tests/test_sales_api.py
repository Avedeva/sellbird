from __future__ import annotations

from fastapi.testclient import TestClient

import sellbird.dashboard as dashboard
import sellbird.sales_routes as sales_routes
from sellbird.sales_store import SalesStore


class OfflineAI:
    def __init__(self, store):
        self.store = store

    async def health(self):
        return {"status": "unavailable", "configured_model": "qwen3:4b",
                "model_available": False, "error": "Test fixture only"}


def test_authenticated_dashboard_serves_sales_shell_and_product_crud(tmp_path, monkeypatch):
    store = SalesStore(tmp_path / "sales.sqlite3")
    monkeypatch.setattr(sales_routes, "_store", lambda request: store)
    monkeypatch.setattr(sales_routes, "OllamaService", OfflineAI)
    monkeypatch.setattr(dashboard.token_store, "path", tmp_path / "dashboard-token")
    monkeypatch.setattr(dashboard.token_store, "_token", None)
    token = dashboard.token_store.get()
    headers = {"Authorization": f"Bearer {token}"}

    with TestClient(dashboard.app, base_url="http://127.0.0.1:5555") as client:
        shell = client.get("/sales-agent")
        assert shell.status_code == 200
        assert "Local AI Sales Agent" in shell.text
        assert client.get("/api/sales/companies").status_code == 401

        company = client.post("/api/sales/companies", headers=headers, json={
            "name": "Sample Seller", "description": "Stored locally", "industry": "Software",
            "website": "", "company_size": "1-10", "target_geography": "US",
            "business_model": "B2B", "existing_sales_information": "",
        }).json()
        product = client.post("/api/sales/products", headers=headers, json={
            "company_id": company["id"], "name": "Product One", "description": "Test",
            "features": [], "benefits": [], "target_market": "Clinics", "pricing": "",
            "value_proposition": "Reduce manual work", "competitive_differentiation": "",
            "customer_pain_points": [], "sales_positioning": "", "icp_criteria": {},
            "scoring_weights": {"industry_fit": 1.0},
        }).json()
        assert product["company_id"] == company["id"]

        edited_icp = {
            "target_industries": ["Clinics"], "company_size": "2-30", "revenue_range": "",
            "geographic_markets": ["US"], "buyer_personas": [], "decision_maker_roles": [],
            "technology_stack": [], "business_challenges": [], "purchase_motivations": [],
            "exclusion_criteria": [], "qualification_criteria": ["Verify need"],
        }
        response = client.put(f"/api/sales/products/{product['id']}/icp", headers=headers, json=edited_icp)
        assert response.status_code == 200
        assert response.json()["icp"] == edited_icp


def test_osm_discovery_is_company_scoped_offline_aware_and_task_tracked(tmp_path, monkeypatch):
    store = SalesStore(tmp_path / "discovery-api.sqlite3")
    monkeypatch.setattr(sales_routes, "_store", lambda request: store)
    monkeypatch.setattr(sales_routes, "OllamaService", OfflineAI)
    monkeypatch.setattr(dashboard.token_store, "path", tmp_path / "dashboard-token")
    monkeypatch.setattr(dashboard.token_store, "_token", None)
    token = dashboard.token_store.get()
    headers = {"Authorization": f"Bearer {token}"}

    async def offline(_store):
        return True

    async def online(_store):
        return False

    async def complete_task(task_store, task_id, args):
        await task_store.update_task(task_id, "completed", {
            "provider": "OpenStreetMap", "term": args["term"], "imported": 1,
            "duplicates": 0, "prospects": [],
        })

    with TestClient(dashboard.app, base_url="http://127.0.0.1:5556") as client:
        company = client.post("/api/sales/companies", headers=headers, json={
            "name": "Seller", "description": "", "industry": "", "website": "",
            "company_size": "", "target_geography": "Denver", "business_model": "",
            "existing_sales_information": "",
        }).json()
        product = client.post("/api/sales/products", headers=headers, json={
            "company_id": company["id"], "name": "Product", "description": "",
            "features": [], "benefits": [], "target_market": "Local services", "pricing": "",
            "value_proposition": "", "competitive_differentiation": "",
            "customer_pain_points": [], "sales_positioning": "", "icp_criteria": {},
            "scoring_weights": {"industry_fit": 1.0},
        }).json()
        payload = {"company_id": company["id"], "product_id": product["id"],
                   "term": "roofer", "location": "Denver, CO", "radius_km": 25, "limit": 10}

        monkeypatch.setattr(sales_routes, "_offline", offline)
        assert client.post("/api/sales/discover", headers=headers, json=payload).status_code == 409
        monkeypatch.setattr(sales_routes, "_offline", online)
        monkeypatch.setattr(sales_routes, "_run_discovery_task", complete_task)

        unsupported = client.post("/api/sales/discover", headers=headers,
                                  json={**payload, "term": "B2B SaaS"})
        assert unsupported.status_code == 400
        response = client.post("/api/sales/discover", headers=headers, json=payload)
        assert response.status_code == 202
        assert response.json()["provider"] == "OpenStreetMap"
        task = client.get(f"/api/sales/tasks/{response.json()['task_id']}", headers=headers).json()
        assert task["status"] == "completed"
        assert task["result"]["imported"] == 1
