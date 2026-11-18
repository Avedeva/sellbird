# Harvey Local Sales Agent — Implementation Plan

## Repository audit (pre-implementation)

- The checkout is the Sellbird successor to Harvey (`ethanplusai/sellbird`), not a checkout whose remote is `ethanplusai/harvey`. The README confirms the Harvey-to-Sellbird rename and preserves that project history.
- Backend is Python 3.11+, with an existing FastAPI dashboard (`sellbird/dashboard.py`), agent orchestration (`sellbird/main.py`, `sellbird/agents/`), Pydantic configuration/models, and asynchronous SQLite storage with append-only schema migrations (`sellbird/state.py`, `sellbird/storage.py`).
- The existing dashboard is a bundled vanilla HTML/CSS/JS UI (`sellbird/web/`), not React. It has many working pipeline, prospect, conversation, activity, and settings routes and is protected by local dashboard-token middleware.
- Existing sales pipeline: Scout discovers companies/contacts and extracts public-site facts; Analyst classifies signals; Writer generates outreach; Handler processes replies; StateManager persists companies, prospects, campaigns, conversations, outbox, signals and usage. These are useful pieces to preserve.
- Existing inference is incompatible with this assignment: `sellbird/brain.py` defaults to Claude Code and supports Codex, and configuration/setup/CLI expose those paid subscription paths. It has no Ollama provider.
- Existing persistence is SQLite and uses migrations, WAL, foreign keys, and deduplication. The current schema is oriented around one configured offer and does not model multiple product contexts or the required generated artifacts.
- Dependencies already include FastAPI, Uvicorn, HTTPX, Playwright, BeautifulSoup, Pydantic and aiosqlite. No Sentence Transformers or Scrapy dependency is currently declared.
- The repository has a large existing pytest suite. The working tree already contains user changes to `pyproject.toml` and an untracked `uv.lock`; these are being preserved and will be kept in sync only as needed for this implementation.

## Target architecture

- Keep the existing Sellbird/Harvey dashboard, FastAPI application, auth guard, and SQLite database.
- Add a clearly accessible Sales Agent section and modular `/api/sales/*` routes to the same FastAPI application.
- Add isolated relational tables for sales companies, products, product ICPs, prospects, research sources/findings, buying signals, workflow artifacts, conversations, inference logs, and task status. Every product-derived record carries a product foreign key.
- Put all inference behind one Ollama client. The endpoint defaults to loopback and accepts only loopback/private network addresses. No provider fallback is allowed. Pydantic validates every structured response; timeouts/errors are persisted without logging prompts or sensitive prospect data.
- Use deterministic scoring with product-configurable factor weights. Keep extracted, verified, inferred, and missing information explicitly distinguished.
- Research uses the existing SSRF-resistant public HTTP transport, robots.txt checks, bounded requests, BeautifulSoup extraction, cached source records, and Playwright only as an optional JavaScript-rendering fallback. Cached-research analysis stays local/offline.
- Hardware recommendations use actual OS/RAM/CPU/GPU data. Optional Sentence Transformers load only from a configured local model directory with downloads disabled.
- Frontend extends Harvey's bundled local dashboard with functional sales-agent views and system/inference status.

## Requirement-to-code mapping

| Requirement | Planned implementation |
|---|---|
| Existing Harvey functionality audit | This document; current app modules and routes above |
| Local-only inference | `sellbird/local_ai.py`, strict local endpoint validation, inference log table |
| Company and product context | `sellbird/sales_store.py`, `sellbird/sales_schemas.py`, `/api/sales/companies` and `/products` |
| Profile and ICP generation | `sellbird/sales_workflows.py`, profile/ICP endpoints |
| Prospect create/import/dedup | Sales store + prospect routes, transactional CSV import |
| Public and cached research | `sellbird/sales_research.py`, source-attributed cached records and research routes |
| Buying signals/problem statements/outreach/replies | Local structured workflow service + API routes |
| Explainable scoring | Deterministic configurable scoring service and persisted breakdown |
| Hardware/model status | `sellbird/hardware.py`, system routes |
| Offline acceptance | Acceptance test, outbound interception, setup and repeatable procedure docs |
| Dependency/provider audit | `scripts/audit_local_ai.py`, `COST_AND_DEPENDENCY_AUDIT.md` |
| Demo data and product UX | Initialization script, sample data, integrated sales dashboard view |

## Deficiencies and risks found

- Existing default inference violates the zero-paid-inference rule and must be removed from active execution paths.
- Existing product config is a single YAML offer; product-specific persisted contexts are missing.
- Existing prospects/company tables do not capture product-specific qualification, source evidence, or the required verification labels.
- Existing dashboard metrics are for the current Sellbird outreach pipeline; the new sales-agent metrics need live queries against their own records.
- Ollama, models, model licences, and hardware capabilities are machine/environment dependent. A real model integration and offline run cannot be claimed until Ollama and a local model are present.
- Fresh web research requires internet and is separate from local inference. Robots policies and site restrictions can prevent extraction; the application must report that honestly.
- Heavy embedding/crawling dependencies may make first installation slow. Embeddings must be optional at runtime and must fail clearly when the local model directory is absent.
- Existing provider-focused tests may need replacement/retirement where they assert paid-provider behavior; unrelated legacy pipeline behavior should remain covered.

## Database design

Use SQLite migrations and foreign keys. New tables are prefixed `sales_` to coexist with Harvey/Sellbird tables:

