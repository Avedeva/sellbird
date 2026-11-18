# Sellbird Local AI Sales Agent

This checkout extends the Harvey/Sellbird application with a product-scoped sales workspace that runs inference through a local Ollama server. The new experience is available at **`/sales-agent`** in the existing FastAPI dashboard. Its AI workflows have no cloud model fallback.

The original Sellbird outreach pipeline remains in the repository. For this assignment, use the Local AI Sales Agent page; the provider audit documents which legacy integrations are disabled from the active inference and prospecting paths.

<<<<<<< Updated upstream
<p align="center">
  <a href="https://x.com/sellbirdagent"><img alt="Follow @sellbirdagent on X" src="https://img.shields.io/badge/follow-%40sellbirdagent-000000?logo=x&logoColor=white"></a>
  <a href="https://github.com/ethanplusai/sellbird/stargazers"><img alt="GitHub stars" src="https://img.shields.io/github/stars/ethanplusai/sellbird?style=flat&logo=github&label=stars&color=244b62&cacheSeconds=3600"></a>
  <a href="https://github.com/ethanplusai/sellbird/actions/workflows/tests.yml"><img alt="Tests" src="https://github.com/ethanplusai/sellbird/actions/workflows/tests.yml/badge.svg"></a>
  <a href="LICENSE"><img alt="License: AGPL-3.0" src="https://img.shields.io/badge/license-AGPL--3.0-244b62"></a>
  <img alt="Python 3.11+" src="https://img.shields.io/badge/python-3.11%2B-244b62?logo=python&logoColor=white">
  <a href="https://sellbird.ai"><img alt="Hosted at sellbird.ai" src="https://img.shields.io/badge/hosted-sellbird.ai-244b62"></a>
  <a href="https://sellbird.ai/harvey/"><img alt="Formerly Harvey" src="https://img.shields.io/badge/formerly-Harvey-8aa0ad"></a>
</p>

<p align="center">
  <a href="https://trendshift.io/repositories/303676?utm_source=repository-badge&amp;utm_medium=badge&amp;utm_campaign=badge-repository-303676" target="_blank" rel="noopener noreferrer"><img src="https://trendshift.io/api/badge/repositories/303676" alt="ethanplusai%2Fsellbird | Trendshift" width="250" height="55"/></a>
</p>

