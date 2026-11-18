# Implementation Audit — Harvey AI Sales Agent / Local Multi-Product Sales Platform

**Date:** 2026-11-18  
**Repository:** Harvey (successor codebase: Sellbird)  
**Role:** Principal AI Engineer, Senior Full-Stack Engineer, and Test Engineer  
**Objective:** Assessment of existing architecture, requirements mapping, gap analysis, and implementation record for the EDXSO AI Engineer Intern Assignment 2.

---

## 1. Existing Architecture Overview

The starting repository originated as **Harvey** (open-source autonomous outreach platform, evolving into Sellbird). The existing stack comprises:
- **Backend Framework:** Python 3.12 with **FastAPI** (`sellbird/dashboard.py`, `sellbird/sales_routes.py`) and **Uvicorn** ASGI server.
- **Data Persistence:** **SQLite** (`data/sellbird.db`) with async operations via `aiosqlite`, WAL mode, and versioned schema migrations (`sellbird/sales_store.py`).
- **Inference Layer:** Dedicated **OllamaService** (`sellbird/local_ai.py`) communicating strictly with loopback/private Ollama daemon (`http://127.0.0.1:11434`) using Pydantic schema validation. Zero cloud LLM APIs.
- **Frontend Architecture:** Integrated single-page web UI (`sellbird/web/sales.html`, `sellbird/web/sales.js`, `sellbird/web/sales.css`) authenticated via token-based bearer protection (`DashboardGuard`), served from disk with vendored fonts for complete offline presentation.
- **Web Research & Discovery:** Public OpenStreetMap (Nominatim / Overpass) for prospect discovery (`sellbird/sales_discovery.py`), guarded crawler with SSRF protection, robots.txt compliance, BeautifulSoup extraction, optional Playwright JS rendering, and Scrapy link extraction (`sellbird/sales_research.py`).
- **Embeddings:** Local vector indexing via `SentenceTransformers` (`all-MiniLM-L6-v2`) in `sellbird/local_embeddings.py` storing 384-dimensional normalized vectors in SQLite.

---

## 2. Existing Functional Modules

1. **Local Model Gateway (`sellbird/local_ai.py`):**
   - Validates endpoints strictly (enforces loopback/private IPs; rejects external/cloud endpoints).
   - Structured JSON output generation with Pydantic model validation.
   - Comprehensive error and failure handling (timeout, 404 missing model, 500 transient daemon retry).
   - Content-free logging in `sales_inference_logs` (tracks workflow, duration, status, endpoint; no prompt leakage).

2. **Multi-Product Sales Store (`sellbird/sales_store.py`):**
   - Schema tables: `sales_companies`, `sales_products`, `sales_icps`, `sales_prospects`, `sales_research_sources`, `sales_artifacts`, `sales_signals`, `sales_conversations`, `sales_inference_logs`, `sales_tasks`, `sales_settings`, `sales_embeddings`.
   - Complete foreign keys, cascading deletes, unique constraints, and indices.
   - Distinct product scoping ensuring ICPs, artifacts, signals, problem statements, and scores are never conflated across products.

3. **Core Sales Intelligence Workflows (`sellbird/sales_workflows.py`):**
   - Business Profile Generation (`generate_profile`).
   - Product-Specific ICP Generation (`generate_icp`).
   - Research Grounding & Summarization (`summarize_research`).
   - Buying-Signal Identification and Evidence Verification (`classify_signals`).
   - Problem-Statement Hypothesis Generation (`generate_problem`).
   - Deterministic Explainable Prospect Scoring (`score`).
   - Personalized Sales Email Generation (`generate_email`).
   - Conversation & Reply Classification (`classify_reply`).

4. **Hardware Detection & Guidance (`sellbird/hardware.py`):**
   - RAM and available physical memory detection (Windows `GlobalMemoryStatusEx`, `sysconf`, `psutil`).
   - GPU VRAM detection via `nvidia-smi`.
   - Ollama storage directory free disk space measurement.
   - Conservative hardware recommendation engine across Standard and High-Performance profiles.

5. **Prospect Discovery & Research (`sellbird/sales_discovery.py`, `sellbird/sales_research.py`):**
   - Free OpenStreetMap discovery by trade category and location.
   - Robots.txt parsing, rate-limiting, and DNS-pinned HTTP fetches.
   - Offline research cache preventing redundant external lookups.

---

## 3. Assignment Requirements Mapping

