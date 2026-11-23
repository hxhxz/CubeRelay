"""Gemini multimodal VLM client loaded safely from environment variables / .env."""

from __future__ import annotations

import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import socket
import ssl
import time
from typing import Any, Callable
import urllib.error
import urllib.parse
import urllib.request

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .models import VLMDecisionOutput

DEFAULT_VLM_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/openai/"
DEFAULT_VLM_MODEL = "gemini-3.5-flash-lite"


def _chat_completions_url(endpoint: str) -> str:
    """Build a /chat/completions URL without duplicating the path suffix."""
    clean = str(endpoint or "").strip().rstrip("/")
    if clean.endswith("/chat/completions"):
        return clean
    return clean + "/chat/completions"


def _format_http_error(
    exc: urllib.error.HTTPError,
    url: str | None = None,
    *,
    pre_read_detail: str | None = None,
) -> str:
    """Format HTTPError with target URL and response body snippet for diagnostics."""
    detail = pre_read_detail
    if detail is None:
        try:
            raw = exc.read(1024)
            detail = raw.decode("utf-8", errors="replace").strip() if raw else ""
        except Exception:
            detail = ""
    else:
        detail = detail.strip()
    parts = [f"HTTPError: {exc}"]
    if url:
        parts.append(f"url={url}")
    if detail:
        parts.append(f"body={detail[:500]}")
    return " | ".join(parts)