> **[Harvey is now Sellbird.](https://sellbird.ai/harvey/)** Same project, same history, new name. Already running Harvey? Your setup carries over: see [Upgrading from Harvey](#upgrading-from-harvey).

**New releases, features and the roadmap go out first on X: [follow @sellbirdagent](https://x.com/sellbirdagent).**

**Prefer not to run it yourself? [sellbird.ai](https://sellbird.ai) is the hosted version, with sending domains, inboxes and warmup set up for you. It's in early access.**
=======
Mailbox warmup is a separate, optional deliverability service. Sellbird can read mailbox health from [TrulyInbox](https://trulyinbox.com/?via=sellbird) when connected; its API requires a paid plan.

## What the local agent does

- Stores multiple businesses, products, product-specific ICPs, prospects, cached research, workflow artifacts, conversations and local inference logs in SQLite.
- Generates business profiles, ICPs, research summaries, buying-signal classifications, problem hypotheses, personalized email drafts and reply classifications through local Ollama inference.
- Scores prospects deterministically with configurable product-specific weights and an evidence breakdown.
- Discovers mapped local business categories through free public OpenStreetMap services inside the selected business/product workspace; imports source-attributed facts, deduplicates by OSM object ID, and leaves unavailable contact, size, and revenue fields blank. It also imports and deduplicates CSV prospects and supports manual entry and source-attributed research of public company websites.
- Keeps previously cached research usable offline. Fresh public-web research is disabled by the Offline Mode control.
- Detects OS, CPU, RAM and available NVIDIA GPU details, and recommends conservative model sizes.
>>>>>>> Stashed changes

The demo initializer creates clearly labelled synthetic sample records. It does not create real customer interactions or verified prospect facts.

## Quick start

Requirements: Python 3.11+, Ollama, and enough memory for the selected model. Qwen3 4B is the default; on a lower-memory machine choose Qwen3 1.7B in Ollama and set `SELLBIRD_OLLAMA_MODEL=qwen3:1.7b`.

### Windows PowerShell

```powershell
# From the repository root
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,local-embeddings,research]"

# Install Ollama separately, start it, then fetch the model once.
ollama pull qwen3:4b

# Optional: seed synthetic demonstration data.
python scripts/init_demo_data.py

# Start the existing dashboard.
sellbird dashboard
```

### macOS or Linux

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev,local-embeddings,research]'
ollama pull qwen3:4b
python scripts/init_demo_data.py  # optional synthetic sample data
sellbird dashboard
```

Open the local URL printed by `sellbird dashboard`, sign in if prompted, then select **Local AI Sales Agent**. The default Ollama endpoint is `http://127.0.0.1:11434`; override it with `SELLBIRD_OLLAMA_URL` only for a loopback or private self-hosted Ollama server. Select the model tag with `SELLBIRD_OLLAMA_MODEL`.

Public business discovery is explicitly user-triggered and requires internet access. The default Nominatim and Overpass services are community-operated, rate-limited sources, not an unlimited bulk data feed. Deployments can select replacement HTTPS services with `SELLBIRD_NOMINATIM_URL` and comma-separated `SELLBIRD_OVERPASS_URLS`; attribution remains visible in the prospect workspace.

If the configured model is missing or Ollama is stopped, the UI reports the error and preserves an AI task in the queue. Start Ollama or install the configured model, then use **System & inference → Retry locally**. The app never falls back to a hosted model.

## Local embedding and research extras

The `local-embeddings` extra installs Sentence Transformers for indexing cached research. Download `sentence-transformers/all-MiniLM-L6-v2` while online, set `SELLBIRD_EMBEDDING_MODEL_PATH` to that local model directory, then use **Index locally**. The application loads it with `local_files_only=True`; it does not download model weights during indexing.

Scrapy's link extractor is used by the `research` extra. The bounded crawler always uses the existing SSRF-protected HTTP transport for requests, BeautifulSoup for extraction, and optional Playwright rendering. Public-site research remains subject to robots.txt, website terms, and rate limits.

## Tests and acceptance

```powershell
# Install the project dev extra first; it includes pytest and pytest-asyncio.
python -m pytest -q
```

The real-model acceptance test is opt-in and is not equivalent to mocked-client tests:

<<<<<<< Updated upstream
See [CHANGELOG.md](CHANGELOG.md) for what changed in each release, and [follow @sellbirdagent on X](https://x.com/sellbirdagent) to hear about new ones first.
=======
```powershell
$env:SELLBIRD_RUN_LOCAL_ACCEPTANCE = "1"
$env:SELLBIRD_OFFLINE = "1"
python -m pytest -q tests/acceptance/test_offline_sales_workflow.py
```
>>>>>>> Stashed changes

Run it only after Ollama and the selected model are installed. The test rejects application HTTP requests to public hosts and checks for local inference records. For the final demonstration, additionally disable networking at the operating-system level after installation and model download. Follow [Offline Acceptance](docs/OFFLINE_ACCEPTANCE.md).

## Engineering documents

- [Architecture and data flow](docs/ARCHITECTURE.md)
- [Local Ollama setup](docs/LOCAL_AI_SETUP.md)
- [Hardware and model guidance](docs/HARDWARE_REQUIREMENTS.md)
- [Offline acceptance and demo script](docs/OFFLINE_ACCEPTANCE.md)
- [Implementation audit](docs/IMPLEMENTATION_AUDIT.md)
- [Testing record](docs/TESTING.md)
- [Zero-cost compliance](docs/ZERO_COST_COMPLIANCE.md)
- [Dependency and licence inventory](docs/LICENCES_AND_DEPENDENCIES.md)
- [Repeatable demo script](docs/DEMO_SCRIPT.md)
- [Final acceptance report](docs/FINAL_ACCEPTANCE_REPORT.md)
- [Authenticated OpenAPI JSON](docs/API_OPENAPI.md)
- [Licence audit](docs/LICENCES.md)
- [Cost and dependency audit](COST_AND_DEPENDENCY_AUDIT.md)
- [Known limitations](docs/KNOWN_LIMITATIONS.md)
- [Repository audit and implementation plan](IMPLEMENTATION_PLAN.md)
- [Engineering context](context.md)

The model, libraries, optional dependencies and model-download requirements are listed in the audit. `uv.lock` was already present as an untracked workspace file and is preserved; the exact resolved versions used for this implementation are recorded in the dependency audit.
