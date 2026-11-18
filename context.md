# Engineering Context — Harvey/Sellbird Local AI Sales Agent

Last updated: 2026-11-18
Workspace: `C:\Users\suees\skill\Job\sellbird`

## Objective

Complete EDXSO Assignment 2 by extending the existing Sellbird/Harvey application into a local-first, multi-product sales agent. All model inference must go through local Ollama; no cloud fallback is allowed. See `IMPLEMENTATION_PLAN.md` for the original audit and design.

## Repository and preserved user state

- Existing repository remote: `https://github.com/ethanplusai/sellbird.git`; Harvey is the former project name.
- Existing app uses FastAPI, authenticated local dashboard, HTML/CSS/JS, async SQLite, migrations, and a multi-stage prospecting workflow.
- `sellbird/brain.py` previously used Claude/Codex; active brain now routes to Ollama. `sellbird.config.BRAIN_PROVIDERS` is `("ollama",)`.
- The working tree already had a user change in `pyproject.toml` (quote/case normalization) and an untracked `uv.lock`. Preserve both; neither has been reset or overwritten. The new local-agent code does not add optional Scrapy or Sentence Transformers packages to that user lock.
- Existing public HTTP transport is SSRF-resistant and is reused for new public research.

## Implemented

- Local inference gateway: `sellbird/local_ai.py`; private/loopback host validation, no environment proxies, strict Pydantic JSON validation, timeouts/retry, content-free inference log, and no cloud fallback.
- Existing Brain adapted to Ollama; legacy config, CLI, setup, Scout/discovery and email verification active paths restricted to Ollama, OpenStreetMap, and DNS/SMTP respectively.
- New product-scoped SQLite schema in `sellbird/sales_store.py` with companies, products, ICPs, prospects, research cache, signals, artifacts, conversations, inference logs, task queue, settings, embeddings, and foreign keys.
- Schemas and workflows in `sellbird/sales_schemas.py` and `sellbird/sales_workflows.py`: business profile, product ICP, cached-source summary, evidence-grounded signals/problem/email/reply, deterministic weighted scoring, and product isolation checks.
- Public research in `sellbird/sales_research.py`: robots checks, page/time bounds, shared SSRF-safe HTTP transport, BeautifulSoup extraction, optional Playwright rendering, optional Scrapy `LinkExtractor`, and stored source cache.
- Actual hardware detection/model recommendations in `sellbird/hardware.py`; local-only optional Sentence Transformers loader/indexing in `sellbird/local_embeddings.py`.
- FastAPI routes in `sellbird/sales_routes.py` and integrated `/sales-agent` UI in `sellbird/web/sales.html`, `.css`, `.js`. Profile/ICP can be generated and edited. Failed local AI requests persist retryable task IDs and can be retried from System & inference.
- Product-scoped, user-triggered OSM discovery imports mapped local businesses with provenance and attribution, deduplicates by OSM object ID, and leaves fields the map does not supply empty. Endpoints are operator-configurable by HTTPS environment variables and rate-limited responses pause for 30 seconds.
- Synthetic-only demo initializer: `scripts/init_demo_data.py`.
- Static audit script: `scripts/audit_local_ai.py`. It passed here: Ollama-only provider config, local brain gateway, public endpoint rejection, ignored proxy environment, no paid LLM package in runtime dependencies, OSM-only active discovery.
- Documentation: README, `docs/IMPLEMENTATION_AUDIT.md`, `docs/TESTING.md`, `docs/ZERO_COST_COMPLIANCE.md`, `docs/LICENCES_AND_DEPENDENCIES.md`, `docs/DEMO_SCRIPT.md`, `docs/FINAL_ACCEPTANCE_REPORT.md`, `docs/API_OPENAPI.md`, `docs/ARCHITECTURE.md`, `docs/LOCAL_AI_SETUP.md`, `docs/HARDWARE_REQUIREMENTS.md`, `docs/OFFLINE_ACCEPTANCE.md`, `docs/LICENCES.md`, `docs/KNOWN_LIMITATIONS.md`, `COST_AND_DEPENDENCY_AUDIT.md`, and `ACCEPTANCE_MATRIX.md`.
- Authored tests: SQLite persistence/dedup, local inference JSON/error/logging/security, product-scoped workflows/evidence, retry queue, and opt-in real-model acceptance. The acceptance test blocks non-local HTTPX hosts but does not physically disable host networking.

## Verification state

- The full Windows pytest suite passed after the final workflow and reply-route fixes: **3,523 passed, 191 skipped, 9 warnings in 267.20 seconds**. Focused workflow, local inference, and route regressions reported 13 passed. See `docs/TESTING.md` for commands.
- Closing checks passed: `.venv\\Scripts\\python.exe -m compileall -q sellbird scripts`, `node --check sellbird\\web\\sales.js`, `git diff --check`, and `pyproject.toml` parsing.
- `scripts/audit_local_ai.py` passed all seven active-routing/configuration checks and made no network requests.
- Ollama has `qwen3:8b` installed at Q4_K_M quantization. Direct local CLI inference passed, and the application-level test passed: **1 passed in 425.90 seconds**, with eight successful logs to loopback and no external HTTPX attempts. Physical OS-level offline acceptance remains unverified per the user's direction.
- Headless Edge visual QA passed at desktop and 390 × 844 mobile sizes; screenshots are in `docs/evidence/`. Physical offline acceptance remains outstanding.
- The workspace `.venv` includes the optional `research` and `local-embeddings` extras. The cached `all-MiniLM-L6-v2` API indexing acceptance passed in 11.66 seconds with offline flags and produced a normalized 384-dimensional vector. Configure `SELLBIRD_EMBEDDING_MODEL_PATH` for UI indexing; default sales workflows do not require embeddings.
- The captioned local sales-agent video is `docs/evidence/sellbird-local-sales-demo.webm` (8:42.92). It shows application Offline Mode only; browser requests to non-local origins were blocked and none were attempted.

## Test commands for a prepared developer environment

```powershell
python -m pip install -e ".[dev]"
python -m pytest -q tests/test_sales_store.py tests/test_local_ai.py tests/test_sales_workflows.py tests/test_sales_routes.py tests/acceptance/test_offline_sales_workflow.py
python -m pytest -q
python scripts/audit_local_ai.py
```

Real Ollama test only after downloading model:

```powershell
$env:SELLBIRD_RUN_LOCAL_ACCEPTANCE = "1"
$env:SELLBIRD_OFFLINE = "1"
python -m pytest -q tests/acceptance/test_offline_sales_workflow.py
```

## Remaining tasks / honest gaps

1. Perform physical network-disconnected acceptance.
2. Complete browser visual verification and capture a short demo; publish only if the assignment submission requires it.
3. GPU detection covers NVIDIA only. Scrapy is used for link extraction only; the network fetch loop stays in the SSRF-guarded transport. Sentence Transformers and its local model need a separate optional install.
