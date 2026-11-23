"""M4-B independent perception/planning provider and causal decision tests."""

from __future__ import annotations

import base64
import io
import json
import os
from typing import Any

import numpy as np
from PIL import Image
import pytest
from pydantic import ValidationError

from cube_relay.mission import (
    AgentActionDecision,
    AgentObservation,
    AgentPlanningProvider,
    DualModelDecisionClient,
    FakeStructuredModelClient,
    LLMAgentDecisionPolicy,
    MissionState,
    MissionStatus,
    MissionType,
    SemanticSceneObservation,
    SkillRegistry,
    SimulationSession,
    VLMPerceptionProvider,
)


def _image_url(color: tuple[int, int, int]) -> str:
    pixels = np.full((24, 32, 3), color, dtype=np.uint8)
    buf = io.BytesIO()
    Image.fromarray(pixels).save(buf, format="JPEG")
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _observation(image: str, *, obs_id: str = "obs-m4b-1", frame_id: str = "frm-m4b-1") -> AgentObservation:
    return AgentObservation(
        observation_id=obs_id,
        mission_id="msn-m4b",
        session_id="sess-m4b",
        sim_time=1.0,
        frame_id=frame_id,
        camera_id="overhead",
        rgb_image_data_url=image,
        camera_metadata={"frame_source": "REAL_MUJOCO_RENDERER"},
        observed_facelets="?" * 9 + "W" * 45,
        observed_count=45,
        unknown_facelet_indices=list(range(9)),
    )


def _mission() -> MissionState:
    return MissionState(
        mission_id="msn-m4b",
        session_id="sess-m4b",
        mission_type=MissionType.INSPECT_CUBE,
        user_goal="inspect cube",
        success_criteria="54 observed",
        status=MissionStatus.OBSERVING,
        created_at="00:00:00",
    )


def test_m4b_schemas_are_strict_and_separate() -> None:
    semantic = SemanticSceneObservation.model_validate({
        "observation_id": "obs-1", "frame_id": "frm-1", "camera_id": "overhead",
        "cube_visible": True, "cube_relation_to_gripper": "released on table",
        "support_relation": "supported by table", "visible_regions": ["top", "sides"],
        "occluded_regions": ["bottom"], "information_gaps": ["bottom stickers"],
        "suggested_observations": ["regrasp then pitch"], "visual_conflicts": [],
        "confidence": 0.9, "summary": "bottom is occluded",
    })
    assert semantic.occluded_regions == ["bottom"]
    with pytest.raises(ValidationError):
        SemanticSceneObservation.model_validate({**semantic.model_dump(), "skill_id": "regrasp_cube"})

    decision = AgentActionDecision.model_validate({
        "selected_action": "REGRASP", "skill_id": "regrasp_cube", "parameters": {},
        "reason_summary": "bottom is occluded", "evidence_observation_ids": ["obs-1"],
        "expected_outcome": "hold cube", "completion_condition": "cube held",
        "confidence": 0.85, "need_replan": False,
    })
    assert decision.skill_id == "regrasp_cube"


