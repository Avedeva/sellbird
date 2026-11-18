"""Static checks for the active local-AI and free-discovery boundaries.

This audit does not open sockets, check whether Ollama is running, or replace
the real-model and physically offline acceptance procedures.
"""

from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    import sellbird.config as config
    from sellbird.collectors.discover import PROVIDERS
    from sellbird.local_ai import _validate_endpoint

    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    runtime_dependencies = [str(item).split("[", 1)[0].split("<", 1)[0].split(">", 1)[0]
                           .split("=", 1)[0].strip().lower()
                           for item in project["project"].get("dependencies", [])]
    paid_packages = {"anthropic", "openai", "google-generativeai", "google-genai",
                     "openrouter", "litellm", "cohere", "mistralai"}
    brain = (ROOT / "sellbird" / "brain.py").read_text(encoding="utf-8").lower()
    local_ai = (ROOT / "sellbird" / "local_ai.py").read_text(encoding="utf-8").lower()
    active_inference_text = brain + "\n" + local_ai

    rejects_public_host = False
    try:
        _validate_endpoint("https://api.example.com")
    except ValueError:
        rejects_public_host = True

    checks = {
        "configured_brain_provider_is_ollama_only": tuple(config.BRAIN_PROVIDERS) == ("ollama",),
        "brain_routes_through_local_ollama": "ollamaservice" in brain and "generate_text" in brain,
        "local_gateway_uses_no_paid_provider_client": not any(
            token in active_inference_text for token in
            ("anthropic", "claude_runtime", "codex", "openai.com", "openrouter", "gemini")
        ),
        "public_ollama_endpoint_rejected": rejects_public_host,
        "ollama_client_disables_environment_proxies": "trust_env=false" in local_ai,
        "runtime_has_no_paid_llm_packages": not (paid_packages & set(runtime_dependencies)),
        "active_discovery_is_osm_only": set(PROVIDERS) == {"osm"},
    }
    result = {
        "audit": "active local inference source/config audit",
        "network_requests_made": False,
        "active_discovery_providers": sorted(PROVIDERS),
        "runtime_dependency_names": runtime_dependencies,
        "checks": checks,
        "legacy_provider_code_note": "Historical provider classes and UI strings remain in the repository; this audit checks active routing only.",
        "real_ollama_required_for_inference_evidence": True,
    }
    print(json.dumps(result, indent=2))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
