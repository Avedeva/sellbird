# Known limitations

This list separates implemented paths from items that still need live-machine or external evidence.

## Environment and acceptance evidence

- Local Ollama is installed with `qwen3:8b` Q4_K_M and the `nomic-embed-text:latest` tag. Direct local CLI inference and the application-level workflow acceptance passed; see [Final Acceptance Report](FINAL_ACCEPTANCE_REPORT.md) for exact evidence.
- No operating-system network disconnect or packet capture was performed. The opt-in acceptance test's HTTPX guard blocks external application requests, but it does not physically disconnect the host.
- The full Windows pytest suite passed on 2026-11-18 after the final workflow and reply-route fixes: **3,523 passed, 191 skipped, 9 warnings in 267.20 seconds**. The nine warnings are legacy `datetime.utcnow()` deprecations.
- Headless Edge visual acceptance passed for desktop and 390 × 844 mobile layouts on isolated synthetic data. The 8:42.92 captioned UI video is also saved with the screenshots in [browser evidence](evidence/README.md).
- The video demonstrates Sellbird's application Offline Mode and a local cached workflow. Physical Windows network disconnection remains unverified per the user's direction. Repository publication and live deployment were not performed.

## Feature boundaries

- Product-scoped public discovery is available for supported OpenStreetMap categories. OSM coverage is incomplete, especially for service-area trades; it does not provide personal contacts, employee counts, or revenue. Searches use public Nominatim/Overpass services, require network access, and follow their rate limits. Operators can change endpoints through `SELLBIRD_NOMINATIM_URL` and `SELLBIRD_OVERPASS_URLS`.
- Fresh research uses a bounded same-host request loop with BeautifulSoup and the repository's SSRF-protected HTTP transport. Scrapy's optional `LinkExtractor` structures link discovery; the Scrapy downloader is intentionally not used because its separate request path would bypass the shared network guard.
- Buying-signal classification rejects sources unless their cached status is `ok`; demo and failed-source text cannot be stored as buying signals. Exact source excerpts and URLs are checked before accepted signals are saved.
- Sentence Transformers remains optional for ordinary installs. The workspace `.venv` includes the `local-embeddings` and `research` extras. The route-level index acceptance passed in the venv in 11.66 seconds using the cached `all-MiniLM-L6-v2` model and Hugging Face offline flags; it wrote one normalized 384-dimensional vector. Set `SELLBIRD_EMBEDDING_MODEL_PATH` to a local model directory before using UI indexing in another environment.
- Playwright Python is installed, but the Chromium browser runtime may need separate installation. Playwright is only requested as an optional fallback when static extraction is insufficient.
- Hardware detection identifies NVIDIA GPUs only through `nvidia-smi`; AMD/Intel GPU details, shared memory and current free VRAM are not reported.
- Ollama memory recommendations are conservative starting points. Actual speed and fit depend on quantization, context size, OS and concurrent memory use. The acceptance host completed Qwen3 8B inference but was below the UI's high-profile RAM/VRAM guidance.
- Research tasks are created and tracked in SQLite, but their background coroutine is in-process; if the dashboard stops during a fresh crawl, the task may need to be started again. Local AI tasks retain request identifiers and can be explicitly retried after restart.
- Generated email is a draft only. The new workspace does not send email or verify contact addresses.
- Public website statements are source-attributed but not independently fact-checked. The UI distinguishes imported/provided/extracted/inferred/missing data; a source page itself may be inaccurate.
- `uv.lock` was preserved as an untracked workspace artifact. Optional crawler/embedding dependencies are declared in `pyproject.toml` but are not pinned as extras in that lock.

## Retained legacy source

The Sellbird repository still includes historical Claude/Codex, paid prospecting-provider, and paid email-verifier classes and UI copy for compatibility with the original app. Current active inference routes use the Ollama-only gateway; the active discovery registry exposes only OpenStreetMap and the active email verifier uses DNS/SMTP checks. This source-level retention means a repository-wide keyword scan will find provider names; it is not proof of an active cloud route. The audit script checks active configuration and gateway boundaries, and the evaluator should use `/sales-agent`.
