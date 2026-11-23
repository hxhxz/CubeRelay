"""Independent VLM perception and LLM planning providers for M4-B/M4-E."""

from __future__ import annotations

import hashlib
import json
import os
import socket
import time
from typing import Any, Callable, Mapping, Protocol, TypeVar
import urllib.error
import urllib.parse
import urllib.request
import uuid

from pydantic import BaseModel, Field, ValidationError

from cube_relay.perception.evidence import (
    EvidenceSourceType,
    PerceptionEvidenceBundle,
    SemanticObservationEnvelope,
    build_perception_evidence_bundle,
)
from cube_relay.perception.validator import EvidenceValidationResult, EvidenceValidator

from .models import (
    AgentActionDecision,
    AgentObservation,
    ObservationReference,
    SemanticSceneObservation,
    VLMDecisionOutput,
)
from .vlm_client import (
    VLMCallResult,
    _chat_completions_url,
    _execute_json_post_with_transport_retry,
    _format_http_error,
    _strip_json_fences,
    _urlopen_without_environment_proxy,
)

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class StructuredCall(BaseModel):
    provider: str
    model: str
    latency_ms: float
    input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    parsed: dict[str, Any] | None = None
    error: str | None = None
    error_code: str | None = None
    prompt_sha256: str | None = None
    redacted_prompt_summary: str | None = None
    request_id: str | None = Field(default_factory=lambda: f"req-{uuid.uuid4().hex[:12]}")


class StructuredModelClient(Protocol):
    provider_name: str
    model: str
    has_completed_valid_call: bool

    def is_configured(self) -> bool: ...
    def generate(self, prompt: str, schema: type[SchemaT], image_data_url: str | None = None) -> tuple[SchemaT | None, StructuredCall]: ...


