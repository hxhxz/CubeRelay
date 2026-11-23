from __future__ import annotations

import io
import json
import math
import urllib.error
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from cube_relay.benchmark.cases import build_m4d_replay_cases
from cube_relay.benchmark.runners import DecisionReplayRunner
from cube_relay.benchmark.schema import PlannerGroup, PromptGuideMode
from cube_relay.mission import dual_model as dm
from cube_relay.mission.dual_model import (
    OpenAICompatibleStructuredClient,
)
from cube_relay.mission.models import AgentActionDecision


class _DummySchema(BaseModel):
    ok: bool


class _FakeHTTPResponse:
    def __init__(self, body: dict[str, Any]) -> None:
        self._raw = json.dumps(body).encode("utf-8")

    def read(self) -> bytes:
        return self._raw

    def __enter__(self) -> _FakeHTTPResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None


def test_agent_thinking_budget_defaults_and_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CUBERELAY_AGENT_ENDPOINT", "https://example.invalid/v1")
    monkeypatch.setenv("CUBERELAY_AGENT_MODEL", "gemini-3.8-flash")
    monkeypatch.setenv("CUBERELAY_AGENT_API_KEY", "test-key")
    monkeypatch.delenv("CUBERELAY_AGENT_THINKING_BUDGET", raising=False)
    monkeypatch.delenv("CUBERELAY_AGENT_REASONING_EFFORT", raising=False)

    agent = OpenAICompatibleStructuredClient("AGENT")
    assert agent.thinking_budget == 1024
    assert agent.reasoning_effort is None

    monkeypatch.setenv("CUBERELAY_PERCEPTION_ENDPOINT", "https://example.invalid/v1")
    monkeypatch.setenv("CUBERELAY_PERCEPTION_MODEL", "gemini-3.5-flash-lite")
    monkeypatch.setenv("CUBERELAY_PERCEPTION_API_KEY", "test-key")
    monkeypatch.delenv("CUBERELAY_PERCEPTION_THINKING_BUDGET", raising=False)
    perc = OpenAICompatibleStructuredClient("PERCEPTION")
    assert perc.thinking_budget is None

    monkeypatch.setenv("CUBERELAY_AGENT_THINKING_BUDGET", "off")
    monkeypatch.setenv("CUBERELAY_AGENT_REASONING_EFFORT", "low")
    agent_off = OpenAICompatibleStructuredClient("AGENT")
    assert agent_off.thinking_budget is None
    assert agent_off.reasoning_effort == "low"

    monkeypatch.setenv("CUBERELAY_AGENT_THINKING_BUDGET", "512")
    agent_512 = OpenAICompatibleStructuredClient("AGENT")
    assert agent_512.thinking_budget == 512


@pytest.mark.parametrize(
    "usage_payload,expected_reasoning",
    [
        ({"prompt_tokens": 100, "completion_tokens": 20, "reasoning_tokens": 412}, 412),
        ({"prompt_tokens": 100, "completion_tokens": 20, "thoughtsTokenCount": 333}, 333),
        (
            {
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "completion_tokens_details": {"reasoning_tokens": 256},
            },
            256,
        ),
        (
            {
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "output_tokens_details": {"reasoning_tokens": 128},
            },
            128,
        ),
    ],
)
def test_agent_client_fallback_and_reasoning_tokens_parsing(
    monkeypatch: pytest.MonkeyPatch,
    usage_payload: dict[str, Any],
    expected_reasoning: int,
) -> None:
    monkeypatch.setenv("CUBERELAY_AGENT_ENDPOINT", "https://example.invalid/v1/chat/completions")
    monkeypatch.setenv("CUBERELAY_AGENT_MODEL", "gemini-3.8-flash")
    monkeypatch.setenv("CUBERELAY_AGENT_API_KEY", "test-key")
    monkeypatch.setenv("CUBERELAY_AGENT_THINKING_BUDGET", "1024")
    monkeypatch.setenv("CUBERELAY_AGENT_REASONING_EFFORT", "low")

    seen_payloads: list[dict[str, Any]] = []

    def fake_urlopen(req: Any, timeout: float = 0.0) -> _FakeHTTPResponse:
        body = json.loads(req.data.decode("utf-8"))
        seen_payloads.append(body)
        if len(seen_payloads) == 1:
            raise urllib.error.HTTPError(
                url=req.full_url,
                code=400,
                msg="Bad Request",
                hdrs=None,  # type: ignore[arg-type]
                fp=io.BytesIO(b'{"error":{"message":"Unsupported extra_body / reasoning_effort"}}'),
            )
        return _FakeHTTPResponse(
            {
                "id": "chatcmpl-test",
                "choices": [{"message": {"content": '{"ok": true}'}}],
                "usage": usage_payload,
            }
        )

    monkeypatch.setattr(dm, "_urlopen_without_environment_proxy", fake_urlopen)
    client = OpenAICompatibleStructuredClient("AGENT")
    parsed, call = client.generate("Ping", _DummySchema)

    assert parsed is not None and parsed.ok is True
    assert call.error is None
    assert call.input_tokens == 100
    assert call.output_tokens == 20
    assert call.reasoning_tokens == expected_reasoning
    assert len(seen_payloads) == 2
    assert seen_payloads[0]["reasoning_effort"] == "low"
    assert seen_payloads[0]["extra_body"] == {"google": {"thinking_config": {"thinking_budget": 1024}}}
    assert "reasoning_effort" not in seen_payloads[1]
    assert "extra_body" not in seen_payloads[1]


