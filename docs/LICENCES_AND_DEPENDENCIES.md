# Licences and dependencies

The application is distributed as AGPL-3.0-only. Assignment-specific AI and runtime components are summarized here; the existing [licence audit](LICENCES.md) contains the broader package-version table. `uv.lock` is a preserved untracked workspace file, so the resolved versions noted there are not presented as a committed reproducible lock.

| Component | Use | Licence / terms | Acquisition and runtime behavior |
|---|---|---|---|
| Sellbird application | Dashboard and sales-agent source | AGPL-3.0-only; see repository `LICENSE` | Locally installed. |
| Ollama | Local model runtime | MIT; [upstream licence](https://github.com/ollama/ollama/blob/main/LICENSE) | Install separately; model download occurs during setup; inference goes to local Ollama. |
| Qwen3 `qwen3:4b` default | Local model weights | Qwen3 project states Apache-2.0 for open-weight models; [upstream model/licensing information](https://github.com/QwenLM/Qwen3) | Download once using Ollama; model weights are not bundled. Check the selected model card and licence before redistribution/use. |
| Qwen3 `qwen3:8b` used for local inference evidence | Local model weights; observed quantization `Q4_K_M` | Apache License 2.0, confirmed by `ollama show qwen3:8b`; [upstream model/licensing information](https://github.com/QwenLM/Qwen3) | Installed locally (Ollama reports about 5.2 GB). The tag is an acceptance-host choice, not the application's default. |
| Sentence Transformers | Local cached-research embeddings | Apache-2.0; [upstream licence](https://github.com/UKPLab/sentence-transformers/blob/master/LICENSE) | Installed with the `local-embeddings` extra for the documented setup; embedding weights are downloaded separately. Other sales workflows do not depend on it. |
| `sentence-transformers/all-MiniLM-L6-v2` | Optional local embedding weights | Apache-2.0; [model card](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2) | Download once while online, then load from a local directory with `local_files_only=True`. |
| FastAPI, Uvicorn, Pydantic, HTTPX, aiosqlite | API, server, validation, networking, persistence | Their respective permissive project licences; exact direct/runtime versions are listed in `LICENCES.md` and hashes in the preserved lockfile. | Installed as Python dependencies. |
| OpenStreetMap data | User-triggered prospect discovery | Open Database License (ODbL); [attribution and licence](https://www.openstreetmap.org/copyright) | Public service use requires network access and visible attribution. |
| Nominatim and Overpass public services | Geocoding and OSM search | Service policies and rate limits apply; [Nominatim policy](https://operations.osmfoundation.org/policies/nominatim/) and [Overpass guidance](https://wiki.openstreetmap.org/wiki/Overpass_API#Public_Overpass_API_instances) | No account/API key for the configured public endpoints; not an unlimited service. |

## Dependency boundary

The app does not add hosted-model SDKs or paid prospecting SDKs to the active local-agent runtime. `sentence-transformers` and Scrapy are install extras (`local-embeddings` and `research`) included in the documented assignment setup. Playwright and BeautifulSoup are existing runtime dependencies; Playwright's browser binary may require a separate install. See [Cost and Dependency Audit](../COST_AND_DEPENDENCY_AUDIT.md) for the package and active-provider review.

This inventory is a practical engineering summary, not legal advice. Recheck the selected model's exact licence and each dependency's current licence before redistributing binaries or model weights.
