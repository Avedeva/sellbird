# Zero-cost and dependency audit

Audit date: 2026-11-18. This is a source/configuration audit of active application paths, not packet capture. The separate local Qwen3 app acceptance passed; see [Final Acceptance Report](docs/FINAL_ACCEPTANCE_REPORT.md). See [Licences](docs/LICENCES.md) for package versions and licence sources.

## Inference path

- Sales workflows call `SalesWorkflows` → `OllamaService` → `httpx.AsyncClient` at `SELLBIRD_OLLAMA_URL` (default `http://127.0.0.1:11434`).
- Endpoint validation rejects non-loopback/non-private hosts, credentials and other paths. `trust_env=False` ignores HTTP(S) proxy environment variables for local inference.
- Existing `sellbird.brain.Brain` is now an Ollama gateway. `sellbird.config.BRAIN_PROVIDERS` allows only `ollama`; the active prospect discovery registry exposes OpenStreetMap only; paid email verification functions are not called by the active verifier.
- When Ollama or its model is unavailable, the app logs a local failure, returns a clear retryable error and saves an AI task for a later user-triggered retry. No cloud fallback exists.
- Inference logs store timestamp, workflow, model tag, endpoint, status, duration and bounded error text. Prompts and prospect contents are not logged.
- Active Ollama calls do not include token billing or a hosted inference dependency. Downloading Ollama/model weights is an installation-time network operation.

## Dependency groups

| Group | Dependencies | Cost/network behavior |
|---|---|---|
| Backend | Python, FastAPI, Uvicorn, Pydantic, HTTPX, aiosqlite, SQLite | Open-source local components; no token costs |
| Local generation | Ollama + Qwen3 model weights | Free software/model under documented licences; download once; generation is local |
| Public research | HTTPX, BeautifulSoup, Playwright; `research` extra provides Scrapy link extraction | Explicit website access may use internet; crawler observes robots/access status and uses guarded requests |
| Local embeddings | `local-embeddings` extra: Sentence Transformers + local `all-MiniLM-L6-v2` snapshot | Extra installs the library; download model once; embedding runs locally with downloads disabled |
| Existing Sellbird features | Existing email/mailbox, DNS/SMTP and public directory/search code | Separate from the new AI acceptance path; the new workspace only drafts email and does not send it |
| Tests | pytest, pytest-asyncio (declared in dev extra and lock) | Test dependencies only; no paid services |

No paid AI-provider package appears in the active `pyproject.toml` runtime dependency list. The old repository still contains historical provider class names, configuration/UI strings and unused verifier implementations. The active provider registry and current inference gateway do not route to them. The original dashboard sections are legacy and are not the assignment's local sales workspace; use `/sales-agent`.

## Repeatable source audit

Run:

```powershell
python scripts/audit_local_ai.py
```

The script checks the configured model endpoint policy, active provider setting, inference gateway, and active prospect discovery registry without sending network requests. A passing static audit is not proof that a model is installed or that the operating system is disconnected from the internet; use the real-model/offline procedure in [Offline Acceptance](docs/OFFLINE_ACCEPTANCE.md).

## Dependency and lockfile note

The current `uv.lock` is an untracked user workspace file and was read but not rewritten. It does not include the newly declared `local-embeddings` or `research` extras, which are installed through pip in the documented setup. The current verification environment does not contain those optional packages.

## Audit limitations

- No packet capture or operating-system firewall trace was available; the code-level route is local, and the opt-in acceptance test intercepts HTTPX requests.
- The local Qwen3 8B Q4_K_M app-level acceptance passed with the HTTPX external-request guard. No operating-system disconnect, packet capture, or firewall trace was performed.
- Legacy files still contain strings and dormant functions for historical providers. Static review must distinguish those retained definitions from active registries and calls; they are listed in `KNOWN_LIMITATIONS.md`.
