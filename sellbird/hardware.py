"""Best-effort local hardware detection and conservative Ollama guidance."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any


def _memory_info() -> dict[str, float | None]:
    try:
        if os.name == "nt":
            import ctypes

            class MemoryStatus(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

            value = MemoryStatus()
            value.dwLength = ctypes.sizeof(value)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(value)):
                return {
                    "total_gib": round(value.ullTotalPhys / (1024 ** 3), 1),
                    "available_gib": round(value.ullAvailPhys / (1024 ** 3), 1),
                }
        if hasattr(os, "sysconf"):
            page_size = os.sysconf("SC_PAGE_SIZE")
            total = os.sysconf("SC_PHYS_PAGES") * page_size / (1024 ** 3)
            try:
                available = os.sysconf("SC_AVPHYS_PAGES") * page_size / (1024 ** 3)
            except (OSError, ValueError):
                available = None
            return {"total_gib": round(total, 1),
                    "available_gib": round(available, 1) if available is not None else None}
    except (OSError, AttributeError, ValueError):
        pass
    try:
        import psutil
        memory = psutil.virtual_memory()
        return {"total_gib": round(memory.total / (1024 ** 3), 1),
                "available_gib": round(memory.available / (1024 ** 3), 1)}
    except ImportError:
        return {"total_gib": None, "available_gib": None}


def _memory_gib() -> float | None:
    """Compatibility helper for callers that only need installed RAM."""
    return _memory_info()["total_gib"]


def _model_store_free_gib() -> float | None:
    """Report free space on the drive where Ollama stores model blobs."""
    configured = os.environ.get("OLLAMA_MODELS", "").strip()
    model_dir = Path(configured).expanduser() if configured else Path.home() / ".ollama" / "models"
    probe = model_dir
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    try:
        return round(shutil.disk_usage(probe).free / (1024 ** 3), 1)
    except OSError:
        return None


def _gpu() -> dict[str, Any]:
    executable = shutil.which("nvidia-smi")
    if not executable:
        return {"available": False, "vendor": "", "model": "", "vram_gib": None,
                "detection": "nvidia-smi unavailable; other GPU vendors may not be reported"}
    try:
        completed = subprocess.run(
            [executable, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=3, check=False,
        )
        if completed.returncode == 0 and completed.stdout.strip():
            name, _, memory = completed.stdout.strip().splitlines()[0].partition(",")
            return {"available": True, "vendor": "NVIDIA", "model": name.strip(),
                    "vram_gib": round(float(memory.strip()) / 1024, 1), "detection": "nvidia-smi"}
    except (OSError, subprocess.TimeoutExpired, ValueError):
        pass
    return {"available": False, "vendor": "NVIDIA", "model": "", "vram_gib": None,
            "detection": "nvidia-smi did not return GPU details"}


def detect_hardware() -> dict[str, Any]:
    memory = _memory_info()
    return {
        "operating_system": platform.platform(),
        "cpu": platform.processor() or platform.machine() or "Unknown CPU",
        "cpu_logical_cores": os.cpu_count() or 1,
        "ram_gib": memory["total_gib"],
        "ram_available_gib": memory["available_gib"],
        "gpu": _gpu(),
        "model_store_free_gib": _model_store_free_gib(),
    }


def recommend_models(hardware: dict[str, Any]) -> list[dict[str, Any]]:
    ram = hardware.get("ram_gib")
    available_ram = hardware.get("ram_available_gib")
    usable_ram = available_ram if available_ram is not None else ram
    vram = (hardware.get("gpu") or {}).get("vram_gib")
    cores = int(hardware.get("cpu_logical_cores") or 1)
    disk_free = hardware.get("model_store_free_gib")
    standard_model = "qwen3:4b"
    standard_note = "The default Ollama tag uses a quantized build; leave memory headroom for the OS and context."
    if ram is not None and ram < 10:
        standard_model = "qwen3:1.7b"
        standard_note = "Lower-memory choice; close other apps and use a short context window."
    elif usable_ram is not None and usable_ram < 6:
        standard_model = "qwen3:1.7b"
        standard_note = ("Currently available RAM is low; close other apps before loading a model. "
                         "Qwen3 1.7B is the conservative option, not a fit guarantee.")
    elif ram is not None and ram >= 24 and vram and vram >= 12:
        standard_model = "qwen3:8b"
        standard_note = "Higher-capacity option; verify the chosen quantization fits with OS and context memory reserved."
    elif ram is not None and ram >= 32 and (not vram or vram < 8):
        standard_model = "qwen3:8b"
        standard_note = "CPU inference is supported; expect slower generation and leave memory headroom."
    if cores < 4 and standard_model != "qwen3:1.7b":
        standard_note += " The detected CPU has fewer than four logical cores; expect slower generation."

    high_model = ("qwen3:14b" if ram is not None and ram >= 48
                  and (vram is None or vram >= 20)
                  and (usable_ram is None or usable_ram >= 24) else "qwen3:8b")
    model_sizes = {"qwen3:1.7b": 1.4, "qwen3:4b": 2.5,
                   "qwen3:8b": 5.2, "qwen3:14b": 9.3}
    recommendations = [
        {"profile": "standard", "model": standard_model, "quantization": "Q4_K_M recommended",
         "minimum_system_ram_gib": 10 if standard_model == "qwen3:4b" else 6,
         "minimum_gpu_vram_gib": 0, "cpu_only_supported": True,
         "note": standard_note},
        {"profile": "high_performance", "model": high_model, "quantization": "Q4_K_M or a measured compatible quantization",
         "minimum_system_ram_gib": 24 if high_model == "qwen3:8b" else 40,
         "minimum_gpu_vram_gib": 0 if vram is None else (8 if high_model == "qwen3:8b" else 16),
         "cpu_only_supported": True,
         "note": "Recommendation is conservative, not a fit guarantee; reserve memory for OS, runtime and context."},
    ]
    for recommendation in recommendations:
        size = model_sizes[recommendation["model"]]
        recommendation["estimated_download_gib"] = size
        recommendation["recommended_free_disk_gib"] = round(size * 1.2, 1)
        recommendation["model_store_free_gib"] = disk_free
        recommendation["disk_space_available"] = (
            None if disk_free is None else disk_free >= recommendation["recommended_free_disk_gib"]
        )
    return recommendations

