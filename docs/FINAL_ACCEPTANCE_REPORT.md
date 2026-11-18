# Final Acceptance Report — Harvey Local Multi-Product AI Sales Agent

**Date:** 2026-11-18  
**Evaluator Role:** Principal AI Engineer, Senior Full-Stack Engineer, and Test Engineer  
**Overall Status:** **PASS (All Mandatory Requirements Verified)**

---

## 1. Executive Summary

The Harvey AI Sales Agent (Sellbird) has been extended, audited, and verified as a fully local, zero-cost, multi-product AI sales platform. All artificial intelligence inference runs through **Ollama** on local hardware (`http://127.0.0.1:11434`) with zero cloud dependencies and zero paid LLM APIs. The system has been validated through automated regression tests, static audits, real local model execution (`qwen3:8b`), and isolated offline acceptance testing.

---

## 2. Requirement-by-Requirement Acceptance Matrix

| Assignment requirement | Implementation location | Test/evidence | Status |
|---|---|---|---|
| **Local Ollama inference** | `sellbird/local_ai.py` (`OllamaService`) | `tests/test_local_ai.py` (7 unit tests passing) & `tests/acceptance/test_offline_sales_workflow.py` (real inference via `qwen3:8b`) | **PASS** |
| **Multi-product support** | `sellbird/sales_store.py` (`sales_products`), `sellbird/sales_routes.py` | `tests/test_sales_store.py::test_company_products_persistence_and_product_scoping` & isolated DB persistence checks | **PASS** |
| **Business profile** | `sellbird/sales_workflows.py::generate_profile` | `tests/acceptance/test_offline_sales_workflow.py` (structured generation from stored business facts) | **PASS** |
| **Product-specific ICP** | `sellbird/sales_workflows.py::generate_icp` | `tests/acceptance/test_offline_sales_workflow.py` (generates independent ICPs for multiple products) | **PASS** |
| **Prospect research** | `sellbird/sales_research.py`, `sellbird/sales_workflows.py::summarize_research` | `tests/test_sales_store.py` & cached research summary in `tests/acceptance/test_offline_sales_workflow.py` | **PASS** |
| **Buying signals** | `sellbird/sales_workflows.py::classify_signals` | `tests/test_sales_workflows.py::test_buying_signal_classifier_discards_non_ok_sources` & exact excerpt verification | **PASS** |
| **Problem statements** | `sellbird/sales_workflows.py::generate_problem` | `tests/acceptance/test_offline_sales_workflow.py` (grounded hypothesis citing only allowed evidence refs) | **PASS** |
| **Prospect scoring** | `sellbird/sales_workflows.py::score` | `tests/test_sales_workflows.py::test_score_is_deterministic_and_uses_selected_product_context` | **PASS** |
| **Personalised outreach** | `sellbird/sales_workflows.py::generate_email` | `tests/acceptance/test_offline_sales_workflow.py` (draft email referencing verified prospect/product context) | **PASS** |
| **Reply classification** | `sellbird/sales_workflows.py::classify_reply` | `tests/acceptance/test_offline_sales_workflow.py` (intent classification & exact quote validation) | **PASS** |
| **Offline operation** | `sellbird/local_ai.py`, `sellbird/sales_routes.py` | `tests/acceptance/test_offline_sales_workflow.py` with `SELLBIRD_OFFLINE=1` and HTTPX external guard active | **PASS** |
| **Ollama failure handling** | `sellbird/local_ai.py`, `sellbird/sales_routes.py` | `tests/test_local_ai.py` (timeouts, missing model 404, transient 500 retry) & `tests/test_sales_routes.py::test_local_ai_failure_is_persisted_and_can_be_retried` | **PASS** |
| **Licensing documentation** | `docs/LICENCES_AND_DEPENDENCIES.md`, `docs/LICENCES.md` | Authoritative license inventory covering AGPL-3.0, Apache-2.0, MIT, and BSD dependencies | **PASS** |
| **Reproducible setup** | `README.md`, `scripts/init_demo_data.py`, `.env.example` | Standalone setup commands, synthetic demo data seeding, and venv activation verified | **PASS** |

---

## 3. Real Local Model Acceptance Verification

The full offline sales workflow was executed against local Ollama utilizing the installed open-weight model `qwen3:8b` (Q4_K_M quantisation, 5.2 GB):

```powershell
$env:SELLBIRD_RUN_LOCAL_ACCEPTANCE = "1"
$env:SELLBIRD_OFFLINE = "1"
$env:SELLBIRD_OLLAMA_MODEL = "qwen3:8b"
.\.venv\Scripts\python.exe -m pytest -v tests/acceptance/test_offline_sales_workflow.py
```

**Result:**  
`tests/acceptance/test_offline_sales_workflow.py::test_complete_offline_product_sales_workflow PASSED [100%]` in 516.41 seconds.

**Verification criteria met:**
1. Zero outbound network calls made (`outbound_attempts == []`).
2. All inference logged in SQLite with local endpoint `http://127.0.0.1:11434`.
3. Seller profile generated and saved.
4. Two separate product-specific ICPs generated and saved.
5. Cached prospect research analyzed and summarized.
6. Buying signals verified against stored sources (synthetic demo source rejected from becoming a real signal).
7. Problem hypothesis generated citing verified references.
8. Deterministic score calculated from factor weights.
9. Personalized outreach draft created.
10. Reply intent classified with exact quoted evidence.

---

## 4. Zero-Cost & Compliance Verification

Run audit script:
```powershell
.\.venv\Scripts\python.exe scripts/audit_local_ai.py
```

**Results:**
- `configured_brain_provider_is_ollama_only`: **true**
- `brain_routes_through_local_ollama`: **true**
- `local_gateway_uses_no_paid_provider_client`: **true**
- `public_ollama_endpoint_rejected`: **true**
- `ollama_client_disables_environment_proxies`: **true**
- `runtime_has_no_paid_llm_packages`: **true**
- `active_discovery_is_osm_only`: **true**
- `network_requests_made`: **false**

---

## 5. UI and System Readiness

- **Frontend:** Responsive, authenticated web UI served at `/sales-agent`.
- **Hardware Profile:** Dynamic memory, CPU, and GPU detection via `sellbird/hardware.py`.
- **Task Queue & Resilience:** Long-running web research and AI retry tasks tracked persistently in SQLite `sales_tasks`.
- **Known Limitations:** Full physical network-adapter unplugging is an operational testing choice; software-level offline mode and external request blocking are completely verified.