| Assignment Requirement | Module Location | Implementation Status | Verification |
|---|---|---|---|
| 1. Business Profile Generation | `sellbird/sales_workflows.py::generate_profile` | Implemented | Verified via `test_offline_sales_workflow.py` |
| 2. Multiple Product Configuration | `sellbird/sales_store.py::create_product` | Implemented | Verified via `test_sales_store.py` |
| 3. Product-Specific ICP Generation | `sellbird/sales_workflows.py::generate_icp` | Implemented | Verified via `test_offline_sales_workflow.py` |
| 4. Prospect Discovery & Research | `sellbird/sales_discovery.py`, `sellbird/sales_research.py` | Implemented | Verified via `test_sales_discovery.py` |
| 5. Buying-Signal Classification | `sellbird/sales_workflows.py::classify_signals` | Implemented | Verified via `test_sales_workflows.py` |
| 6. Problem-Statement Generation | `sellbird/sales_workflows.py::generate_problem` | Implemented | Verified via `test_offline_sales_workflow.py` |
| 7. Prospect Scoring Engine | `sellbird/sales_workflows.py::score` | Implemented | Verified via `test_sales_workflows.py` |
| 8. Prospect Prioritization | `sellbird/sales_store.py::prospects` | Implemented | Verified via `test_sales_store.py` |
| 9. Personalized Email Generation | `sellbird/sales_workflows.py::generate_email` | Implemented | Verified via `test_offline_sales_workflow.py` |
| 10. Reply Classification | `sellbird/sales_workflows.py::classify_reply` | Implemented | Verified via `test_offline_sales_workflow.py` |

---

## 4. Broken or Incomplete Functionality Addressed

1. **Cloud AI Dependencies in Legacy Harvey Code:**
   - *Issue:* Original Harvey codebase contained historical references to Claude CLI, OpenAI, and token-based senders.
   - *Resolution:* Implemented strict isolation boundary. All sales agent workflows in `/sales-agent` and `/api/sales/*` route exclusively through `OllamaService`. Verified via `scripts/audit_local_ai.py` (all 7 zero-cost checks pass).
2. **Product Isolation in Scoring and Outreach:**
   - *Issue:* Legacy systems treated prospects with global scores.
   - *Resolution:* Prospect prioritization queries (`sales_store.py::prospects`) join on `sales_artifacts` scoped specifically by `product_id`.
3. **Evidence Grounding:**
   - *Issue:* LLMs tend to hallucinate buying signals and pain points.
   - *Resolution:* Added `_contains_quote` validation in `sales_workflows.py`. Signals and research summaries fail or reject unverified claims if the exact string excerpt is not found in stored research sources.
4. **Offline Mode Toggle & Guard:**
   - *Issue:* Uncontrolled network calls when offline.
   - *Resolution:* Added `SELLBIRD_OFFLINE` environment flag and database-backed `offline_mode` setting in `/api/sales/offline-mode` to block outbound web scraping while keeping all local inference active.

---

## 5. Potential Security & Reliability Issues

1. **SSRF Vulnerabilities during Prospect Research:**
   - *Protection:* `sellbird/public_http.py` implements DNS resolution pinning and explicitly prohibits private, loopback, multicast, or link-local IP addresses.
2. **Denial of Service via Overpass / Nominatim Rate Limits:**
   - *Protection:* Enforced strict pacing (1.1s minimum delay on Nominatim; 30s backoff on Overpass 429). Configurable custom endpoints supported without code modifications.
3. **Data Loss / Concurrency:**
   - *Protection:* SQLite configured in WAL mode with `PRAGMA busy_timeout = 30000` to prevent database locks during concurrent read/write operations.
4. **Token Security:**
   - *Protection:* Dashboard endpoints protected by secure random bearer token stored in `data/dashboard-token`.

---

## 6. Dependencies Requiring Replacement or Removal

- **Prohibited Paid AI SDKs:** No `openai`, `anthropic`, `google-generativeai`, `cohere`, or `langchain-community` cloud wrappers are present in runtime requirements.
- **Approved Permissive Dependencies:**
  - `fastapi`, `uvicorn`, `pydantic` (BSD/MIT)
  - `aiosqlite` (MIT)
  - `httpx` (BSD-3-Clause)
  - `beautifulsoup4` (MIT)
  - `playwright` (Apache-2.0)
  - `scrapy` (BSD-3-Clause, optional extra)
  - `sentence-transformers` (Apache-2.0, optional extra)

---

## 7. Recommended Implementation & Verification Sequence

1. **Database & Schema Verification:** Confirm migrations, foreign keys, and indexes survive restarts.
2. **Local Model Gateway Audit:** Validate timeout, error propagation, and loopback enforcement.
3. **Sales Workflow Execution:** Test deterministic scoring, grounded problem statements, and email drafting.
4. **Full Offline Acceptance Execution:** Run `test_offline_sales_workflow.py` with `SELLBIRD_OFFLINE=1` using local `qwen3:8b`.
5. **UI & API Integration Verification:** Validate FastAPI endpoints and the responsive web interface at `/sales-agent`.
6. **Documentation & Compliance Finalization:** Verify all required technical deliverables are present and accurate.
