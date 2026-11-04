"""Gated remote comparison arm: an OpenAI-compatible ``/chat/completions`` call.

This is not the primary experiment.  It exists so a reviewer can see how the
harness treats a hosted comparison without pretending that a hosted model was run
locally.  The rules are the same as for every arm:

* both the ``remote_api`` and ``network`` gates must be open, checked inside
  ``load()`` before anything is sent (default posture: closed);
* no API key means ``AdapterUnavailable``, never a silent empty call;
* no retries by default;
* token usage is recorded only when the response actually reports it, and an
  estimated cost is recorded only when a price is configured -- otherwise the
  field is ``None`` ("not measured"), never ``0``;
* the only I/O dependency is the standard library (``urllib``), so no extra
  package is needed and the offline test suite can inject a fake transport.

Tests never touch the network: they exercise gate refusal and request shaping
with a monkeypatched ``transport`` callable.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Mapping

from .base import (
    AdapterDescriptor,
    AdapterError,
    AdapterResponse,
    AdapterUnavailable,
    ExtractionRequest,
    ModelAdapter,
)

DEFAULT_API_KEY_ENV = "MEDRADAR_LOCAL_LLM_REMOTE_API_KEY"
CHAT_COMPLETIONS_PATH = "/chat/completions"

# (url, headers, body_bytes, timeout_seconds) -> decoded JSON mapping
Transport = Callable[[str, Mapping[str, str], bytes, float], Mapping[str, Any]]


def _default_transport(
    url: str, headers: Mapping[str, str], body: bytes, timeout: float
) -> Mapping[str, Any]:
    """One ``urllib`` POST, no retries.  Only called when the gates are open."""
    request = urllib.request.Request(url, data=body, headers=dict(headers), method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 (explicit URL)
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
        except Exception:  # pragma: no cover - defensive
            pass
        raise AdapterError(f"remote API HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise AdapterError(f"remote API connection failed: {exc.reason}") from exc
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AdapterError(f"remote API returned non-JSON body: {exc}") from exc
    if not isinstance(decoded, Mapping):
        raise AdapterError("remote API returned a JSON value that is not an object")
    return decoded


class RemoteOpenAIAdapter(ModelAdapter):
    """An OpenAI-compatible chat-completions backend, default-closed and key-gated."""

    def __init__(
        self,
        descriptor: AdapterDescriptor,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        api_key_env: str = DEFAULT_API_KEY_ENV,
        transport: Transport | None = None,
        timeout_s: float = 60.0,
        price_per_1k_tokens_in_usd: float | None = None,
        price_per_1k_tokens_out_usd: float | None = None,
        max_retries: int = 0,
        seed: int = 0,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        if descriptor.backend != "openai_compat":
            raise ValueError("RemoteOpenAIAdapter requires a descriptor with backend='openai_compat'")
        self._descriptor = descriptor
        self._base_url = _clean(base_url)
        self._api_key = _clean(api_key)
        self._api_key_env = api_key_env
        self._transport: Transport = transport or _default_transport
        self._transport_injected = transport is not None
        self._timeout_s = float(timeout_s)
        if price_per_1k_tokens_in_usd is not None and price_per_1k_tokens_in_usd < 0:
            raise ValueError("price_per_1k_tokens_in_usd must be non-negative")
        if price_per_1k_tokens_out_usd is not None and price_per_1k_tokens_out_usd < 0:
            raise ValueError("price_per_1k_tokens_out_usd must be non-negative")
        self._price_in = price_per_1k_tokens_in_usd
        self._price_out = price_per_1k_tokens_out_usd
        if max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        self._max_retries = int(max_retries)
        self._seed = int(seed)
        self._environ = dict(os.environ if environ is None else environ)
        self._loaded = False

    # ------------------------------------------------------------- protocol
    @property
    def descriptor(self) -> AdapterDescriptor:
        return self._descriptor

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def transport_injected(self) -> bool:
        return self._transport_injected

    def describe(self) -> dict[str, Any]:
        payload = super().describe()
        payload.update(
            {
                "base_url_configured": bool(self._base_url),
                "api_key_configured": bool(self._api_key or self._environ.get(self._api_key_env)),
                "api_key_env": self._api_key_env,
                "priced": self._price_in is not None or self._price_out is not None,
                "max_retries": self._max_retries,
                "decoding": {"temperature": 0, "seed": self._seed},
            }
        )
        return payload

    # ------------------------------------------------------------- loading
    def load(self) -> None:
        if self._loaded:
            return
        # Gates first: remote_api and network (base.check_gate requires both for a
        # network adapter).  A closed gate raises AdapterGateClosed.
        self.check_gate()
        key = self._api_key or _clean(self._environ.get(self._api_key_env))
        if not key:
            raise AdapterUnavailable(
                f"{self._descriptor.adapter_id}: no API key configured "
                f"(set {self._api_key_env} or pass api_key=); refusing to call without one"
            )
        if not self._base_url:
            raise AdapterUnavailable(
                f"{self._descriptor.adapter_id}: no base_url configured; refusing to guess an endpoint"
            )
        if not self._descriptor.model_id:
            raise AdapterUnavailable(
                f"{self._descriptor.adapter_id}: no model_id configured; refusing to guess a model name"
            )
        self._api_key = key
        self._loaded = True

    def unload(self) -> None:
        self._loaded = False

    # ------------------------------------------------------------- shaping
    @property
    def endpoint_url(self) -> str:
        if not self._base_url:  # pragma: no cover - load() refuses first
            raise AdapterUnavailable(f"{self._descriptor.adapter_id}: no base_url configured")
        return self._base_url.rstrip("/") + CHAT_COMPLETIONS_PATH

    def request_headers(self) -> dict[str, str]:
        if not self._api_key:  # pragma: no cover - load() refuses first
            raise AdapterUnavailable(f"{self._descriptor.adapter_id}: no API key loaded")
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "medradar-local-llm-research/0.1 (offline evaluation harness)",
        }

    def build_payload(self, request: ExtractionRequest) -> dict[str, Any]:
        if request.prompt is None:
            raise AdapterUnavailable(
                f"{self._descriptor.adapter_id}: this adapter needs request.prompt (built by prompting.py)"
            )
        return {
            "model": self._descriptor.model_id,
            "messages": [
                {"role": "system", "content": request.prompt.system},
                {"role": "user", "content": request.prompt.user},
            ],
            "temperature": 0,  # greedy: matches the local arm's declared decoding
            "max_tokens": self._descriptor.max_new_tokens,
            "seed": self._seed,
            "stream": False,
        }

    # ------------------------------------------------------------- inference
    def generate(self, request: ExtractionRequest) -> AdapterResponse:
        if not self._loaded:
            raise AdapterUnavailable(
                f"{self._descriptor.adapter_id}: generate() called before load(); refusing implicit load"
            )
        payload = self.build_payload(request)
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        url = self.endpoint_url
        headers = self.request_headers()

        started = time.perf_counter()
        decoded: Mapping[str, Any] | None = None
        attempts = 0
        last_error: AdapterError | None = None
        for attempt in range(self._max_retries + 1):
            attempts = attempt + 1
            try:
                decoded = self._transport(url, headers, body, self._timeout_s)
                break
            except AdapterError as exc:
                last_error = exc
        elapsed = time.perf_counter() - started
        if decoded is None:
            raise last_error or AdapterError("remote API call failed without a recorded error")

        choices = decoded.get("choices")
        if not isinstance(choices, list) or not choices:
            raise AdapterError("remote API response has no 'choices' array")
        first = choices[0] if isinstance(choices[0], Mapping) else None
        message = first.get("message") if first else None
        content = message.get("content") if isinstance(message, Mapping) else None
        if not isinstance(content, str):
            raise AdapterError("remote API response has no choices[0].message.content string")

        usage = decoded.get("usage")
        tokens_in = tokens_out = None
        if isinstance(usage, Mapping):
            tokens_in = _positive_int_or_none(usage.get("prompt_tokens"))
            tokens_out = _positive_int_or_none(usage.get("completion_tokens"))
        cost = self._estimate_cost(tokens_in, tokens_out)

        return AdapterResponse(
            text=content,
            finish_reason=str(first.get("finish_reason")) if first and first.get("finish_reason") else None,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            wall_time_s=elapsed,
            peak_vram_mb=None,  # remote: not measured here, never 0
            metadata={
                "backend": "openai_compat",
                "model_id": self._descriptor.model_id,
                "endpoint_path": CHAT_COMPLETIONS_PATH,
                "attempts": attempts,
                "estimated_cost_usd": cost,
                "transport_injected": self._transport_injected,
                "raw_usage": dict(usage) if isinstance(usage, Mapping) else None,
            },
        )

    def _estimate_cost(self, tokens_in: int | None, tokens_out: int | None) -> float | None:
        if self._price_in is None and self._price_out is None:
            return None  # no price configured -> not measured
        if self._price_in is not None and tokens_in is None:
            return None  # cannot price without usage
        if self._price_out is not None and tokens_out is None:
            return None
        total = 0.0
        if self._price_in is not None and tokens_in is not None:
            total += tokens_in / 1000.0 * self._price_in
        if self._price_out is not None and tokens_out is not None:
            total += tokens_out / 1000.0 * self._price_out
        return total


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _positive_int_or_none(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value >= 0 else None


__all__ = [
    "CHAT_COMPLETIONS_PATH",
    "DEFAULT_API_KEY_ENV",
    "RemoteOpenAIAdapter",
    "Transport",
]
