"""Sellbird's single local inference gateway.

Every active agent request goes to the configured local Ollama server. The
optional `transport` argument is an explicit test seam and is never selected
by configuration or used as a runtime fallback.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time

from sellbird.paths import PROJECT_ROOT
from sellbird.sales_store import SalesStore
from sellbird.local_ai import DEFAULT_MODEL, LocalAIError, OllamaService
from sellbird.state import StateManager
from sellbird.textio import read_user_text
from sellbird.workspace_home import current_home


logger = logging.getLogger("sellbird.brain")
PROMPTS_DIR = PROJECT_ROOT / "prompts"
SKILLS_DIR = PROJECT_ROOT / "skills"
DEFAULT_TIMEOUT_SECONDS = 180
PROVIDER_LABELS = {"ollama": "Ollama (local)"}
BRAIN_STATUS_KEY = "brain_status"


def parse_brain_status(raw: str) -> dict:
    try:
        value = json.loads(raw) if raw else {}
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def active_brain_status(raw: str, provider: str) -> dict:
    value = parse_brain_status(raw)
    return value if value.get("provider") == provider else {}


class BrainUnavailable(Exception):
    """Local Ollama is unavailable; inputs should remain queued for retry."""


def _read_knowledge(folder: str, name: str) -> str:
    own = getattr(current_home(), f"{folder}_dir") / f"{name}.md"
    try:
        return read_user_text(own)
    except FileNotFoundError:
        from sellbird.home import bundled_defaults
        shipped = bundled_defaults()
        if shipped is None or (shipped / folder / f"{name}.md") == own:
            raise
        return read_user_text(shipped / folder / f"{name}.md")


class Brain:
    """Agent-compatible adapter backed only by Ollama on private hardware."""

    def __init__(self, state: StateManager, brain_config=None, transport=None):
        from sellbird.config import BrainConfig

        self.state = state
        self.transport = transport
        self.config = brain_config or BrainConfig()
        self.provider = "ollama"
        self.model = self.config.model or os.environ.get("SELLBIRD_OLLAMA_MODEL", DEFAULT_MODEL)
        if state is not None:
            db_path = state.db_path
        else:
            db_path = current_home().db_path
        self.store = SalesStore(db_path)
        self.ai = OllamaService(self.store, model=self.model)
        self.last_reply_empty = False
        self.unavailable = ""

    @property
    def provider_label(self) -> str:
        return PROVIDER_LABELS[self.provider]

    @property
    def paused_reason(self) -> str:
        return str(getattr(self.transport, "paused_reason", "") or "") if self.transport else self.unavailable

    async def preflight(self) -> str:
        if self.transport is not None:
            return str(getattr(self.transport, "paused_reason", "") or "")
        try:
            await self.store.ensure()
            health = await self.ai.health()
            if health["status"] == "ready":
                if self.unavailable:
                    self.unavailable = ""
                    await self._record_status("ok", "")
                return ""
            self.unavailable = health["error"] or "Local Ollama is unavailable"
        except Exception as exc:
            self.unavailable = f"Could not check local Ollama ({type(exc).__name__})"
        await self._record_status("paused", self.unavailable)
        return self.unavailable

    async def _record_status(self, status: str, reason: str) -> None:
        try:
            await self.state.set_setting(BRAIN_STATUS_KEY, json.dumps({
                "provider": "ollama", "status": status, "reason": reason[:500],
                "since": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }))
        except Exception as exc:
            logger.warning("Could not persist local AI status (%s)", type(exc).__name__)

    async def think(self, prompt: str, session_id: str | None = None,
                    expect_json: bool = False, timeout: float = DEFAULT_TIMEOUT_SECONDS,
                    max_retries: int = 1, agent: str = "", task: str = "") -> str:
        if self.paused_reason:
            return ""
        if self.transport is not None:
            return await self._think_transport(prompt, expect_json=expect_json, timeout=timeout,
                                               agent=agent, task=task)
        try:
            text = await self.ai.generate_text(task or agent or "agent_workflow", prompt)
            if self.unavailable:
                self.unavailable = ""
                await self._record_status("ok", "")
            return text
        except LocalAIError as exc:
            self.unavailable = str(exc)
            await self._record_status("paused", self.unavailable)
            logger.warning("Local Ollama request failed for %s/%s", agent or "agent", task or "workflow")
            return ""

    async def think_json(self, prompt: str, session_id: str | None = None,
                         agent: str = "", task: str = "") -> dict | list | None:
        full_prompt = prompt + "\n\nRespond ONLY with valid JSON. No markdown, no explanation."
        response = await self.think(full_prompt, session_id=session_id, expect_json=True,
                                    agent=agent, task=task)
        self.last_reply_empty = not response
        if not response:
            return None
        parsed = self._extract_json(response)
        if parsed is None:
            logger.error("Local Ollama returned a non-JSON response for %s/%s", agent or "agent", task or "workflow")
        return parsed

    @staticmethod
    def _extract_json(text: str) -> dict | list | None:
        cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip())
        cleaned = re.sub(r"\s*```$", "", cleaned)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass
        for open_ch, close_ch in (("{", "}"), ("[", "]")):
            start, end = cleaned.find(open_ch), cleaned.rfind(close_ch)
            if start >= 0 and end > start:
                try:
                    return json.loads(cleaned[start:end + 1])
                except json.JSONDecodeError:
                    continue
        return None

    async def check_usage(self) -> float:
        """There is no per-token budget for local inference."""
        return 0.0

    async def is_within_budget(self, max_daily_calls: int = 200,
                               max_percent: float | None = None) -> bool:
        """Local inference has no subscription quota; service health gates work."""
        return not bool(self.paused_reason)

    async def _think_transport(self, prompt: str, *, expect_json: bool, timeout: float,
                               agent: str, task: str) -> str:
        try:
            value = await asyncio.wait_for(
                self.transport(prompt, agent=agent, task=task, timeout=timeout, expect_json=expect_json),
                timeout=timeout,
            )
        except Exception as exc:
            logger.warning("Injected test transport failed (%s)", type(exc).__name__)
            return ""
        return str(value or "")

    def load_prompt(self, prompt_name: str, **kwargs) -> str:
        try:
            template = _read_knowledge("prompts", prompt_name)
        except FileNotFoundError:
            logger.warning("Prompt file not found: %s.md", prompt_name)
            return ""
        except OSError as exc:
            logger.error("Could not read prompt file %s.md (%s)", prompt_name, type(exc).__name__)
            return ""
        for key, value in kwargs.items():
            template = template.replace(f"{{{{{key}}}}}", str(value))
        leftover = re.findall(r"\{\{(\w+)\}\}", template)
        if leftover:
            logger.warning("Prompt '%s' has unfilled variables: %s", prompt_name, sorted(set(leftover)))
        return template

    def load_skill(self, skill_name: str) -> str:
        try:
            return _read_knowledge("skills", skill_name)
        except FileNotFoundError:
            logger.warning("Skill file not found: %s.md", skill_name)
            return ""
        except OSError as exc:
            logger.error("Could not read skill file %s.md (%s)", skill_name, type(exc).__name__)
            return ""

    def load_skills_for_agent(self, agent_name: str) -> str:
        skill_map = {
            "scout": ["prospecting_tactics", "lead_qualification", "account_navigation", "signal_playbook", "product_knowledge"],
            "writer": ["product_knowledge", "competitive_intel"],
            "handler": ["objection_handling", "sales_methodology", "offer_strategy", "product_knowledge", "competitive_intel"],
            "sender": ["email_frameworks", "product_knowledge"],
            "linkedin": ["linkedin_outreach", "prospecting_tactics", "product_knowledge"],
        }
        return "\n\n".join(value for name in skill_map.get(agent_name, [])
                            if (value := self.load_skill(name)))