def test_decision_replay_runner_propagates_reasoning_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CUBERELAY_AGENT_ENDPOINT", "https://example.invalid/v1/chat/completions")
    monkeypatch.setenv("CUBERELAY_AGENT_MODEL", "gemini-3.8-flash")
    monkeypatch.setenv("CUBERELAY_AGENT_API_KEY", "test-key")

    case = build_m4d_replay_cases()[0]
    obs_id = case.to_agent_input().current_observation["observation_id"]
    agent_json = json.dumps(
        {
            "selected_action": "EXECUTE_STEP",
            "skill_id": "observe_workspace",
            "parameters": {},
            "reason_summary": "Need initial workspace localization before grasp.",
            "evidence_observation_ids": [obs_id],
            "expected_outcome": "localized cube pose",
            "completion_condition": "pose estimated",
            "confidence": 0.9,
            "need_replan": False,
        }
    )

    def fake_urlopen(req: Any, timeout: float = 0.0) -> _FakeHTTPResponse:
        return _FakeHTTPResponse(
            {
                "id": "chatcmpl-replay",
                "choices": [{"message": {"content": agent_json}}],
                "usage": {
                    "prompt_tokens": 1200,
                    "completion_tokens": 95,
                    "completion_tokens_details": {"reasoning_tokens": 310},
                },
            }
        )

    monkeypatch.setattr(dm, "_urlopen_without_environment_proxy", fake_urlopen)
    assert AgentActionDecision is not None
    runner = DecisionReplayRunner(mode="offline_fake", perception_client_factory=lambda: None, agent_client_factory=lambda: OpenAICompatibleStructuredClient("AGENT"))
    rec = runner.run_single(case, planner_group=PlannerGroup.LLM_AGENT_CV_ONLY, guide_mode=PromptGuideMode.GUIDE_MINIMAL)
    assert rec.model_call_status == "SUCCESS", (rec.reason_summary, rec.oracle_result.notes)
    assert rec.token_usage["input_tokens"] == 1200
    assert rec.token_usage["output_tokens"] == 95
    assert rec.token_usage["total_tokens"] == 1295
    assert rec.token_usage["reasoning_tokens"] == 310


