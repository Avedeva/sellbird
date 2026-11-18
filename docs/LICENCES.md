# Model and software licences

This inventory covers the active local sales-agent stack and the optional research/embedding components. Licence labels were checked against the project or model's upstream licence/model card. The installed dependency versions come from the existing `uv.lock` where present; `uv.lock` is untracked user workspace data and was not rewritten.

## Model and inference runtime

| Component | Version / tag | Licence | Purpose and network behavior |
|---|---:|---|---|
| Qwen3 | `qwen3:4b` (default); Qwen3 family | Apache-2.0 | Open-weight local inference. Download once through Ollama; runtime requests go to the local Ollama service. [Qwen3-4B model card](https://huggingface.co/Qwen/Qwen3-4B), [Qwen3 licensing](https://github.com/QwenLM/Qwen3#license-agreement) |
| Ollama | Host install, version varies by OS | MIT | Local model manager and inference server. [Upstream licence](https://github.com/ollama/ollama/blob/main/LICENSE) |
| `sentence-transformers/all-MiniLM-L6-v2` | Local snapshot; optional | Apache-2.0 | Local text embeddings for cached source indexing. Model weights must be downloaded before offline use. [Model card and licence](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2) |
| Sentence Transformers | `>=3.3,<6` recommended optional range; not installed in implementation environment | Apache-2.0 | Optional embedding library. Loaded from `SELLBIRD_EMBEDDING_MODEL_PATH` with `local_files_only=True`. [Upstream licence](https://github.com/UKPLab/sentence-transformers/blob/master/LICENSE) |

Qwen licence terms attach to the model weights; Ollama's MIT licence is a separate software licence. Model registry download happens only during setup. The app does not use an inference-provider API.

## Runtime and research libraries

| Package | Resolved version in existing lock | Licence | Purpose |
|---|---:|---|---|
| Python | 3.12.1 in the verification environment | PSF-2.0 | Backend runtime |
| FastAPI | 0.163.1 | MIT | HTTP API and dashboard server |
| Uvicorn | 0.54.0 | BSD-3-Clause | ASGI server |
| Pydantic | 2.14.3 | MIT | API and structured model response validation |
| HTTPX | 0.28.1 | BSD-3-Clause | Guarded public research and private Ollama requests |
| aiosqlite | 0.22.1 | MIT | Async access to SQLite |
| BeautifulSoup4 | 4.15.0 | MIT | HTML extraction |
| Playwright | 1.65.2 | Apache-2.0 | Optional JS-rendered public site rendering |
| Scrapy | Optional; not installed in verification environment | BSD-3-Clause | Optional `LinkExtractor`; crawling requests still use Sellbird's guarded HTTP transport. [Upstream licence](https://github.com/scrapy/scrapy/blob/master/LICENSE) |
| SQLite | System/library version varies | Public domain | Local relational database |
| pytest | 8.4.2 in locked dev set | MIT | Test runner |
| pytest-asyncio | 0.26.0 in locked dev set; absent from current environment | Apache-2.0 | Async test runner |

The application itself is licensed under [AGPL-3.0-only](../LICENSE). The inventory focuses on the assignment's major runtime and AI components; `uv.lock` records transitive package versions and hashes for the existing resolved environment.

## Optional public-web services

Public company pages and OpenStreetMap are used only for explicitly requested research/discovery where enabled. Those features require internet access and do not provide LLM inference. Website content remains subject to the site's own terms, robots policy, rate limits and access controls. No paid model, prospect-enrichment or per-token package is part of the active local sales-agent inference path.

## Version provenance

The direct package versions in the table are read from the preserved lockfile. The Python version was read from the local interpreter. Ollama and downloaded model tags are machine-installed and reported by the app; there was no local daemon/model available to verify their installed versions in the implementation environment. Optional Scrapy and Sentence Transformers versions are not claimed as installed.