class OpenAICompatibleStructuredClient:
    """One independently configured OpenAI-compatible structured model endpoint."""

    provider_name = "openai_compatible"

    def __init__(self, role: str) -> None:
        prefix = f"CUBERELAY_{role.upper()}_"
        self.role = role.lower()
        self.endpoint = os.getenv(prefix + "ENDPOINT", "").rstrip("/")
        self.model = os.getenv(prefix + "MODEL", "").strip()
        self.api_key = os.getenv(prefix + "API_KEY", "").strip()
        self.temperature = float(os.getenv(prefix + "TEMPERATURE", "0"))
        self.timeout_seconds = float(os.getenv(prefix + "TIMEOUT_SECONDS", "90"))
        # Must accommodate both internal reasoning/thinking tokens (e.g. Gemini Flash
        # thinking models) and the full structured JSON payload to avoid finish_reason=length truncation.
        self.token_budget = int(os.getenv(prefix + "TOKEN_BUDGET", "8192"))
        self.reasoning_effort: str | None = os.getenv(prefix + "REASONING_EFFORT", "").strip() or None
        raw_thinking_budget = os.getenv(prefix + "THINKING_BUDGET", "").strip()
        self._explicit_thinking_budget_off = raw_thinking_budget.lower() in {
            "off",
            "none",
            "null",
            "-1",
            "0",
            "disabled",
        }
        if raw_thinking_budget == "":
            self.thinking_budget: int | None = 1024 if self.role == "agent" else None
        elif raw_thinking_budget.lower() in {"off", "none", "null", "-1", "disabled"}:
            self.thinking_budget = None
        else:
            tb_val = int(raw_thinking_budget)
            self.thinking_budget = tb_val if tb_val >= 0 else None
        raw_thinking_mode = os.getenv(prefix + "THINKING", "").strip().lower()
        if raw_thinking_mode in {"disabled", "off", "false", "0", "disable", "none"}:
            self.thinking_mode: str | None = "disabled"
        elif raw_thinking_mode in {"enabled", "on", "true", "1", "enable"}:
            self.thinking_mode = "enabled"
        else:
            self.thinking_mode = None
        self.provider_name = os.getenv(prefix + "PROVIDER", "openai_compatible").strip()
        self.has_completed_valid_call = False
        self.traces: list[StructuredCall] = []

    def is_configured(self) -> bool:
        return bool(self.endpoint and self.model and self.api_key)

    def _is_deepseek_target(self) -> bool:
        host = (urllib.parse.urlparse(self.endpoint).hostname or "").lower()
        model = self.model.lower()
        provider = self.provider_name.lower()
        return "deepseek" in host or model.startswith("deepseek") or provider == "deepseek"

    def _apply_thinking_params(self, payload: dict[str, Any]) -> None:
        if self._is_deepseek_target():
            eff = (self.reasoning_effort or "").strip()
            if (
                self.thinking_mode == "disabled"
                or self.thinking_budget == 0
                or self._explicit_thinking_budget_off
                or eff.lower() == "none"
            ):
                payload["thinking"] = {"type": "disabled"}
                return
            if self.thinking_mode == "enabled":
                payload["thinking"] = {"type": "enabled"}
            if eff and eff.lower() != "none":
                payload["reasoning_effort"] = eff
            return

        if self.reasoning_effort:
            payload["reasoning_effort"] = self.reasoning_effort
        if self.thinking_budget is not None:
            payload["extra_body"] = {
                "google": {"thinking_config": {"thinking_budget": self.thinking_budget}}
            }

    def generate(
        self,
        prompt: str,
        schema: type[SchemaT],
        image_data_url: str | None = None,
    ) -> tuple[SchemaT | None, StructuredCall]:
        started = time.perf_counter()
        prompt_sha = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        prompt_preview = prompt[:320].replace("\n", " ")
        parsed: SchemaT | None = None
        error: str | None = None
        error_code: str | None = None
        input_tokens: int | None = None
        output_tokens: int | None = None
        reasoning_tokens: int | None = None
        finish_reason: str | None = None
        if not self.is_configured():
            trace = StructuredCall(
                provider=self.provider_name,
                model=self.model,
                latency_ms=0.0,
                error=f"{self.role} model is not configured",
                error_code="CLIENT_UNCONFIGURED",
                prompt_sha256=prompt_sha,
                redacted_prompt_summary=prompt_preview,
            )
            self.traces.append(trace)
            return None, trace

        if image_data_url:
            content: str | list[dict[str, Any]] = [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": image_data_url}},
            ]
        else:
            content = prompt
        base_payload: dict[str, Any] = {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.token_budget,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "user", "content": content}],
        }
        payload = dict(base_payload)
        self._apply_thinking_params(payload)
        target_url = _chat_completions_url(self.endpoint)

        def _make_req(body_dict: dict[str, Any]) -> urllib.request.Request:
            return urllib.request.Request(
                target_url,
                data=json.dumps(body_dict).encode("utf-8"),
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
            )

        last_http_detail: str | None = None
        try:
            while True:
                try:
                    body = _execute_json_post_with_transport_retry(
                        _make_req(payload),
                        timeout=self.timeout_seconds,
                        opener_fn=_urlopen_without_environment_proxy,
                    )
                    break
                except urllib.error.HTTPError as exc:
                    raw_detail = exc.read(4096).decode("utf-8", errors="replace")
                    last_http_detail = raw_detail
                    if exc.code not in {400, 422} or payload == base_payload:
                        raise
                    # Preserve the other thinking switch on gateways that identify
                    # which extension they reject. Generic errors get the base request.
                    detail = raw_detail.lower()
                    rejected = []
                    if "reasoning_effort" in detail and "reasoning_effort" in payload:
                        rejected.append("reasoning_effort")
                    if "thinking" in detail and "thinking" in payload:
                        rejected.append("thinking")
                    if any(key in detail for key in ("extra_body", "thinking_config", "thinking_budget", "google")) and "extra_body" in payload:
                        rejected.append("extra_body")
                    if rejected:
                        for key in rejected:
                            del payload[key]
                    else:
                        payload = dict(base_payload)
            usage = body.get("usage") or body.get("usageMetadata") or body.get("usage_metadata") or {}
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
            choice = body["choices"][0]
            finish_reason = choice.get("finish_reason")
            raw = str(choice["message"].get("content") or "")
            parsed = schema.model_validate(json.loads(_strip_json_fences(raw)))
            self.has_completed_valid_call = True
        except (TimeoutError, socket.timeout) as exc:
            error_code, error = "MODEL_TIMEOUT", f"{type(exc).__name__}: {exc}"
        except urllib.error.HTTPError as exc:
            error_code = "API_UNAVAILABLE"
            error = _format_http_error(exc, target_url, pre_read_detail=last_http_detail)
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                error_code = "MODEL_TIMEOUT"
            else:
                error_code = "API_UNAVAILABLE"
            error = f"{type(exc).__name__}: {exc}"
        except json.JSONDecodeError as exc:
            error_code = "INVALID_JSON"
            trunc_hint = (
                f" [truncated at max_tokens={self.token_budget}, finish_reason=length]"
                if finish_reason == "length"
                else ""
            )
            error = f"JSONDecodeError: {exc}{trunc_hint}"
        except ValidationError as exc:
            error_code, error = "SCHEMA_VALIDATION_FAILED", f"ValidationError: {exc}"
        except Exception as exc:
            error_code, error = "API_UNAVAILABLE", f"{type(exc).__name__}: {exc}"
        trace = StructuredCall(
            provider=self.provider_name,
            model=self.model,
            latency_ms=round((time.perf_counter() - started) * 1000.0, 2),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            reasoning_tokens=reasoning_tokens,
            parsed=parsed.model_dump(mode="json") if parsed else None,
            error=error,
            error_code=error_code,
            prompt_sha256=prompt_sha,
            redacted_prompt_summary=prompt_preview,
        )
        self.traces.append(trace)
        return parsed, trace