def _urlopen_without_environment_proxy(
    request: urllib.request.Request,
    *,
    timeout: float,
) -> Any:
    """Open model requests directly, ignoring Docker/Desktop proxy injection."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    return opener.open(request, timeout=timeout)


def _is_transient_transport_error(exc: BaseException) -> bool:
    """True only for transient TLS/socket/DNS/HTTP-5xx/429 transport failures (never timeouts/JSON)."""
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code in {429, 500, 502, 503, 504}
    if isinstance(exc, (http.client.RemoteDisconnected, ssl.SSLError, ConnectionResetError, BrokenPipeError)):
        return True
    if isinstance(exc, urllib.error.URLError):
        reason = exc.reason
        if isinstance(reason, (http.client.RemoteDisconnected, ssl.SSLError, socket.gaierror, ConnectionResetError, BrokenPipeError)):
            return True
        msg = str(reason or exc).lower()
        return any(tok in msg for tok in (
            "unexpected_eof_while_reading",
            "remote end closed connection",
            "temporary failure in name resolution",
            "connection reset by peer",
        ))
    return False


def _execute_json_post_with_transport_retry(
    request: urllib.request.Request,
    *,
    timeout: float,
    opener_fn: Callable[..., Any] | None = None,
    max_transport_retries: int = 2,
) -> dict[str, Any]:
    """Read JSON HTTP response with bounded backoff retry on transient TLS/DNS drops."""
    fn = opener_fn or _urlopen_without_environment_proxy
    last_exc: BaseException | None = None
    for attempt in range(max_transport_retries + 1):
        try:
            with fn(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except BaseException as exc:
            last_exc = exc
            if attempt >= max_transport_retries or not _is_transient_transport_error(exc):
                raise
            time.sleep(1.0 * (attempt + 1))
    assert last_exc is not None
    raise last_exc


def load_local_env(path: Path = Path(".env")) -> dict[str, str]:
    """Load key-value pairs from a local .env file without overwriting existing env vars."""
    loaded: dict[str, str] = {}
    if not path.exists():
        return loaded
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        clean_key = key.strip()
        clean_val = value.strip().strip('"').strip("'")
        if clean_key:
            os.environ.setdefault(clean_key, clean_val)
            loaded[clean_key] = clean_val
    return loaded


def _strip_json_fences(raw_text: str) -> str:
    stripped = raw_text.strip()
    fence_match = re.search(r"```(?:json)?\s*(.*?)\s*```", stripped, flags=re.DOTALL | re.IGNORECASE)
    if fence_match:
        return fence_match.group(1).strip()
    return stripped


class VLMCallResult(BaseModel):
    """Auditable outcome of a single VLM inference call."""

    model_config = ConfigDict(extra="forbid")

    provider: str
    model: str
    endpoint_host: str
    latency_ms: float
    input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    prompt_sha256: str
    image_sha256: str | None = None
    image_included: bool = True
    raw_response: str = ""
    parsed_output: VLMDecisionOutput | None = None
    error: str | None = None
    error_code: str | None = None
    # M4-E request & evidence correlation metadata
    request_id: str | None = None
    evidence_bundle_id: str | None = None
    perception_provenance: dict[str, Any] = Field(default_factory=dict)
    evidence_conflicts: list[str] = Field(default_factory=list)
    evidence_validity: dict[str, Any] = Field(default_factory=dict)
    semantic_provided_to_agent: bool | None = None


class _EnvLoadedGeminiClient:
    """Gemini VLM client using OpenAI-compatible multimodal chat completions."""

    provider_name = "gemini_openai_compatible"

    def __init__(
        self,
        *,
        endpoint: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        timeout_seconds: float = 45.0,
        env_path: Path | None = None,
        load_env_file: bool = True,
    ) -> None:
        if load_env_file:
            candidate_env = env_path or Path(__file__).resolve().parents[3] / ".env"
            load_local_env(candidate_env)
            if Path(".env").exists() and Path(".env").resolve() != candidate_env.resolve():
                load_local_env(Path(".env"))

        resolved_endpoint = endpoint if endpoint is not None else os.getenv("CUBERELAY_VLM_ENDPOINT", DEFAULT_VLM_ENDPOINT)
        resolved_model = model if model is not None else os.getenv("CUBERELAY_VLM_MODEL", DEFAULT_VLM_MODEL)
        resolved_key = api_key if api_key is not None else os.getenv("CUBERELAY_VLM_API_KEY", "")

        self.endpoint = str(resolved_endpoint).rstrip("/")
        self.model = str(resolved_model).strip()
        self.api_key = str(resolved_key).strip()
        self.timeout_seconds = float(timeout_seconds)
        self.traces: list[VLMCallResult] = []
        self.has_completed_valid_call: bool = False

    def __repr__(self) -> str:
        return (
            f"_EnvLoadedGeminiClient(endpoint={self.endpoint!r}, "
            f"model={self.model!r}, api_key='<REDACTED>', "
            f"configured={self.is_configured()})"
        )

    def is_configured(self) -> bool:
        return bool(self.endpoint and self.model and self.api_key)

    def generate_decision(
        self,
        prompt: str,
        rgb_data_url: str | None = None,
        *,
        include_image: bool = True,
    ) -> VLMCallResult:
        prompt_sha = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        has_image = bool(include_image and rgb_data_url)
        img_sha = hashlib.sha256(rgb_data_url.encode("utf-8")).hexdigest() if has_image and rgb_data_url else None
        endpoint_host = urllib.parse.urlparse(self.endpoint).netloc or self.endpoint

        if not self.is_configured():
            res = VLMCallResult(
                provider=self.provider_name,
                model=self.model or "",
                endpoint_host=endpoint_host,
                latency_ms=0.0,
                prompt_sha256=prompt_sha,
                image_sha256=img_sha,
                image_included=has_image,
                error="Missing CUBERELAY_VLM_ENDPOINT, CUBERELAY_VLM_MODEL, or CUBERELAY_VLM_API_KEY",
                error_code="CLIENT_UNCONFIGURED",
            )
            self.traces.append(res)
            return res

        if has_image and rgb_data_url is not None:
            content: str | list[dict[str, Any]] = [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": rgb_data_url}},
            ]
        else:
            content = prompt

        target_url = _chat_completions_url(self.endpoint)
        payload = {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "user", "content": content}],
        }
        request = urllib.request.Request(
            target_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )

        started = time.perf_counter()
        raw_text = ""
        parsed: VLMDecisionOutput | None = None
        error_msg: str | None = None
        error_code: str | None = None
        input_tokens: int | None = None
        output_tokens: int | None = None
        reasoning_tokens: int | None = None

        try:
            result = _execute_json_post_with_transport_retry(
                request,
                timeout=self.timeout_seconds,
                opener_fn=_urlopen_without_environment_proxy,
            )
            usage = result.get("usage") or result.get("usageMetadata") or result.get("usage_metadata") or {}
            input_tokens = usage.get("prompt_tokens", usage.get("promptTokenCount"))
            output_tokens = usage.get("completion_tokens", usage.get("candidatesTokenCount"))
            comp_details = usage.get("completion_tokens_details") or {}
            out_details = usage.get("output_tokens_details") or {}
            raw_reasoning = (
                usage.get("reasoning_tokens")
                or usage.get("thoughtsTokenCount")
                or comp_details.get("reasoning_tokens")
                or out_details.get("reasoning_tokens")
            )
            reasoning_tokens = int(raw_reasoning) if raw_reasoning is not None else None
            choices = result.get("choices") or []
            if not choices:
                raise ValueError("Empty choices in Gemini response")
            raw_text = str(choices[0]["message"]["content"])
            cleaned = _strip_json_fences(raw_text)
            decoded = json.loads(cleaned)
            parsed = VLMDecisionOutput.model_validate(decoded)
            self.has_completed_valid_call = True
        except (TimeoutError, socket.timeout) as exc:
            error_code = "MODEL_TIMEOUT"
            error_msg = f"{type(exc).__name__}: {exc}"
        except urllib.error.HTTPError as exc:
            error_code = "API_UNAVAILABLE"
            error_msg = _format_http_error(exc, target_url)
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                error_code = "MODEL_TIMEOUT"
            else:
                error_code = "API_UNAVAILABLE"
            error_msg = f"{type(exc).__name__}: {exc}"
        except json.JSONDecodeError as exc:
            error_code = "INVALID_JSON"
            error_msg = f"JSONDecodeError: {exc}"
        except ValidationError as exc:
            error_code = "SCHEMA_VALIDATION_FAILED"
            error_msg = f"ValidationError: {exc}"
        except Exception as exc:
            error_code = "API_UNAVAILABLE"
            error_msg = f"{type(exc).__name__}: {exc}"

        latency_ms = round((time.perf_counter() - started) * 1000.0, 2)
        call_res = VLMCallResult(
            provider=self.provider_name,
            model=self.model,
            endpoint_host=endpoint_host,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            reasoning_tokens=reasoning_tokens,
            prompt_sha256=prompt_sha,
            image_sha256=img_sha,
            image_included=has_image,
            raw_response=raw_text,
            parsed_output=parsed,
            error=error_msg,
            error_code=error_code,
        )
        self.traces.append(call_res)
        return call_res


class FakeGeminiVLMClient:
    """Offline controllable VLM client for deterministic protocol and ablation tests."""

    provider_name = "fake_gemini_protocol"

    def __init__(
        self,
        *,
        model: str = "gemini-fake-test",
        responses: list[dict[str, Any] | str | Exception] | None = None,
        handler: Callable[[str, str | None, bool], dict[str, Any] | str] | None = None,
        configured: bool = True,
        simulated_latency_ms: float = 12.0,
    ) -> None:
        self.endpoint = "https://fake.gemini.local/v1beta/openai"
        self.model = model
        self._responses = list(responses or [])
        self._handler = handler
        self._configured = configured
        self.simulated_latency_ms = float(simulated_latency_ms)
        self.traces: list[VLMCallResult] = []
        self.calls: list[dict[str, Any]] = []
        self.has_completed_valid_call: bool = False

    def is_configured(self) -> bool:
        return self._configured

    def generate_decision(
        self,
        prompt: str,
        rgb_data_url: str | None = None,
        *,
        include_image: bool = True,
    ) -> VLMCallResult:
        prompt_sha = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        has_image = bool(include_image and rgb_data_url)
        img_sha = hashlib.sha256(rgb_data_url.encode("utf-8")).hexdigest() if has_image and rgb_data_url else None
        self.calls.append({
            "prompt": prompt,
            "prompt_sha256": prompt_sha,
            "image_included": has_image,
            "image_sha256": img_sha,
            "rgb_data_url": rgb_data_url if has_image else None,
        })

        if not self._configured:
            res = VLMCallResult(
                provider=self.provider_name,
                model=self.model,
                endpoint_host="fake.gemini.local",
                latency_ms=0.0,
                prompt_sha256=prompt_sha,
                image_sha256=img_sha,
                image_included=has_image,
                error="Fake client unconfigured",
                error_code="CLIENT_UNCONFIGURED",
            )
            self.traces.append(res)
            return res

        raw_text = ""
        parsed: VLMDecisionOutput | None = None
        error_msg: str | None = None
        error_code: str | None = None

        try:
            if self._handler is not None:
                item: Any = self._handler(prompt, rgb_data_url if has_image else None, has_image)
            elif self._responses:
                item = self._responses.pop(0)
            else:
                raise RuntimeError("FakeGeminiVLMClient ran out of scripted responses")

            if isinstance(item, Exception):
                raise item
            if isinstance(item, str):
                raw_text = item
                decoded = json.loads(_strip_json_fences(item))
            else:
                raw_text = json.dumps(item, ensure_ascii=False)
                decoded = item
            parsed = VLMDecisionOutput.model_validate(decoded)
            self.has_completed_valid_call = True
        except (TimeoutError, socket.timeout) as exc:
            error_code = "MODEL_TIMEOUT"
            error_msg = f"{type(exc).__name__}: {exc}"
        except urllib.error.HTTPError as exc:
            error_code = "API_UNAVAILABLE"
            error_msg = _format_http_error(exc, getattr(exc, "url", None))
        except urllib.error.URLError as exc:
            error_code = "API_UNAVAILABLE"
            error_msg = f"{type(exc).__name__}: {exc}"
        except json.JSONDecodeError as exc:
            error_code = "INVALID_JSON"
            error_msg = f"JSONDecodeError: {exc}"
        except ValidationError as exc:
            error_code = "SCHEMA_VALIDATION_FAILED"
            error_msg = f"ValidationError: {exc}"
        except Exception as exc:
            error_code = "API_UNAVAILABLE"
            error_msg = f"{type(exc).__name__}: {exc}"

        res = VLMCallResult(
            provider=self.provider_name,
            model=self.model,
            endpoint_host="fake.gemini.local",
            latency_ms=self.simulated_latency_ms,
            input_tokens=120,
            output_tokens=36,
            prompt_sha256=prompt_sha,
            image_sha256=img_sha,
            image_included=has_image,
            raw_response=raw_text,
            parsed_output=parsed,
            error=error_msg,
            error_code=error_code,
        )
        self.traces.append(res)
        return res
