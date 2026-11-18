# Local sales-agent architecture

## Integration

The local sales workspace is a module inside the existing Sellbird application, not a separate mock UI. `sellbird/dashboard.py` serves `sellbird/web/sales.html` at `/sales-agent`, uses the existing dashboard authentication boundary for API requests, and includes the `sellbird.sales_routes` FastAPI router. The frontend is the repository's existing HTML, CSS, and JavaScript stack.

## Request paths

```text
Browser /sales-agent
  └─ authenticated /api/sales/* routes
       ├─ sales_store.py ── SQLite (sales_* tables)
       ├─ sales_workflows.py ── OllamaService ── private Ollama endpoint
       ├─ sales_research.py ── public_http_client ── public websites (online only)
       ├─ sales_discovery.py ── Nominatim + Overpass ── user-triggered OSM search (online only)
       ├─ hardware.py ── local OS / CPU / RAM / NVIDIA details
       └─ local_embeddings.py ── configured local Sentence Transformers directory
```

The inference boundary is `sellbird/local_ai.py`. It validates `SELLBIRD_OLLAMA_URL` as loopback or a private self-hosted IP, uses HTTPX with environment proxies disabled, logs workflow/model/status/duration and bounded error text, and validates JSON with Pydantic. No cloud client or fallback is selected when Ollama fails. Failed AI API requests are persisted in `sales_tasks` with their workflow and input identifiers; a user can retry after the local model becomes available.

## Product context and evidence

The independent `sales_*` tables avoid a destructive migration of existing Sellbird data and isolate company, product, and prospect records. Product-generated artifacts, ICPs, signals, scores, and email drafts carry a product key. Workflows verify that a prospect belongs to the selected seller company before using it. Each generation request receives only the selected product and the relevant seller/prospect records.

Research summaries and buying signals must cite URLs from the prospect's stored research, and supporting excerpts are checked against the cached text before saving. Problem statements and emails can reference only known prospect fields and stored source URLs. Scores are deterministic and weighted by editable product scoring weights.

### Tables

| Table | Contents |
|---|---|
| `sales_companies` | Business profile inputs and generated profile JSON |
| `sales_products` | Product details, ICP criteria, and scoring weights |
| `sales_icps` | Generated or edited ICP JSON, one current record per product |
| `sales_prospects` | Imported/manual prospect data and per-field provenance |
| `sales_research_sources` | Cached public-page text, title, URL, fetch time, status, and SHA-256 |
| `sales_signals` | Product-scoped buying signal, evidence, source, confidence, and implication |
| `sales_artifacts` | Research summaries, problem hypotheses, scores, emails, and reply results |
| `sales_conversations` | Reply text, classification, and explicit sample marker |
| `sales_inference_logs` | Content-free local model request log |
| `sales_tasks` | Public research task state and retryable local AI task input/result |
| `sales_settings` | User-selected offline mode and local preferences |
| `sales_embeddings` | Locally generated vectors linked to cached sources |

Foreign keys cascade for company/product/prospect deletion. The schema uses SQLite foreign keys and WAL mode; versioned migrations are separate from the original `state.py` schema.

## Research and offline boundary

Fresh research is an explicit public-site operation and is disabled when `SELLBIRD_OFFLINE=1` or the in-app Offline Mode switch is on. The crawler uses `public_http_client`, which pins public DNS results and blocks restricted addresses, observes robots.txt, applies delays and page limits, and stores extracted text locally. BeautifulSoup extracts page content. Scrapy's `LinkExtractor` is used if Scrapy is installed; the bounded request loop remains on the guarded transport. Playwright is optional for JS-rendered pages and every browser request is fulfilled through the guarded HTTP client.

Cached research analysis, scoring, generated content, SQLite retrieval, and local embeddings have no application-level internet requirement. Sentence Transformers loading sets `local_files_only=True`; embeddings do not trigger downloads.

Product-scoped prospect discovery is separate from research on a supplied website. It geocodes the user's place query through Nominatim, queries a mapped category using Overpass, and imports only facts returned by OSM with source URLs and extracted provenance. The app leaves personal contact, employee, and revenue fields blank. Searches are serialized and rate-limited; HTTP 406/429 causes a 30-second cooldown. Endpoint selection is deployment-configurable via `SELLBIRD_NOMINATIM_URL` and `SELLBIRD_OVERPASS_URLS`. This feature requires internet access and displays OpenStreetMap attribution. The OpenAPI JSON schema is available at authenticated `/api/openapi.json`; interactive `/docs` and `/redoc` remain disabled.

## User data and authentication

`/sales-agent` is a static shell route like the existing dashboard shell. Sales APIs remain behind the existing bearer-token guard. Database location follows `sellbird.workspace_home.current_home()`; do not put real prospect data into committed demo fixtures. The initializer labels synthetic examples and uses reserved `.test`/demo identifiers.

## Main tradeoffs

- The existing product dashboard and SQLite system were reused; a second frontend stack was unnecessary.
- Separate `sales_*` records preserve the legacy schema while making product ownership explicit.
- Public crawling uses the repository's SSRF-safe client instead of Scrapy's independent downloader, so Scrapy only contributes optional URL extraction. This maintains a single guarded network path.
- The new workspace drafts outreach but does not send email; the existing SMTP workflow is outside the local-agent acceptance flow.
- Hardware detection currently reports NVIDIA details through `nvidia-smi`; it does not yet identify AMD/Intel accelerator memory.