class FakeStructuredModelClient:
    """Offline independent provider used only for protocol and physical-loop tests."""

    provider_name = "fake_structured_model"

    def __init__(
        self,
        role: str,
        handler: Callable[[str, str | None], dict[str, Any]],
        *,
        model: str | None = None,
        latency_ms: float = 5.0,
    ) -> None:
        self.role = role
        self.model = model or f"fake-{role}"
        self.handler = handler
        self.latency_ms = latency_ms
        self.has_completed_valid_call = False
        self.traces: list[StructuredCall] = []
        self.calls: list[dict[str, Any]] = []

    def is_configured(self) -> bool:
        return True

    def generate(self, prompt: str, schema: type[SchemaT], image_data_url: str | None = None) -> tuple[SchemaT | None, StructuredCall]:
        self.calls.append({"prompt": prompt, "image_data_url": image_data_url})
        try:
            parsed = schema.model_validate(self.handler(prompt, image_data_url))
            self.has_completed_valid_call = True
            trace = StructuredCall(
                provider=self.provider_name,
                model=self.model,
                latency_ms=self.latency_ms,
                parsed=parsed.model_dump(mode="json"),
            )
            self.traces.append(trace)
            return parsed, trace
        except Exception as exc:
            trace = StructuredCall(
                provider=self.provider_name,
                model=self.model,
                latency_ms=self.latency_ms,
                error=f"{type(exc).__name__}: {exc}",
                error_code="SCHEMA_VALIDATION_FAILED",
            )
            self.traces.append(trace)
            return None, trace


