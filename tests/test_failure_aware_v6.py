import json

import numpy as np
import pytest
from pydantic import ValidationError

from cube_relay.embodied.failure_aware_v6 import (
    ContactSnapshot,
    FailureAwareDecision,
    FailureAwareObservation,
    GraspAttemptMemory,
    GraspAttemptRecord,
    OpenAICompatibleFailureAwareVLM,
)
from cube_relay.embodied.v2_types import CubeDetection, GraspCandidate, SceneSemantics


def record(**updates) -> GraspAttemptRecord:
    values = dict(
        attempt=1,
        candidate_index=1,
        face_pair="local_x_faces",
        tangent_offset_m=.01,
        closure_offset_m=-.015,
        cube_world_position_m=(.1, .2, .66),
        cube_world_yaw_rad=.2,
        gripper_target_world_position_m=(.11, .185, .66),
        gripper_target_world_yaw_rad=.2 + np.pi / 2,
        gripper_pose_in_object_m=(.01, -.015, 0),
        gripper_yaw_in_object_rad=np.pi / 2,
        contact=ContactSnapshot(),
        failure_code="BILATERAL_CONTACT_NOT_ESTABLISHED",
        success=False,
        repeated_geometry=False,
        image_sha256="abc",
    )
    values.update(updates)
    return GraspAttemptRecord(**values)


def test_attempt_memory_uses_object_and_world_geometry() -> None:
    memory = GraspAttemptMemory()
    memory.add(record())
    assert memory.geometrically_similar(
        cube_world_position_m=(.101, .2, .66),
        cube_world_yaw_rad=.21,
        face_pair="local_x_faces",
        gripper_pose_in_object_m=(.011, -.015, 0),
        gripper_yaw_in_object_rad=np.pi / 2,
    )
    assert not memory.geometrically_similar(
        cube_world_position_m=(.14, .2, .66),
        cube_world_yaw_rad=.21,
        face_pair="local_x_faces",
        gripper_pose_in_object_m=(.011, -.015, 0),
        gripper_yaw_in_object_rad=np.pi / 2,
    )
    assert not memory.geometrically_similar(
        cube_world_position_m=(.101, .2, .66),
        cube_world_yaw_rad=.21,
        face_pair="local_x_faces",
        gripper_pose_in_object_m=(-.01, .015, 0),
        gripper_yaw_in_object_rad=np.pi / 2,
    )


def test_failure_aware_decision_rejects_joint_commands() -> None:
    with pytest.raises(ValidationError):
        FailureAwareDecision.model_validate({
            "action": "select", "option_id": "c1_t+10_c-15", "reason": "x",
            "joint_targets": [0, 1],
        })


@pytest.mark.parametrize(
    ("provider_action", "expected_action", "option_id"),
    [
        ("reobserve", "reobserve", None),
        ("execute_grasp", "select", "c1_t+0_c+0"),
    ],
)
def test_real_vlm_adapter_is_traced_and_schema_validated(
    monkeypatch, provider_action, expected_action, option_id
) -> None:
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return None
        def read(self):
            return json.dumps({
                "choices": [{"message": {"content": json.dumps({
                    "action": provider_action,
                    "option_id": option_id,
                    "reason": "auditable high-level choice",
                })}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 10},
            }).encode()

    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout: Response())
    provider = OpenAICompatibleFailureAwareVLM(
        endpoint="https://vlm.example/v1", model="real-vision-model", api_key="secret",
        input_cost_per_million=2, output_cost_per_million=8,
    )
    observation = FailureAwareObservation(
        attempt=1,
        semantics=SceneSemantics(True, .9, "cube", "test"),
        detection=CubeDetection((0, 0, .66), 0, 1, 100),
        options=(), memory=(), failure_history=(), image_shape=(4, 4, 3),
        image_sha256="image-hash",
    )
    decision, trace = provider.decide(
        observation, np.zeros((4, 4, 3), dtype=np.uint8)
    )
    assert decision.action == expected_action
    assert decision.option_id == option_id
    assert trace.model == "real-vision-model"
    assert trace.input_tokens == 100 and trace.output_tokens == 10
    assert trace.cost_usd == pytest.approx(.00028)
    assert "secret" not in trace.model_dump_json()