def test_translate_x_010_mujoco_causal_audit_convergence(tmp_path: Path) -> None:
    pytest.importorskip("mujoco")
    import zipfile
    from cube_relay.experiment.perturbation import run_perturbation_suite

    suite = run_perturbation_suite(
        ["baseline", "translate_x_005", "translate_x_010", "vision_missing_negative_control"],
        seed=0,
        mission_type="INSPECT_CUBE",
        output_dir=tmp_path / "causal_m5a",
        width=240,
        height=180,
    )
    by_name = {r["condition"]: r for r in suite["results"]}
    for cond in ("baseline", "translate_x_005", "translate_x_010"):
        res = by_name[cond]
        assert res["mission_status"] == "COMPLETED", res
        assert res["reference_integrity_ok"] is True, res
        with zipfile.ZipFile(res["zip_path"], "r") as zf:
            manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
            assert manifest["reference_integrity"]["ok"] is True
            cv_rows = [json.loads(line) for line in zf.read("contact_verifications.jsonl").decode("utf-8").splitlines() if line.strip()]
            init_cv = [c for c in cv_rows if c.get("skill_name") == "initial_grasp"][0]
            assert init_cv["bilateral_contact_fraction"] >= 0.80, init_cv
    assert by_name["vision_missing_negative_control"]["mission_status"] == "FAILED"
    assert by_name["vision_missing_negative_control"]["reference_integrity_ok"] is True


def test_router_uses_fast_model_and_preserves_supported_thinking_switch(monkeypatch):
    from cube_relay.mission.relay_cognition import HRIDialogueInterpreter

    monkeypatch.setenv("CUBERELAY_PERCEPTION_ENDPOINT", "https://example.invalid/v1")
    monkeypatch.setenv("CUBERELAY_PERCEPTION_MODEL", "fast-perception")
    monkeypatch.setenv("CUBERELAY_PERCEPTION_API_KEY", "test-key")
    monkeypatch.setenv("CUBERELAY_PERCEPTION_THINKING_BUDGET", "1024")
    monkeypatch.delenv("CUBERELAY_ROUTER_MODEL", raising=False)
    assert HRIDialogueInterpreter().client.model == "fast-perception"
    monkeypatch.setenv("CUBERELAY_ROUTER_MODEL", "fast-router")
    client = HRIDialogueInterpreter().client
    payloads = []

    def gateway(req, timeout):
        payload = json.loads(req.data)
        payloads.append(payload)
        if "reasoning_effort" in payload:
            raise urllib.error.HTTPError(req.full_url, 422, "Unsupported", {},
                                         io.BytesIO(b'{"error":"unknown reasoning_effort"}'))
        return _FakeHTTPResponse({"choices": [{"message": {"content": '{"ok":true}'}}]})

    monkeypatch.setattr(dm, "_urlopen_without_environment_proxy", gateway)
    parsed, _ = client.generate("ping", _DummySchema)
    assert parsed.ok
    assert len(payloads) == 2
    assert payloads[0]["reasoning_effort"] == "none"
    assert "reasoning_effort" not in payloads[1]
    for payload in payloads:
        assert payload["model"] == "fast-router"
        assert payload["max_tokens"] == 256
        assert payload["extra_body"] == {"google": {"thinking_config": {"thinking_budget": 0}}}