class VLMPerceptionProvider:
    """Model A: image-to-semantics only. It never receives the Skill list."""

    def __init__(self, client: StructuredModelClient | None = None) -> None:
        self.client = client or OpenAICompatibleStructuredClient("PERCEPTION")
        self.latest: SemanticSceneObservation | None = None
        self.latest_envelope: SemanticObservationEnvelope | None = None
        self.latest_trace: StructuredCall | None = None

    def _provenance_tags(self) -> tuple[EvidenceSourceType, bool, str]:
        provider_tag = str(getattr(self.client, "provider_name", "") or "").lower()
        is_fake = isinstance(self.client, FakeStructuredModelClient) or "fake" in provider_tag
        client_type = "fake_structured_model" if is_fake else type(self.client).__name__
        return EvidenceSourceType.REAL_VLM, (not is_fake), client_type

    def perceive_envelope(
        self,
        observation: Any,
        image_data_url: str | None,
    ) -> tuple[SemanticObservationEnvelope | None, StructuredCall, bool]:
        """Run image-to-semantics inference and wrap result in a provenance envelope."""
        camera_id = getattr(observation, "camera_id", None) or getattr(observation, "camera_name", "overhead")
        sim_time = getattr(observation, "sim_time", None)
        prompt = (
            "You are CubeRelay's visual perception model. Describe only observable scene semantics; "
            "never select a robot Skill and never infer hidden sticker colors. Output strict JSON.\n"
            + json.dumps({
                "observation_id": observation.observation_id,
                "frame_id": observation.frame_id,
                "camera_id": camera_id,
                "schema": SemanticSceneObservation.model_json_schema(),
            }, ensure_ascii=False, separators=(",", ":"))
        )
        parsed, trace = self.client.generate(prompt, SemanticSceneObservation, image_data_url)
        self.latest_trace = trace
        if parsed is None:
            self.latest_envelope = None
            return None, trace, False

        source_type, is_real_vlm, client_type = self._provenance_tags()
        envelope = SemanticObservationEnvelope(
            semantic=parsed,
            source_type=source_type,
            is_real_vlm=is_real_vlm,
            declared_origin=client_type,
            client_type=client_type,
            model_provider=getattr(self.client, "provider_name", None),
            model_name=getattr(self.client, "model", None),
            captured_sim_time=float(sim_time) if sim_time is not None else None,
            request_id=trace.request_id,
            latency_ms=trace.latency_ms,
        )
        mismatch = (
            parsed.observation_id != observation.observation_id
            or parsed.frame_id != observation.frame_id
            or parsed.camera_id != camera_id
        )
        if mismatch:
            trace.error_code = "OBSERVATION_REFERENCE_MISMATCH"
            trace.error = "semantic output referenced a different observation/frame/camera"
            self.latest_envelope = envelope
            return envelope, trace, True

        self.latest = parsed
        self.latest_envelope = envelope
        return envelope, trace, False

    def perceive(self, observation: Any, image_data_url: str | None) -> SemanticSceneObservation | None:
        envelope, _trace, mismatch = self.perceive_envelope(observation, image_data_url)
        if envelope is None or mismatch:
            return None
        return envelope.semantic


class AgentPlanningProvider:
    """Model B: semantics/CV/history-to-action only. It receives no image bytes."""

    def __init__(self, client: StructuredModelClient | None = None) -> None:
        self.client = client or OpenAICompatibleStructuredClient("AGENT")
        self.latest: AgentActionDecision | None = None
        self.latest_trace: StructuredCall | None = None

    def decide(
        self,
        base_prompt: str,
        semantics: SemanticSceneObservation | None = None,
        *,
        evidence_observation_id: str | None = None,
        evidence_bundle: PerceptionEvidenceBundle | None = None,
    ) -> AgentActionDecision | None:
        if semantics is not None:
            instruction = (
                "You are CubeRelay's independent planning model. Use the VLM semantics, traditional CV state, "
                "evidence validity metadata, Mission, history, available Skills and physical constraints to select one action. "
                "You do not receive image pixels and must not modify simulation state. Cite valid observation_id(s) in "
                "evidence_observation_ids. Output strict JSON.\n"
            )
            semantic_payload: dict[str, Any] | None = semantics.model_dump(mode="json")
            expected_obs_id = semantics.observation_id
        else:
            instruction = (
                "You are CubeRelay's independent planning model (CV-only mode: no VLM semantic scene observation "
                "is provided). Use only the traditional CV state, observation metadata/history, failure feedback, "
                "Mission, available Skills and physical constraints to select one action. You do not receive image "
                "pixels and must not fabricate visual semantics. Cite valid observation_id(s) in "
                "evidence_observation_ids. Output strict JSON.\n"
            )
            semantic_payload = None
            expected_obs_id = evidence_observation_id

        body: dict[str, Any] = {
            "planner_context": base_prompt,
            "semantic_scene_observation": semantic_payload,
        }
        if evidence_bundle is not None:
            body["evidence_bundle"] = evidence_bundle.to_agent_prompt_payload()
        body["schema"] = AgentActionDecision.model_json_schema()

        prompt = instruction + json.dumps(body, ensure_ascii=False, separators=(",", ":"))
        parsed, trace = self.client.generate(prompt, AgentActionDecision, None)
        self.latest_trace = trace
        if parsed is not None and expected_obs_id is not None and expected_obs_id not in parsed.evidence_observation_ids:
            self.latest_trace.error_code = "EVIDENCE_REFERENCE_INVALID"
            self.latest_trace.error = "agent decision did not cite the current observation"
            return None
        self.latest = parsed
        return parsed


