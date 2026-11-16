from types import SimpleNamespace

import numpy as np
import pytest
from pydantic import ValidationError

from cube_relay.embodied.skill_agent import (
    ApproachGraspInput,
    FailureCode,
    PlannerDecision,
    SkillRuntime,
    TestLiftInput as LiftSkillInput,
    VLMAgentPlanner,
)
from cube_relay.embodied.vlm import HeuristicSceneVLM


def test_planner_contract_rejects_joint_actions_and_unbounded_offsets() -> None:
    with pytest.raises(ValidationError):
        PlannerDecision.model_validate({
            "candidate_index": 0,
            "tangent_offset_m": .01,
            "closure_offset_m": 0,
            "recovery": "abort",
            "reason": "unsafe",
            "robot_x_ctrl": .5,
        })
    with pytest.raises(ValidationError):
        ApproachGraspInput.model_validate({
            "detection": {
                "center_world_m": [0, 0, .66], "yaw_radians": 0,
                "confidence": 1, "pixel_count": 100,
            },
            "candidate_index": 0,
            "tangent_offset_m": .2,
            "closure_offset_m": 0,
        })


def test_test_lift_precondition_cannot_be_bypassed() -> None:
    backend = SimpleNamespace(data=SimpleNamespace(time=0.0))
    runtime = SkillRuntime(backend, HeuristicSceneVLM())
    output = runtime.test_lift(LiftSkillInput())
    assert not output.success
    assert output.failure_code == FailureCode.BILATERAL_CONTACT_REQUIRED
    assert runtime.logs[-1].preconditions == {"stable_bilateral_contact": False}


def test_vlm_planner_output_is_schema_validated() -> None:
    class UnsafeProvider:
        def decide(self, observation, rgb):
            return {"candidate_index": 0, "tangent_offset_m": .01,
                    "closure_offset_m": 0, "recovery": "abort", "reason": "x",
                    "joint_targets": [1, 2, 3]}

    planner = VLMAgentPlanner(UnsafeProvider())
    with pytest.raises(ValidationError):
        # Validation happens before any Skill/backend call.
        planner.decide(SimpleNamespace(), np.zeros((2, 2, 3), dtype=np.uint8))
