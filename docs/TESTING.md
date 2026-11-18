# Testing record

## Full regression suite

On 2026-11-18, the full Windows suite completed after the final sales-workflow and reply-route fixes: **3,523 passed, 191 skipped, and 9 warnings in 267.20 seconds**. The run used the workspace `.venv`; expected external-service and opt-in hardware/model cases account for skips. The nine warnings are existing `datetime.utcnow()` deprecations in the legacy analyst module.

The focused sales-workflow, local-inference, and reply-route checks passed separately: **13 passed in 2.38 seconds**. These focused results are not added to the full-suite count.

## Static, source, and browser checks

- `.venv\\Scripts\\python.exe -m compileall -q sellbird scripts`: passed after the final Python changes.
- `node --check sellbird\\web\\sales.js`: passed.
- `.venv\\Scripts\\python.exe scripts\\audit_local_ai.py`: all seven active-routing/configuration checks passed; `network_requests_made: false`.
- `pyproject.toml` parsed successfully with Python `tomllib`.
- `git diff --check`: passed.
- Headless Microsoft Edge visual QA passed desktop and 390 × 844 mobile checks against an isolated synthetic dashboard; screenshots and the full demo recording are in [`docs/evidence/`](evidence/README.md).

## Real model and application-level offline acceptance

Ollama is installed locally with `qwen3:8b` (Q4_K_M) and `nomic-embed-text:latest`. Direct CLI inference succeeded. The opt-in Sellbird application-level acceptance passed separately: **1 passed in 425.90 seconds**. It generated eight workflow results using local Qwen and asserted that there were no external HTTPX attempts.

```powershell
$env:SELLBIRD_RUN_LOCAL_ACCEPTANCE = "1"
$env:SELLBIRD_OFFLINE = "1"
$env:SELLBIRD_OLLAMA_MODEL = "qwen3:8b"
.\.venv\Scripts\python.exe -m pytest -q tests/acceptance/test_offline_sales_workflow.py
```

The HTTP guard and app Offline Mode are application-level checks, not physical network isolation. The recorded demo [`sellbird-local-sales-demo.webm`](evidence/README.md) shows the app toggle and a cached workflow; no Wi-Fi/Ethernet disconnect or packet capture was performed.

## Local embeddings

The opt-in local embedding route acceptance passed in the workspace `.venv`: **1 passed in 11.66 seconds**. It loaded the cached `all-MiniLM-L6-v2` model with `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` and persisted a normalized 384-dimensional vector. The UI indexing action needs `SELLBIRD_EMBEDDING_MODEL_PATH` set to a local model directory.

## Common commands

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q sellbird scripts
node --check sellbird/web/sales.js
.\.venv\Scripts\python.exe scripts/audit_local_ai.py
```