def test_semantic_observation_changes_independent_agent_action() -> None:
    released_image = _image_url((180, 40, 40))
    held_image = _image_url((40, 180, 40))

    def perceive(_prompt: str, image: str | None) -> dict[str, Any]:
        held = image == held_image
        return {
            "observation_id": "obs-m4b-1", "frame_id": "frm-m4b-1", "camera_id": "overhead",
            "cube_visible": True,
            "cube_relation_to_gripper": "held between fingers" if held else "released on table",
            "support_relation": "gripper supported" if held else "table supported",
            "visible_regions": ["top", "sides"], "occluded_regions": ["bottom"],
            "information_gaps": ["bottom stickers"],
            "suggested_observations": ["pitch reorientation" if held else "regrasp"],
            "visual_conflicts": [], "confidence": 0.95,
            "summary": "held" if held else "released",
        }

    def plan(prompt: str, image: str | None) -> dict[str, Any]:
        assert image is None, "Agent planning model must never receive RGB bytes"
        payload = json.loads(prompt.split("\n", 1)[1])
        semantic = payload["semantic_scene_observation"]
        held = semantic["cube_relation_to_gripper"].startswith("held")
        return {
            "selected_action": "REORIENT" if held else "REGRASP",
            "skill_id": "reorient_cube" if held else "regrasp_cube",
            "parameters": {"axis": "pitch", "degrees": -90} if held else {},
            "reason_summary": semantic["summary"],
            "evidence_observation_ids": [semantic["observation_id"]],
            "expected_outcome": "reveal hidden face", "completion_condition": "new face visible",
            "confidence": 0.9, "need_replan": False,
        }

    perception_client = FakeStructuredModelClient("perception", perceive, model="vision-model-A")
    agent_client = FakeStructuredModelClient("agent", plan, model="planner-model-B")
    dual = DualModelDecisionClient(
        VLMPerceptionProvider(perception_client), AgentPlanningProvider(agent_client)
    )
    policy = LLMAgentDecisionPolicy(client=dual)
    registry = SkillRegistry()
    mission = _mission()
    state = {
        "simulation_initialized": True, "cube_localized": True, "scan_attempted": True,
        "cube_released_on_table": True, "cube_held_in_gripper": True,
    }

    first = policy.select_next_action(
        mission, policy.create_plan(mission, registry, plan_id="p1"), registry, state, None,
        agent_observation=_observation(released_image),
    )
    assert first.skill_id == "regrasp_cube"

    second = policy.select_next_action(
        mission, policy.create_plan(mission, registry, plan_id="p2"), registry, state, None,
        agent_observation=_observation(held_image),
    )
    assert second.skill_id == "reorient_cube"
    assert perception_client.calls[0]["image_data_url"] == released_image
    assert agent_client.calls[0]["image_data_url"] is None
    assert perception_client.model != agent_client.model
    assert dual.has_completed_valid_call is True


def test_agent_must_cite_current_semantic_observation() -> None:
    perception = FakeStructuredModelClient("perception", lambda _p, _i: {
        "observation_id": "obs-m4b-1", "frame_id": "frm-m4b-1", "camera_id": "overhead",
        "cube_visible": True, "cube_relation_to_gripper": "released", "support_relation": "table",
        "visible_regions": [], "occluded_regions": [], "information_gaps": [],
        "suggested_observations": [], "visual_conflicts": [], "confidence": 0.8, "summary": "visible",
    })
    agent = FakeStructuredModelClient("agent", lambda _p, _i: {
        "selected_action": "OBSERVE", "skill_id": "observe_visible_faces", "parameters": {},
        "reason_summary": "observe", "evidence_observation_ids": ["obs-does-not-exist"],
        "expected_outcome": "new evidence", "completion_condition": "observed", "confidence": 0.8,
        "need_replan": False,
    })
    policy = LLMAgentDecisionPolicy(
        client=DualModelDecisionClient(VLMPerceptionProvider(perception), AgentPlanningProvider(agent))
    )
    registry = SkillRegistry()
    result = policy.select_next_action(
        _mission(), policy.create_plan(_mission(), registry, plan_id="p-bad"), registry,
        {"simulation_initialized": True, "cube_localized": True}, None,
        agent_observation=_observation(_image_url((10, 10, 10))),
    )
    assert result.decision_kind == "FAIL_MISSION"
    assert result.failure_code == "EVIDENCE_REFERENCE_INVALID"


