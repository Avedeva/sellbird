from __future__ import annotations

from sellbird import hardware


def test_hardware_report_includes_available_ram_and_ollama_disk_space(monkeypatch):
    monkeypatch.setattr(hardware, "_memory_info", lambda: {
        "total_gib": 16.0, "available_gib": 5.5,
    })
    monkeypatch.setattr(hardware, "_gpu", lambda: {
        "available": False, "vendor": "", "model": "", "vram_gib": None,
    })
    monkeypatch.setattr(hardware, "_model_store_free_gib", lambda: 1.2)
    monkeypatch.setattr(hardware.platform, "platform", lambda: "test-os")
    monkeypatch.setattr(hardware.platform, "processor", lambda: "test-cpu")
    monkeypatch.setattr(hardware.os, "cpu_count", lambda: 8)

    result = hardware.detect_hardware()

    assert result["ram_gib"] == 16.0
    assert result["ram_available_gib"] == 5.5
    assert result["model_store_free_gib"] == 1.2
    assert result["gpu"]["available"] is False


def test_recommendations_account_for_available_ram_and_model_disk_space():
    recommendations = hardware.recommend_models({
        "ram_gib": 16.0,
        "ram_available_gib": 5.5,
        "cpu_logical_cores": 8,
        "gpu": {"available": False, "vram_gib": None},
        "model_store_free_gib": 1.2,
    })

    standard, high = recommendations
    assert standard["model"] == "qwen3:1.7b"
    assert standard["estimated_download_gib"] == 1.4
    assert standard["disk_space_available"] is False
    assert "currently available ram is low" in standard["note"].lower()
    assert high["cpu_only_supported"] is True
    assert high["disk_space_available"] is False


def test_high_performance_profile_requires_memory_and_gpu_headroom():
    recommendations = hardware.recommend_models({
        "ram_gib": 64.0,
        "ram_available_gib": 32.0,
        "cpu_logical_cores": 16,
        "gpu": {"available": True, "vram_gib": 24.0},
        "model_store_free_gib": 20.0,
    })

    assert recommendations[1]["model"] == "qwen3:14b"
    assert recommendations[1]["disk_space_available"] is True
    assert recommendations[1]["recommended_free_disk_gib"] > recommendations[1]["estimated_download_gib"]


def test_unknown_memory_or_disk_details_fail_open_as_unknown_not_as_a_fit():
    recommendations = hardware.recommend_models({
        "ram_gib": None,
        "ram_available_gib": None,
        "cpu_logical_cores": 4,
        "gpu": {"available": False, "vram_gib": None},
        "model_store_free_gib": None,
    })

    assert recommendations[0]["model"] == "qwen3:4b"
    assert recommendations[0]["disk_space_available"] is None
    assert recommendations[0]["cpu_only_supported"] is True
