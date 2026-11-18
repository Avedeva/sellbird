# Hardware requirements and model selection

## Detection

`GET /api/system/hardware` reports the operating system, CPU name, logical core count, total and currently available RAM, free space on the Ollama model-store drive, and available NVIDIA GPU/VRAM when `nvidia-smi` works. The UI pairs those values with standard and high-performance suggestions. CPU-only execution is supported by Ollama.

GPU identification is best-effort. Current code queries NVIDIA through `nvidia-smi`; AMD and Intel GPU models/VRAM are not reported, and some virtualized systems may hide RAM or GPU details. A missing GPU report does not disable CPU inference.

## Recommendations in this build

| Hardware profile | Suggested model | Guidance |
|---|---|---|
| Standard laptop with under 10 GiB RAM | `qwen3:1.7b` | Lower-memory option; keep prompts and context short |
| Standard laptop with at least 10 GiB RAM | `qwen3:4b` | Default; allow OS/runtime/context headroom |
| Higher-capacity CPU machine (about 32 GiB+ RAM) | `qwen3:8b` | CPU-only works but can be slow |
| Strong GPU and 48 GiB+ system RAM | `qwen3:14b` | Recommendation requires substantial memory; validate actual quantization and available VRAM |

Ollama's published file sizes are approximately 1.4 GB, 2.5 GB, 5.2 GB and 9.3 GB for Qwen3 1.7B, 4B, 8B and 14B respectively. The app reports an approximate download size, recommends 20% free disk headroom, and flags when the detected model-store drive may be short on space. Model file size is not a runtime fit guarantee. Runtime memory also depends on quantization, context length, concurrency, backend and operating system. The app cannot inspect all memory use or every GPU vendor's acceleration stack.

The standard profile recommends Qwen3 4B when installed RAM and currently available memory allow; it falls back to Qwen3 1.7B when memory is low. The high-performance profile recommends 8B by default and 14B only when reported system RAM, currently available memory and GPU details justify it. Recommendations include Q4_K_M guidance and CPU core count, but they remain estimates; test the chosen Ollama tag before importing real prospect data.

### Detected implementation host

The acceptance host reported Windows 11, 16 logical CPU cores, 15.8 GiB installed RAM, about 4.3 GiB available RAM before model loading, an NVIDIA GeForce RTX 3050 Laptop GPU with 6.0 GiB VRAM, and about 199.5 GiB free on the Ollama model-store drive. Its conservative standard recommendation is Qwen3 1.7B because currently available memory was below 6 GiB. The installed and exercised tag was `qwen3:8b` (Q4_K_M, about 5.2 GB); this is above the UI's stated 24 GiB system RAM/8 GiB VRAM high-profile guidance. It loaded and completed a simple local inference, but that observation is not a general performance or fit guarantee.

## CPU-only use

Ollama can run on CPU. Expect lower throughput, especially for larger models and long contexts. Start with Qwen3 1.7B or 4B, close memory-heavy applications, and avoid running concurrent generation jobs. A dedicated GPU is not required by the application.

## Change the model

Install the chosen tag in Ollama, then set the exact tag before starting Sellbird:

```powershell
ollama pull qwen3:1.7b
$env:SELLBIRD_OLLAMA_MODEL = "qwen3:1.7b"
sellbird dashboard
```

The **System & inference** panel shows which model tag is configured and which model tags Ollama reports as installed. A missing model produces a clear local error; AI tasks remain queued for retry.