def test_m4b_real_mujoco_two_model_closed_loop() -> None:
    if os.environ.get("CUBERELAY_SKIP_GL_TESTS", "0") == "1":
        pytest.skip("GL tests disabled")

    def perceive(prompt: str, _image: str | None) -> dict[str, Any]:
        meta = json.loads(prompt.split("\n", 1)[1])
        return {
            "observation_id": meta["observation_id"], "frame_id": meta["frame_id"],
            "camera_id": meta["camera_id"], "cube_visible": True,
            "cube_relation_to_gripper": "current image requires task-state fusion",
            "support_relation": "observable support retained", "visible_regions": ["camera-visible cube"],
            "occluded_regions": ["unseen face"], "information_gaps": ["remaining unknown stickers"],
            "suggested_observations": ["use safe inspection skill"], "visual_conflicts": [],
            "confidence": 0.9, "summary": "cube visible with a potentially occluded face",
        }

    def plan(prompt: str, image: str | None) -> dict[str, Any]:
        assert image is None
        outer = json.loads(prompt.split("\n", 1)[1])
        base = outer["planner_context"]
        ctx = json.loads(base.split("\n", 1)[1])
        st = ctx["observable_state"]
        obs_id = outer["semantic_scene_observation"]["observation_id"]
        if not st["cube_localized"]:
            skill, params = "observe_workspace", {"camera_name": "overhead"}
        elif not st["scan_attempted"]:
            skill, params = "place_and_release", {}
        elif not st["all_54_facelets_observed"]:
            latest = ctx["observation_metadata"]["latest_skill_result"] or {}
            if st["observed_count"] == 0:
                skill, params = "observe_visible_faces", {"view_mode": "released"}
            elif st["cube_released_on_table"]:
                skill, params = "regrasp_cube", {}
            elif latest.get("skill_id") == "regrasp_cube":
                skill, params = "reorient_cube", {"axis": "pitch", "degrees": -90}
            else:
                skill, params = "observe_visible_faces", {"view_mode": "held"}
        elif not st["finish_inspection_done"]:
            skill, params = "finish_inspection", {}
        elif not st["cube_state_validated"]:
            skill, params = "validate_cube_state", {}
        else:
            skill, params = "FINISH", {}
        return {
            "selected_action": skill, "skill_id": None if skill == "FINISH" else skill,
            "parameters": params, "reason_summary": f"semantic+CV selected {skill}",
            "evidence_observation_ids": [obs_id], "expected_outcome": "advance inspection",
            "completion_condition": "skill feedback confirms progress", "confidence": 0.9,
            "need_replan": False,
        }

    p_client = FakeStructuredModelClient("perception", perceive, model="fake-vision-A")
    a_client = FakeStructuredModelClient("agent", plan, model="fake-planner-B")
    policy = LLMAgentDecisionPolicy(
        client=DualModelDecisionClient(VLMPerceptionProvider(p_client), AgentPlanningProvider(a_client))
    )
    session = SimulationSession(seed=0, width=320, height=240, planner=policy)
    try:
        snapshot = session.run_mission(MissionType.INSPECT_CUBE, seed=0)
        assert snapshot["mission"]["status"] == "COMPLETED", json.dumps(
            {"mission": snapshot["mission"], "agent": snapshot["agent_state"],
             "skills": snapshot["skill_executions"]}, ensure_ascii=False
        )
        assert snapshot["frame_source"] == "REAL_MUJOCO_RENDERER"
        assert len(p_client.calls) >= 2 and len(a_client.calls) >= 2
        assert all(call["image_data_url"] is not None for call in p_client.calls)
        assert all(call["image_data_url"] is None for call in a_client.calls)
        assert len({event["input_frame_ids"][0] for event in snapshot["decision_events"]
                    if event["event_type"] == "VLM_INFERENCE_COMPLETED"}) >= 2
        assert any(execution["skill_id"] == "reorient_cube" for execution in snapshot["skill_executions"])
        assert snapshot["agent_state"]["perception_model_name"] == "fake-vision-A"
        assert snapshot["agent_state"]["agent_model_name"] == "fake-planner-B"
        assert snapshot["agent_state"]["latest_semantic_observation"] is not None
    finally:
        session.close()