class DualModelDecisionClient:
    """Consolidated M4-B/M4-E dual-model orchestrator enforcing PerceptionEvidenceBundle & EvidenceValidator."""

    provider_name = "dual_model_pipeline"

    def __init__(
        self,
        perception: VLMPerceptionProvider | None = None,
        agent: AgentPlanningProvider | None = None,
        *,
        use_vlm_perception: bool = True,
        injected_semantics: SemanticSceneObservation | None = None,
        allow_cv_only_on_vlm_failure: bool = False,
        evidence_validator: EvidenceValidator | None = None,
    ) -> None:
        self.perception = perception or VLMPerceptionProvider()
        self.agent = agent or AgentPlanningProvider()
        self.use_vlm_perception = bool(use_vlm_perception)
        self.injected_semantics = injected_semantics
        self.allow_cv_only_on_vlm_failure = bool(allow_cv_only_on_vlm_failure)
        self.evidence_validator = evidence_validator or EvidenceValidator()
        self.model = (
            f"perception={self.perception.client.model};agent={self.agent.client.model}"
            if self.use_vlm_perception
            else f"perception=NONE;agent={self.agent.client.model}"
        )
        self.has_completed_valid_call = False
        self.traces: list[VLMCallResult] = []
        self.last_perception_latency_ms = 0.0
        self.last_agent_latency_ms = 0.0
        self.last_semantic_observation: SemanticSceneObservation | None = None
        self.last_agent_decision: AgentActionDecision | None = None
        self.last_prompt_metadata: dict[str, Any] = {}
        self.last_evidence_bundle: PerceptionEvidenceBundle | None = None
        self.last_validation_result: EvidenceValidationResult | None = None
        self.last_request_id: str | None = None
        self.event_callback: Callable[[str, dict[str, Any]], None] | None = None

    def _emit(self, phase: str, payload: dict[str, Any]) -> None:
        if self.event_callback is not None:
            self.event_callback(phase, payload)

    def is_configured(self) -> bool:
        if not self.use_vlm_perception or self.injected_semantics is not None:
            return self.agent.client.is_configured()
        return self.perception.client.is_configured() and self.agent.client.is_configured()

    @staticmethod
    def _fallback_observation_from_prompt(prompt: str, rgb_data_url: str | None) -> tuple[dict[str, Any], dict[str, Any]]:
        context = json.loads(prompt.split("\n", 1)[1])
        metadata = dict(context["observation_metadata"])
        observable_state = dict(context.get("observable_state") or {})
        metadata.setdefault("camera_id", "overhead")
        metadata.setdefault("mission_id", context.get("mission_id"))
        metadata.setdefault("session_id", None)
        metadata.setdefault("sim_time", observable_state.get("sim_time", 0.0))
        metadata.setdefault("rgb_image_data_url", rgb_data_url)
        metadata.setdefault("observed_count", observable_state.get("observed_count", 0))
        metadata.setdefault("unknown_facelet_indices", observable_state.get("unknown_facelet_indices", []))
        metadata.setdefault("observation_conflicts", observable_state.get("observation_conflicts", []))
        metadata.setdefault("observed_facelets", observable_state.get("observed_facelets"))
        metadata.setdefault("latest_skill_result", metadata.get("latest_skill_result"))
        metadata.setdefault("scene_summary", observable_state)
        return metadata, observable_state

    def decide_with_evidence(
        self,
        *,
        prompt: str,
        observation: AgentObservation | Mapping[str, Any],
        observation_ref: ObservationReference | Mapping[str, Any] | None = None,
        scene_state: Mapping[str, Any] | None = None,
        rgb_data_url: str | None = None,
        include_image: bool = True,
        geometric_source: EvidenceSourceType | str | None = None,
        allow_cv_only_on_vlm_failure: bool | None = None,
    ) -> VLMCallResult:
        started = time.perf_counter()
        prompt_sha = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        image_sha = hashlib.sha256(rgb_data_url.encode("utf-8")).hexdigest() if rgb_data_url else None
        eff_allow_cv_only = (
            self.allow_cv_only_on_vlm_failure
            if allow_cv_only_on_vlm_failure is None
            else bool(allow_cv_only_on_vlm_failure)
        )
        obs_dict = observation.model_dump() if isinstance(observation, AgentObservation) else dict(observation)
        frame_src = str((obs_dict.get("camera_metadata") or {}).get("frame_source") or "")
        resolved_geo_source: EvidenceSourceType | str = (
            geometric_source
            if geometric_source is not None
            else (
                EvidenceSourceType.RECORDED_REPLAY
                if frame_src == "REAL_MUJOCO_BUNDLE"
                else EvidenceSourceType.DETERMINISTIC_CV
            )
        )
        obs_id = str(obs_dict["observation_id"])
        frame_id = str(obs_dict["frame_id"])
        camera_id = str(obs_dict.get("camera_id") or "overhead")
        obs_proxy = type("ObservationRef", (), {
            "observation_id": obs_id,
            "frame_id": frame_id,
            "camera_id": camera_id,
            "sim_time": obs_dict.get("sim_time", 0.0),
        })()

        self.last_semantic_observation = None
        self.last_agent_decision = None
        self.last_evidence_bundle = None
        self.last_validation_result = None
        self.last_prompt_metadata = {
            "prompt_sha256": prompt_sha,
            "use_vlm_perception": self.use_vlm_perception,
            "has_injected_semantics": self.injected_semantics is not None,
        }

        envelope: SemanticObservationEnvelope | SemanticSceneObservation | None = None
        sem_source = EvidenceSourceType.NONE
        p_trace: StructuredCall | None = None
        vlm_requested = False
        vlm_timed_out = False
        vlm_error_code: str | None = None
        vlm_error: str | None = None
        sem_model_provider: str | None = None
        sem_model_name: str | None = None
        sem_client_type: str | None = None

        if self.injected_semantics is not None:
            envelope = self.injected_semantics
            sem_source = EvidenceSourceType.INJECTED_SEMANTICS
            sem_client_type = "injected_semantics"
            sem_model_provider = "benchmark_injection"
            sem_model_name = "injected_semantic_observation"
            self.last_perception_latency_ms = 0.0
        elif self.use_vlm_perception:
            vlm_requested = True
            if not include_image:
                vlm_error_code = "IMAGE_WITHHELD_NO_IMAGE"
                vlm_error = "VLM perception enabled but include_image=False"
                self.last_perception_latency_ms = 0.0
            else:
                self._emit("VLM_INFERENCE_STARTED", {
                    "observation_id": obs_id,
                    "frame_id": frame_id,
                    "model": self.perception.client.model,
                    "provider": self.perception.client.provider_name,
                })
                envelope, p_trace, ref_mismatch = self.perception.perceive_envelope(
                    obs_proxy, rgb_data_url
                )
                self.last_perception_latency_ms = float(p_trace.latency_ms if p_trace else 0.0)
                sem_source = EvidenceSourceType.REAL_VLM
                sem_model_provider = self.perception.client.provider_name
                sem_model_name = self.perception.client.model
                sem_client_type = envelope.client_type if envelope else type(self.perception.client).__name__
                vlm_error_code = p_trace.error_code if p_trace else None
                vlm_error = p_trace.error if p_trace else None
                vlm_timed_out = bool(vlm_error_code == "MODEL_TIMEOUT")
                valid_sem = envelope.semantic if (envelope is not None and not ref_mismatch) else None
                self._emit("VLM_INFERENCE_COMPLETED", {
                    "observation_id": obs_id,
                    "frame_id": frame_id,
                    "model": self.perception.client.model,
                    "provider": self.perception.client.provider_name,
                    "latency_ms": self.last_perception_latency_ms,
                    "input_tokens": p_trace.input_tokens if p_trace else None,
                    "output_tokens": p_trace.output_tokens if p_trace else None,
                    "semantic": valid_sem.model_dump(mode="json") if valid_sem else None,
                    "error_code": vlm_error_code,
                    "request_id": p_trace.request_id if p_trace else None,
                })
        else:
            self.last_perception_latency_ms = 0.0

        bundle = build_perception_evidence_bundle(
            obs_dict,
            observation_ref=observation_ref,
            scene_state=scene_state,
            semantic_observation=envelope,
            semantic_source=sem_source,
            geometric_source=resolved_geo_source,
            semantic_client_type=sem_client_type,
            model_provider=sem_model_provider,
            model_name=sem_model_name,
            semantic_request_id=p_trace.request_id if p_trace else None,
            semantic_latency_ms=self.last_perception_latency_ms if vlm_requested else None,
            vlm_requested=vlm_requested,
            vlm_timed_out=vlm_timed_out,
            vlm_error_code=vlm_error_code,
            vlm_error=vlm_error,
        )
        validation = self.evidence_validator.validate(
            bundle,
            allow_cv_only_on_vlm_failure=eff_allow_cv_only,
        )
        validated_bundle = validation.bundle
        self.last_evidence_bundle = validated_bundle
        self.last_validation_result = validation

        provenance_dict = validated_bundle.provenance.model_dump(mode="json")
        validity_dict = validated_bundle.validity.model_dump(mode="json")
        conflict_codes = list(validated_bundle.detected_conflicts)

        should_abort_before_agent = validated_bundle.validity.fail_closed_required or (
            validated_bundle.validity.semantic_rejected and not eff_allow_cv_only
        )
        if should_abort_before_agent:
            err_code = vlm_error_code or (
                "SOURCE_COERCION_FORBIDDEN"
                if validated_bundle.validity.semantic_rejection_reason == "SOURCE_COERCION_FORBIDDEN"
                else ("OBSERVATION_REFERENCE_MISMATCH" if validated_bundle.validity.is_stale else "PERCEPTION_FAILED")
            )
            err_msg = vlm_error or validated_bundle.validity.semantic_rejection_reason or "perception failed"
            req_id = (p_trace.request_id if p_trace else None) or f"req-{uuid.uuid4().hex[:12]}"
            self.last_request_id = req_id
            result = VLMCallResult(
                provider=self.provider_name,
                model=self.model,
                endpoint_host="independent-providers",
                latency_ms=round((time.perf_counter() - started) * 1000.0, 2),
                prompt_sha256=prompt_sha,
                image_sha256=image_sha,
                image_included=bool(include_image and rgb_data_url and self.use_vlm_perception),
                input_tokens=p_trace.input_tokens if p_trace else None,
                output_tokens=p_trace.output_tokens if p_trace else None,
                error=err_msg,
                error_code=err_code,
                request_id=req_id,
                evidence_bundle_id=validated_bundle.bundle_id,
                perception_provenance=provenance_dict,
                evidence_conflicts=conflict_codes,
                evidence_validity=validity_dict,
                semantic_provided_to_agent=False,
            )
            self.traces.append(result)
            return result

        semantics_for_agent = validation.semantic_passed_to_agent
        self.last_semantic_observation = semantics_for_agent

        self._emit("AGENT_DECISION_STARTED", {
            "observation_id": semantics_for_agent.observation_id if semantics_for_agent else obs_id,
            "frame_id": semantics_for_agent.frame_id if semantics_for_agent else frame_id,
            "model": self.agent.client.model,
            "provider": self.agent.client.provider_name,
            "evidence_bundle_id": validated_bundle.bundle_id,
            "detected_conflicts": conflict_codes,
            "semantic_provided_to_agent": semantics_for_agent is not None,
        })
        agent_decision = self.agent.decide(
            prompt,
            semantics_for_agent,
            evidence_observation_id=obs_id,
            evidence_bundle=validated_bundle,
        )
        a_trace = self.agent.latest_trace
        self.last_agent_latency_ms = float(a_trace.latency_ms if a_trace else 0.0)
        combined_req_id = (
            a_trace.request_id if a_trace and a_trace.request_id else None
        ) or (p_trace.request_id if p_trace else None) or f"req-{uuid.uuid4().hex[:12]}"
        self.last_request_id = combined_req_id

        self._emit("AGENT_DECISION_COMPLETED", {
            "observation_id": semantics_for_agent.observation_id if semantics_for_agent else obs_id,
            "frame_id": semantics_for_agent.frame_id if semantics_for_agent else frame_id,
            "model": self.agent.client.model,
            "provider": self.agent.client.provider_name,
            "latency_ms": self.last_agent_latency_ms,
            "input_tokens": a_trace.input_tokens if a_trace else None,
            "output_tokens": a_trace.output_tokens if a_trace else None,
            "reasoning_tokens": a_trace.reasoning_tokens if a_trace else None,
            "decision": agent_decision.model_dump(mode="json") if agent_decision else None,
            "error_code": a_trace.error_code if a_trace else None,
            "request_id": combined_req_id,
            "evidence_bundle_id": validated_bundle.bundle_id,
        })
        if agent_decision is None:
            in_tok = (p_trace.input_tokens or 0) if p_trace else 0
            out_tok = (p_trace.output_tokens or 0) if p_trace else 0
            reason_tok = (p_trace.reasoning_tokens or 0) if (p_trace and p_trace.reasoning_tokens is not None) else 0
            has_reason = bool(p_trace and p_trace.reasoning_tokens is not None)
            if a_trace:
                in_tok += a_trace.input_tokens or 0
                out_tok += a_trace.output_tokens or 0
                if a_trace.reasoning_tokens is not None:
                    reason_tok += a_trace.reasoning_tokens
                    has_reason = True
            result = VLMCallResult(
                provider=self.provider_name,
                model=self.model,
                endpoint_host="independent-providers",
                latency_ms=round((time.perf_counter() - started) * 1000.0, 2),
                prompt_sha256=prompt_sha,
                image_sha256=image_sha,
                image_included=bool(include_image and rgb_data_url and self.use_vlm_perception),
                input_tokens=in_tok or None,
                output_tokens=out_tok or None,
                reasoning_tokens=reason_tok if has_reason else None,
                error=a_trace.error if a_trace else "agent planning failed",
                error_code=a_trace.error_code if a_trace else "AGENT_DECISION_FAILED",
                request_id=combined_req_id,
                evidence_bundle_id=validated_bundle.bundle_id,
                perception_provenance=provenance_dict,
                evidence_conflicts=conflict_codes,
                evidence_validity=validity_dict,
                semantic_provided_to_agent=semantics_for_agent is not None,
            )
            self.traces.append(result)
            return result

        self.last_agent_decision = agent_decision
        translated = VLMDecisionOutput(
            action=agent_decision.skill_id or agent_decision.selected_action,
            parameters=agent_decision.parameters,
            reason_summary=agent_decision.reason_summary,
            expected_information_gain=agent_decision.expected_outcome,
            confidence=agent_decision.confidence,
        )
        p_in = (p_trace.input_tokens or 0) if p_trace else 0
        p_out = (p_trace.output_tokens or 0) if p_trace else 0
        a_in = (a_trace.input_tokens or 0) if a_trace else 0
        a_out = (a_trace.output_tokens or 0) if a_trace else 0
        p_reas = p_trace.reasoning_tokens if p_trace else None
        a_reas = a_trace.reasoning_tokens if a_trace else None
        tot_reas = ((p_reas or 0) + (a_reas or 0)) if (p_reas is not None or a_reas is not None) else None
        result = VLMCallResult(
            provider=self.provider_name,
            model=self.model,
            endpoint_host="independent-providers",
            latency_ms=round((time.perf_counter() - started) * 1000.0, 2),
            input_tokens=int(p_in + a_in),
            output_tokens=int(p_out + a_out),
            reasoning_tokens=tot_reas,
            prompt_sha256=prompt_sha,
            image_sha256=image_sha,
            image_included=bool(include_image and rgb_data_url and self.use_vlm_perception),
            parsed_output=translated,
            request_id=combined_req_id,
            evidence_bundle_id=validated_bundle.bundle_id,
            perception_provenance=provenance_dict,
            evidence_conflicts=conflict_codes,
            evidence_validity=validity_dict,
            semantic_provided_to_agent=semantics_for_agent is not None,
        )
        self.has_completed_valid_call = True
        self.traces.append(result)
        return result

    def generate_decision(self, prompt: str, rgb_data_url: str | None = None, *, include_image: bool = True) -> VLMCallResult:
        """Prompt-context adapter delegating directly into `decide_with_evidence`."""
        prompt_sha = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        image_sha = hashlib.sha256(rgb_data_url.encode("utf-8")).hexdigest() if rgb_data_url else None
        try:
            obs_dict, observable_state = self._fallback_observation_from_prompt(prompt, rgb_data_url)
        except Exception as exc:
            result = VLMCallResult(
                provider=self.provider_name,
                model=self.model,
                endpoint_host="independent-providers",
                latency_ms=0.0,
                prompt_sha256=prompt_sha,
                image_sha256=image_sha,
                image_included=bool(include_image and rgb_data_url),
                error=f"invalid planner context: {exc}",
                error_code="INVALID_PLANNER_CONTEXT",
            )
            self.traces.append(result)
            return result
        return self.decide_with_evidence(
            prompt=prompt,
            observation=obs_dict,
            scene_state=observable_state,
            rgb_data_url=rgb_data_url,
            include_image=include_image,
        )
