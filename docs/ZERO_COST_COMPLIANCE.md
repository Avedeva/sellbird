# Zero-cost compliance

## Active sales-agent paths

- Model inference routes only to the configured local Ollama service. There is no hosted-model fallback and no token-metered inference API in the runtime dependency list.
- The active discovery registry exposes OpenStreetMap only. Nominatim geocoding and Overpass lookup are public community services and require internet access; they are rate-limited and intended for interactive, modest-volume use, not bulk enumeration.
- Manual prospect entry, CSV import, SQLite persistence, deterministic scoring, cached analysis, and local embedding support do not require a paid API.
- Email generation creates a local draft. The new workspace does not send it or use a paid email-verification provider.
- Optional Sentence Transformers embeddings use a configured local model directory with downloads disabled. Installing the library and obtaining model weights are optional setup steps.

## Honest cost boundaries

The included software paths do not require a subscription, API key, card, or per-request fee. This does not make the user's computer, electricity, internet access, or model download bandwidth free. Fresh public discovery and research need a network connection. Public OSM services can reject, delay, or limit requests, and users must not treat them as unlimited infrastructure.

The separate legacy mailbox-warmup integration is not part of the sales-agent workflow and may require a paid third-party plan. Historical paid-provider source remains in the repository for compatibility; the active local-agent routes do not invoke it.

## OSM service etiquette

Searches originate from an explicit user action, are serialized, identify the client, and cache geocoding results. Nominatim requests are spaced by at least 1.1 seconds; Overpass calls are serialized and wait at least 30 seconds before another request after HTTP 406 or 429. Provider endpoints can be changed at deployment time without a software update:

```powershell
$env:SELLBIRD_NOMINATIM_URL = "https://your-nominatim.example/search"
$env:SELLBIRD_OVERPASS_URLS = "https://overpass.example/api/interpreter,https://backup.example/api/interpreter"
```

Configured endpoints must use HTTPS and omit credentials, query strings, and fragments. Keep OSM attribution visible in any deployment and follow the [Nominatim usage policy](https://operations.osmfoundation.org/policies/nominatim/), [Overpass API usage guidance](https://wiki.openstreetmap.org/wiki/Overpass_API#Public_Overpass_API_instances), and [OpenStreetMap attribution requirements](https://www.openstreetmap.org/copyright).

## Verification boundary

`python scripts/audit_local_ai.py` checks active source/configuration and makes no network request. It is not packet capture. The app-level request guards and tests provide code-level evidence; deployment-level network proof requires a real model run with OS firewall/network monitoring, documented in [Offline Acceptance](OFFLINE_ACCEPTANCE.md).
