"""Tests for usage tracking: schema, pricing, result parsing, reconciliation, quota."""

import os
import tempfile

import pytest
import pytest_asyncio

from sellbird.brain import Brain
from sellbird.state import StateManager


@pytest_asyncio.fixture
async def state():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        sm = StateManager(db_path)
        await sm.init_db()
        yield sm


# ── usage_events table + aggregations ──


@pytest.mark.asyncio
async def test_record_usage_event_and_totals(state):
    ok = await state.record_usage_event(
        agent="writer", task="write_sequence", session_id="sess-1",
        model="claude-opus-4-8", input_tokens=100, output_tokens=500,
        cache_read_tokens=2000, cache_creation_tokens=300,
        cost_usd=0.05, duration_ms=1200, num_turns=1,
    )
    assert ok

    totals = await state.usage_totals()
    assert totals["today"]["calls"] == 1
    assert totals["today"]["output_tokens"] == 500
    assert totals["today"]["cost_usd"] == pytest.approx(0.05)
    assert totals["week"]["input_tokens"] == 100


@pytest.mark.asyncio
async def test_usage_by_agent_groups_and_counts_sessions(state):
    # Two model-rows from the SAME call (same session) → one "call"
    await state.record_usage_event(
        agent="scout", session_id="sess-a", model="claude-opus-4-8",
        output_tokens=10, cost_usd=0.01,
    )
    await state.record_usage_event(
        agent="scout", session_id="sess-a", model="claude-haiku-4-5",
        output_tokens=5, cost_usd=0.001,
    )
    await state.record_usage_event(
        agent="handler", session_id="sess-b", model="claude-opus-4-8",
        output_tokens=20, cost_usd=0.02,
    )

    rows = await state.usage_by_agent(days=7)
    by_name = {r["agent"]: r for r in rows}
    assert by_name["scout"]["calls"] == 1
    assert by_name["scout"]["output_tokens"] == 15
    assert by_name["handler"]["calls"] == 1


@pytest.mark.asyncio
async def test_request_key_dedup(state):
    first = await state.record_usage_event(
        request_key="msg_1:req_1", model="claude-opus-4-8",
        output_tokens=50, source="transcript",
    )
    second = await state.record_usage_event(
        request_key="msg_1:req_1", model="claude-opus-4-8",
        output_tokens=50, source="transcript",
    )
    assert first is True
    assert second is False  # unique index makes reconciliation idempotent

    totals = await state.usage_totals()
    assert totals["today"]["output_tokens"] == 50


# ── Local Brain JSON handling and usage model ──


@pytest.mark.parametrize("raw, expected", [
    ('{"intent":"interested"}', {"intent": "interested"}),
    ('```json\n{"intent":"unsubscribe"}\n```', {"intent": "unsubscribe"}),
    ("plain text", None),
])
def test_brain_extracts_json_without_provider_envelopes(raw, expected):
    assert Brain._extract_json(raw) == expected


@pytest.mark.asyncio
async def test_brain_usage_is_local_and_unmetered(state):
    brain = Brain(state)
    assert brain.provider == "ollama"
    assert await brain.check_usage() == 0.0
    assert await brain.is_within_budget()


@pytest.mark.asyncio
async def test_usage_is_sellbird_only(state):
    """Sanity: the ledger only contains rows Sellbird's Brain wrote. There is
    no transcript scan to pull in other projects' Claude sessions."""
    import sellbird.usage as usage_mod
    assert not hasattr(usage_mod, "reconcile_transcripts")
    assert not hasattr(usage_mod, "parse_transcript_events")