- `sales_companies`: company profile inputs and generated profile JSON.
- `sales_products`: company-scoped products, value propositions, ICP criteria, scoring weights, and generated ICP JSON.
- `sales_prospects`: company, contact, company description, geography, employee/revenue hints, source, status, and confidence-labelled field data.
- `sales_research_sources`: prospect/product-scoped URL, timestamp, extraction status, content hash, and cached text.
- `sales_artifacts`: typed product/prospect workflow output (research synthesis, problem statement, score, email, reply result) with evidence JSON.
- `sales_signals`: product-specific signal classification and supporting evidence/source/confidence.
- `sales_conversations`: sample or user-provided reply text; explicit demo/sample marker.
- `sales_inference_logs`: timestamp, workflow, local endpoint, model, status, duration, and bounded error details only.
- `sales_tasks`: research/background task status and error summaries.

Product foreign keys are mandatory for ICPs, signals, scores, generated emails, problem statements, and analysis artifacts. Imports deduplicate by normalized company website and contact identity where present.

## AI pipeline design

1. Assemble only persisted company/product/prospect/research context for a workflow.
2. Send JSON-mode request to the configured local Ollama endpoint with bounded timeout and retries for transport failures only.
3. Parse and validate against the workflow's Pydantic result model; malformed output is a recorded failure, never a hardcoded substitute.
4. Persist output with product/prospect foreign keys and evidence references.
5. Compute scores outside the LLM using configurable weights and documented factor evidence.
6. Keep local inference logs content-free; preserve failures for visible retry.

## Implementation phases

1. Audit and record this plan/context (done).
2. Build schema, validation models, local Ollama service, hardware detection, and safe configuration.
3. Implement product-scoped CRUD/import/research/workflow API and integrate it into FastAPI.
4. Add a usable sales-agent screen and system status to Harvey's existing dashboard.
5. Add demo data, audit script, acceptance tests, and setup/architecture/offline/licence documentation.
6. Run targeted and existing regression suites, fix failures, and record only observed test/model results in `context.md` and the final report.

## Testing strategy

- Pytest unit tests for SQLite persistence, relationships/deduplication, hardware detection using injected platform facts, Ollama connectivity/errors/invalid JSON/timeouts, scoring, research extraction, and product-context isolation.
- API tests against temporary SQLite databases and mocked local Ollama HTTP responses.
- Security tests that reject cloud Ollama URLs, intercept non-local inference attempts, and verify public research uses the existing guarded HTTP transport.
- Explicit local integration test marked/skipped unless a real Ollama daemon and chosen model are installed. It must not call an external model.
- Offline acceptance test blocks outbound inference requests and exercises the complete cached-data sales workflow. Mocked test results are not presented as genuine local-model evidence.
- Frontend validation via executable JavaScript checks and API-level workflow coverage, subject to available frontend test tooling.

## Known technical risks

- The initial checkout contains user dependency edits and an untracked lockfile; preserve both and avoid resetting or cleaning the tree.
- Ollama and model availability are machine dependent. This host has Ollama and Qwen3 8B Q4_K_M; the app workflow has passed against it. Physical offline acceptance still requires an OS-level disconnect.
- Public sites may prohibit crawling or expose insufficient data; research must fail safely and show source/permission limits.
- Sentence Transformer weights may be absent locally. Any embedding path must refuse network download and retain keyword-based deterministic workflows where embeddings are optional.
- The existing repository's old paid-provider tests conflict with the assignment's new required behavior and need a deliberate compatibility boundary.

## Implementation status — 2026-11-18

Implemented the product-scoped FastAPI/SQLite/Ollama workflow, dashboard page, task persistence/retry, local model/hardware reporting, guarded cached research, optional local embedding loader, synthetic demo initializer, source audit, authenticated OpenAPI JSON, and product-scoped OpenStreetMap discovery. Public-discovery results retain OSM provenance and attribution, deduplicate by OSM object identity, and leave unavailable contact/company-size/revenue fields empty. Nominatim and Overpass endpoints are configurable with HTTPS environment variables; Overpass 406/429 responses trigger a 30-second cooldown. The Ollama-only provider check and active OpenStreetMap-only discovery check pass in `scripts/audit_local_ai.py`.

The full Windows suite passed after the final workflow and reply-route fixes on 2026-11-18: **3,523 passed, 191 skipped, 9 warnings in 267.20 seconds**. Focused workflow, local-inference, and reply-route regressions reported 13 passed. The real Qwen3 8B Q4_K_M application acceptance passed separately: **1 passed in 425.90 seconds**, with eight successful loopback inference logs and no external HTTPX attempts. Compileall, JavaScript syntax, metadata parsing, `git diff --check`, and all seven source/config audit checks passed. Desktop/mobile visual QA passed in headless Edge; the captioned local workflow video is 8:42.92. Physical OS-level offline acceptance remains unverified per the user's direction. See `ACCEPTANCE_MATRIX.md`, `docs/TESTING.md`, and `docs/FINAL_ACCEPTANCE_REPORT.md` for the evidence boundaries.

Scrapy is declared as an optional `research` extra and structures link extraction while the actual network crawl stays on the SSRF-safe shared HTTP transport. The workspace `.venv` has both optional extras installed. The cached Sentence Transformer API index acceptance passed through the venv in 11.66 seconds with offline flags. The UI indexing action requires `SELLBIRD_EMBEDDING_MODEL_PATH` to point at a local model directory. The pre-existing user `pyproject.toml` formatting change and untracked `uv.lock` were preserved.
