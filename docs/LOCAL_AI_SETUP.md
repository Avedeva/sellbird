# Local Ollama setup

## 1. Install Ollama and the model

Install Ollama for your operating system from [ollama.com/download](https://ollama.com/download), start its local service, then fetch the default model once:

```powershell
ollama pull qwen3:4b
ollama list
```

Ollama's registry currently lists approximate package sizes of 2.5 GB for `qwen3:4b`, 1.4 GB for `qwen3:1.7b`, 5.2 GB for `qwen3:8b`, and 9.3 GB for `qwen3:14b`. These are download sizes, not total runtime RAM requirements. The exact model license is Apache-2.0; see [Qwen's official Qwen3-4B model card](https://huggingface.co/Qwen/Qwen3-4B) and [Qwen3 license statement](https://github.com/QwenLM/Qwen3#license-agreement).

For a lower-memory machine, install and select the smaller model:

```powershell
ollama pull qwen3:1.7b
$env:SELLBIRD_OLLAMA_MODEL = "qwen3:1.7b"
```

The default endpoint is `http://127.0.0.1:11434`. To use a self-hosted Ollama machine on a private network, set `SELLBIRD_OLLAMA_URL` to its private IP address. Public endpoints and endpoints with credentials are rejected. Proxy environment variables are ignored for Ollama requests.

## 2. Install and start Sellbird

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,local-embeddings,research]"
sellbird dashboard
```

The local workspace is `http://127.0.0.1:5555/sales-agent` unless the dashboard reports a different port. Sales API routes use the existing dashboard authentication. `SELLBIRD_OLLAMA_MODEL` and `SELLBIRD_OLLAMA_URL` can be set in the process environment before starting the dashboard.

Check the **System & inference** panel for the local model tag, installed models, Ollama status, actual hardware report, and inference logs. Inference errors do not cause a cloud request. When Ollama is unavailable, the API returns a retryable error and persists the task; after restoring the local service, use **Retry locally** in the queued-workflows panel.

## 3. Local embeddings

Embeddings are an optional local indexing feature; core scoring and workflows do not require them. The selected model is `sentence-transformers/all-MiniLM-L6-v2`, whose model card states Apache-2.0. Download it while online and configure the resulting local directory:

```powershell
python -m pip install -e ".[local-embeddings]"
python -m pip install "huggingface_hub>=0.20"
python -c "from huggingface_hub import snapshot_download; snapshot_download('sentence-transformers/all-MiniLM-L6-v2', local_dir='models/all-MiniLM-L6-v2')"
$env:SELLBIRD_EMBEDDING_MODEL_PATH = (Resolve-Path "models/all-MiniLM-L6-v2").Path
```

The app only loads a pre-downloaded path with `local_files_only=True`. Set `HF_HUB_OFFLINE=1` during local indexing if you want the library itself to refuse Hub connections too. The optional embedding package is not in the small default install.

## 4. Optional public research tools

The documented assignment setup installs Scrapy through the `research` extra for structured link extraction. Install the Playwright browser runtime only if JS rendering is needed:

```powershell
python -m pip install "playwright>=1.40,<2"
playwright install chromium
```

Fresh research requires internet access and is controlled separately from local inference. The crawler follows robots.txt and uses the repository's guarded transport for every request. An offline acceptance run should use data already cached before disconnecting.

## Useful environment variables

| Variable | Default | Meaning |
|---|---|---|
| `SELLBIRD_OLLAMA_URL` | `http://127.0.0.1:11434` | Loopback or private self-hosted Ollama origin |
| `SELLBIRD_OLLAMA_MODEL` | `qwen3:4b` | Installed Ollama model tag |
| `SELLBIRD_OFFLINE` | unset | Set to `1` to disable fresh web research and public OSM discovery |
| `SELLBIRD_EMBEDDING_MODEL_PATH` | unset | Existing local Sentence Transformers model folder |
| `SELLBIRD_NOMINATIM_URL` | public Nominatim endpoint | Optional replacement HTTPS geocoder endpoint |
| `SELLBIRD_OVERPASS_URLS` | two public Overpass endpoints | Optional comma-separated replacement HTTPS endpoints |

The app does not start Ollama, download LLM weights, or download embedding weights for you. Complete those installation steps while internet access is available, then the inference workflows can run locally.

Public prospect discovery in the Prospects workspace is a separate, user-started online operation. It uses OpenStreetMap category data, honors service cooldowns, and shows attribution. It is disabled in offline mode; configure replacement services only when authorized to use them.