@pytest.mark.parametrize(
    "configured_endpoint",
    [
        "https://api.deepseek.com",
        "https://api.deepseek.com/",
        "https://api.deepseek.com/chat/completions",
        "https://api.deepseek.com/chat/completions/",
    ],
)
def test_deepseek_endpoint_dedup_text_content_and_thinking_disabled(
    monkeypatch: pytest.MonkeyPatch,
    configured_endpoint: str,
) -> None:
    from cube_relay.mission.relay_cognition import HRIDialogueInterpreter

    monkeypatch.setenv("CUBERELAY_AGENT_ENDPOINT", configured_endpoint)
    monkeypatch.setenv("CUBERELAY_AGENT_MODEL", "deepseek-v4-pro")
    monkeypatch.setenv("CUBERELAY_AGENT_API_KEY", "test-key")
    monkeypatch.setenv("CUBERELAY_AGENT_THINKING", "disabled")
    monkeypatch.delenv("CUBERELAY_AGENT_THINKING_BUDGET", raising=False)
    monkeypatch.delenv("CUBERELAY_AGENT_REASONING_EFFORT", raising=False)

    seen_urls: list[str] = []
    seen_payloads: list[dict[str, Any]] = []

    def fake_urlopen(req: Any, timeout: float = 0.0) -> _FakeHTTPResponse:
        seen_urls.append(req.full_url)
        seen_payloads.append(json.loads(req.data.decode("utf-8")))
        return _FakeHTTPResponse({"choices": [{"message": {"content": '{"ok": true}'}}]})

    monkeypatch.setattr(dm, "_urlopen_without_environment_proxy", fake_urlopen)
    client = OpenAICompatibleStructuredClient("AGENT")
    parsed, call = client.generate("Ping JSON", _DummySchema)

    assert parsed is not None and parsed.ok is True
    assert call.error is None
    assert seen_urls == ["https://api.deepseek.com/chat/completions"]
    payload = seen_payloads[0]
    assert payload["messages"] == [{"role": "user", "content": "Ping JSON"}]
    assert payload["thinking"] == {"type": "disabled"}
    assert "extra_body" not in payload
    assert "reasoning_effort" not in payload

    # HRI router on deepseek-flash should also disable thinking cleanly without Google fields
    monkeypatch.setenv("CUBERELAY_PERCEPTION_ENDPOINT", configured_endpoint)
    monkeypatch.setenv("CUBERELAY_PERCEPTION_MODEL", "deepseek-flash")
    monkeypatch.setenv("CUBERELAY_PERCEPTION_API_KEY", "test-key")
    monkeypatch.setenv("CUBERELAY_PERCEPTION_THINKING", "enabled")
    monkeypatch.delenv("CUBERELAY_ROUTER_MODEL", raising=False)
    router_client = HRIDialogueInterpreter().client
    parsed_router, _ = router_client.generate("Route JSON", _DummySchema)
    assert parsed_router is not None and parsed_router.ok is True
    assert seen_urls[-1] == "https://api.deepseek.com/chat/completions"
    assert seen_payloads[-1]["thinking"] == {"type": "disabled"}
    assert "reasoning_effort" not in seen_payloads[-1]
    assert "extra_body" not in seen_payloads[-1]


def test_deepseek_thinking_enabled_multimodal_and_http_error_detail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CUBERELAY_PERCEPTION_ENDPOINT", "https://api.deepseek.com")
    monkeypatch.setenv("CUBERELAY_PERCEPTION_MODEL", "deepseek-flash")
    monkeypatch.setenv("CUBERELAY_PERCEPTION_API_KEY", "test-key")
    monkeypatch.setenv("CUBERELAY_PERCEPTION_THINKING", "enabled")
    monkeypatch.setenv("CUBERELAY_PERCEPTION_REASONING_EFFORT", "low")

    seen_payloads: list[dict[str, Any]] = []

    def fake_urlopen(req: Any, timeout: float = 0.0) -> _FakeHTTPResponse:
        seen_payloads.append(json.loads(req.data.decode("utf-8")))
        return _FakeHTTPResponse({"choices": [{"message": {"content": '{"ok": true}'}}]})

    monkeypatch.setattr(dm, "_urlopen_without_environment_proxy", fake_urlopen)
    client = OpenAICompatibleStructuredClient("PERCEPTION")
    parsed, call = client.generate("Inspect JSON", _DummySchema, "data:image/jpeg;base64,AAA")
    assert parsed is not None and parsed.ok is True
    assert seen_payloads[0]["thinking"] == {"type": "enabled"}
    assert seen_payloads[0]["reasoning_effort"] == "low"
    assert isinstance(seen_payloads[0]["messages"][0]["content"], list)
    assert seen_payloads[0]["messages"][0]["content"][1]["image_url"]["url"] == "data:image/jpeg;base64,AAA"

    def failing_urlopen(req: Any, timeout: float = 0.0) -> _FakeHTTPResponse:
        raise urllib.error.HTTPError(
            req.full_url,
            404,
            "Not Found",
            {},  # type: ignore[arg-type]
            io.BytesIO(b'{"error":{"message":"No route matched"}}'),
        )

    monkeypatch.setattr(dm, "_urlopen_without_environment_proxy", failing_urlopen)
    parsed_err, err_call = client.generate("Ping", _DummySchema)
    assert parsed_err is None
    assert err_call.error_code == "API_UNAVAILABLE"
    assert "https://api.deepseek.com/chat/completions" in (err_call.error or "")
    assert "No route matched" in (err_call.error or "")
