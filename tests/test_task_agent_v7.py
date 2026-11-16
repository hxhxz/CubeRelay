import json

import numpy as np
import pytest

from cube_relay.embodied.task_agent_v7 import (
    GeminiTaskPlanner,
    RuleTaskPlanner,
    TaskObservation,
    TaskPhase,
    TaskSkill,
    TaskSkillCandidate,
)


def observation(*skills: TaskSkill) -> TaskObservation:
    return TaskObservation(
        phase=TaskPhase.SEARCHING,
        step=1,
        allowed_skills=tuple(
            TaskSkillCandidate(skill=skill, reason="validated") for skill in skills
        ),
    )


def test_rule_task_planner_uses_same_validated_skill_contract() -> None:
    decision = RuleTaskPlanner().decide(
        observation(TaskSkill.OBSERVE_CUBE), np.zeros((4, 4, 3), dtype=np.uint8)
    )
    assert decision.skill == TaskSkill.OBSERVE_CUBE


def test_gemini_task_planner_rejects_skill_outside_allow_list(monkeypatch) -> None:
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return None
        def read(self):
            return json.dumps({
                "choices": [{"message": {"content": json.dumps({
                    "skill": "place_release", "reason": "unsafe phase jump"
                })}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 4},
            }).encode()

    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout: Response())
    planner = GeminiTaskPlanner("https://vlm.example/v1", "gemini-test", "secret")
    with pytest.raises(RuntimeError, match="disallowed Skill"):
        planner.decide(
            observation(TaskSkill.OBSERVE_CUBE),
            np.zeros((4, 4, 3), dtype=np.uint8),
        )
    assert planner.traces[-1].error is not None
    assert "secret" not in planner.traces[-1].model_dump_json()


def test_gemini_is_called_from_task_start_and_returns_allowed_skill(monkeypatch) -> None:
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return None
        def read(self):
            return json.dumps({
                "choices": [{"message": {"content": json.dumps({
                    "skill": "observe_cube", "reason": "start with active perception"
                })}}],
                "usageMetadata": {"promptTokenCount": 14, "candidatesTokenCount": 5},
            }).encode()

    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout: Response())
    planner = GeminiTaskPlanner("https://vlm.example/v1", "gemini-test", "secret")
    decision = planner.decide(
        observation(TaskSkill.OBSERVE_CUBE), np.zeros((4, 4, 3), dtype=np.uint8)
    )
    assert decision.skill == TaskSkill.OBSERVE_CUBE
    assert planner.traces[-1].input_tokens == 14
