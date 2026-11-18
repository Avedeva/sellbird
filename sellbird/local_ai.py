"""Strict local Ollama inference; there is intentionally no provider fallback."""

from __future__ import annotations

import asyncio
import ipaddress
import json
import os
import time
from urllib.parse import urlsplit
from collections.abc import Callable

import httpx
from pydantic import BaseModel, ValidationError

from sellbird.sales_store import SalesStore


DEFAULT_ENDPOINT = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen3:4b"
DEFAULT_TIMEOUT_SECONDS = 180
TRANSIENT_HTTP_STATUSES = {408, 429, 500, 502, 503, 504}


class LocalAIError(RuntimeError):
    """Local model service or structured response failed."""


def _server_error(response: httpx.Response) -> str:
    """Return a bounded daemon error message without echoing prompts or bodies."""
    try:
        detail = response.json().get("error", "")
    except (ValueError, AttributeError):
        detail = ""
    if not isinstance(detail, str):
        return ""
    detail = " ".join(detail.split())[:240]
    return f": {detail}" if detail else ""


def _validate_endpoint(raw: str) -> str:
    raw = raw.strip().rstrip("/")
    parts = urlsplit(raw)
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
        raise ValueError("SELLBIRD_OLLAMA_URL must be an HTTP(S) local Ollama endpoint without credentials")
    if parts.path not in {"", "/"} or parts.query or parts.fragment:
        raise ValueError("SELLBIRD_OLLAMA_URL must contain only the Ollama server origin")
    host = parts.hostname.lower()
    try:
        address = ipaddress.ip_address(host)
        local = address.is_loopback or address.is_private or address.is_link_local
    except ValueError:
        local = host == "localhost"
    if not local:
        raise ValueError("Ollama endpoint must be loopback or a private self-hosted address")
    return raw


def _endpoint() -> str:
    return _validate_endpoint(os.environ.get("SELLBIRD_OLLAMA_URL", DEFAULT_ENDPOINT))


def _model() -> str:
    model = os.environ.get("SELLBIRD_OLLAMA_MODEL", DEFAULT_MODEL).strip()
    if not model or len(model) > 128 or any(c.isspace() for c in model):
        raise ValueError("SELLBIRD_OLLAMA_MODEL must be a valid local Ollama model tag")
    return model


class OllamaService:
    def __init__(self, store: SalesStore, *, endpoint: str | None = None,
                 model: str | None = None, timeout: float = DEFAULT_TIMEOUT_SECONDS,
                 transport_factory: Callable[[], httpx.AsyncBaseTransport] | None = None):
        self.store = store
        self.endpoint = _validate_endpoint(endpoint) if endpoint else _endpoint()
        self.model = model or _model()
        self.timeout = timeout
        self.transport_factory = transport_factory

    def _client(self, timeout: float | None = None) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=timeout or self.timeout, trust_env=False,
                                 transport=self.transport_factory() if self.transport_factory else None)

    async def _post_chat(self, payload: dict) -> httpx.Response:
        for attempt in range(2):
            try:
                async with self._client() as client:
                    response = await client.post(f"{self.endpoint}/api/chat", json=payload)
            except httpx.TimeoutException as exc:
                raise LocalAIError(f"Local Ollama request timed out after {self.timeout:g} seconds") from exc
            except httpx.HTTPError as exc:
                if attempt:
                    raise LocalAIError("Could not connect to local Ollama after one retry; no cloud fallback was attempted") from exc
                await asyncio.sleep(0.25)
                continue
            if response.status_code in TRANSIENT_HTTP_STATUSES and attempt == 0:
                await asyncio.sleep(0.25)
                continue
            return response
        raise LocalAIError("Could not connect to local Ollama after one retry; no cloud fallback was attempted")

    async def tags(self) -> list[str]:
        try:
            async with self._client(min(self.timeout, 8)) as client:
                response = await client.get(f"{self.endpoint}/api/tags")
                response.raise_for_status()
                payload = response.json()
            return [str(row.get("name", "")) for row in payload.get("models", []) if row.get("name")]
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise LocalAIError("Ollama is not reachable at the configured local endpoint") from exc

    async def health(self) -> dict:
        try:
            models = await self.tags()
            available = self.model in models or any(name.split(":", 1)[0] == self.model.split(":", 1)[0]
                                                     and self.model.endswith(":latest") for name in models)
            return {"status": "ready" if available else "model_missing", "ollama_reachable": True,
                    "configured_model": self.model, "model_available": available,
                    "offline_mode": _offline_mode(), "error": "" if available else f"Model {self.model} is not installed"}
        except LocalAIError as exc:
            return {"status": "unavailable", "ollama_reachable": False,
                    "configured_model": self.model, "model_available": False,
                    "offline_mode": _offline_mode(), "error": str(exc)}

    async def generate_json(self, workflow: str, prompt: str, response_model: type[BaseModel]) -> BaseModel:
        started = time.monotonic()
        status, error, result = "error", "", None
        try:
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "You are a careful sales research assistant. Use only supplied facts. "
                     "Never invent facts, sources, buying signals, numbers, personal details or claims. "
                     "Return only valid JSON conforming to the supplied schema. Mark unknown information explicitly."},
                    {"role": "user", "content": prompt},
                ],
                "format": response_model.model_json_schema(),
                "stream": False,
                "options": {"temperature": 0.2},
            }
            response = await self._post_chat(payload)
            if response.status_code >= 400:
                if response.status_code == 404:
                    raise LocalAIError(f"Ollama model '{self.model}' is unavailable; install it locally and retry")
                raise LocalAIError(f"Ollama returned HTTP {response.status_code}{_server_error(response)}")
            try:
                envelope = response.json()
                content = envelope["message"]["content"]
                result = response_model.model_validate_json(content)
            except (ValueError, KeyError, TypeError, ValidationError) as exc:
                raise LocalAIError("Ollama returned malformed or schema-invalid JSON") from exc
            status = "ok"
            return result
        except LocalAIError as exc:
            error = str(exc)
            raise
        finally:
            duration = round((time.monotonic() - started) * 1000)
            await self.store.log_inference(workflow, self.model, self.endpoint, status, duration, error)

    async def generate_text(self, workflow: str, prompt: str) -> str:
        started = time.monotonic()
        status, error = "error", ""
        try:
            payload = {"model": self.model,
                       "messages": [{"role": "user", "content": prompt}],
                       "stream": False, "options": {"temperature": 0.2}}
            response = await self._post_chat(payload)
            if response.status_code == 404:
                raise LocalAIError(f"Ollama model '{self.model}' is unavailable; install it locally and retry")
            if response.status_code >= 400:
                raise LocalAIError(f"Ollama returned HTTP {response.status_code}{_server_error(response)}")
            try:
                content = response.json()["message"]["content"]
            except (ValueError, KeyError, TypeError) as exc:
                raise LocalAIError("Ollama returned a malformed chat response") from exc
            if not isinstance(content, str) or not content.strip():
                raise LocalAIError("Ollama returned an empty response")
            status = "ok"
            return content
        except LocalAIError as exc:
            error = str(exc)
            raise
        finally:
            await self.store.log_inference(workflow, self.model, self.endpoint, status,
                                           round((time.monotonic() - started) * 1000), error)


def _offline_mode() -> bool:
    return os.environ.get("SELLBIRD_OFFLINE", "").strip().lower() in {"1", "true", "yes", "on"}

