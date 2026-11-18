"""The active Brain and configuration are local-Ollama only."""

import pytest
import yaml
from pydantic import ValidationError

from sellbird.brain import Brain
from sellbird.config import BRAIN_PROVIDERS, BrainConfig, ConfigError, load_brain_config
from sellbird.state import StateManager


BASE = {
    "persona": {"name": "H", "company": "A", "role": "B", "email": "e", "linkedin": "", "tone": "t"},
    "product": {"name": "P", "description": "D", "pricing": "$1", "key_benefits": [],
                "objection_responses": {}},
    "icp": {"industries": [], "company_size": "", "titles": [], "geography": []},
}


def test_ollama_is_the_only_configured_brain_provider():
    assert BRAIN_PROVIDERS == ("ollama",)
    assert BrainConfig().provider == "ollama"
    assert BrainConfig().model == ""


@pytest.mark.parametrize("provider", ["claude", "codex", "openai", "gemini", "openrouter"])
def test_paid_or_cloud_providers_are_rejected(provider):
    with pytest.raises(ValidationError, match="not a supported brain provider"):
        BrainConfig(provider=provider)


def test_ollama_config_normalizes_values():
    config = BrainConfig(provider=" OLLAMA ", model="qwen3:4b", reasoning_effort="HIGH")
    assert (config.provider, config.model, config.reasoning_effort) == ("ollama", "qwen3:4b", "high")


def test_config_file_rejects_a_legacy_provider(tmp_path):
    path = tmp_path / "sellbird.yaml"
    path.write_text(yaml.safe_dump({"brain": {"provider": "claude"}}), encoding="utf-8")
    with pytest.raises(ConfigError):
        load_brain_config(str(path))


def test_brain_adapter_is_always_local_ollama(tmp_path):
    brain = Brain(StateManager(str(tmp_path / "state.sqlite3")))
    assert brain.provider == "ollama"
    assert brain.provider_label == "Ollama (local)"
