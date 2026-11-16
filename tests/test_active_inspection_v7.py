from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from cube_relay.embodied.active_inspection_v7 import ContinuousActiveInspector, NextBestViewPlanner
from cube_relay.embodied.perception_v2 import StickerStateFusion
from cube_relay.embodied.v2_types import FaceObservation


def test_fusion_preserves_unknown_and_reports_index_conflict() -> None:
    fusion = StickerStateFusion()
    fusion.add(FaceObservation("U", ("U",) + (None,) * 8, .8, 0,
                               (.8,) + (0.0,) * 8, "camera:a"))
    fusion.add(FaceObservation("U", ("R",) + (None,) * 8, .7, 1,
                               (.7,) + (0.0,) * 8, "camera:b"))
    assert fusion.observed_sticker_count == 1
    assert fusion.unknown_count == 53
    assert fusion.conflict_count == 1
    assert fusion.conflicting_indices == ("U0",)


def test_next_best_view_prefers_pitch_when_top_bottom_are_unknown() -> None:
    fusion = StickerStateFusion()
    for face in "FRBL":
        fusion.add(FaceObservation(face, (face,) * 9, .9, 0, source_view="controlled"))
    assert NextBestViewPlanner().choose(fusion, ()) == "pitch"


def test_next_best_view_prefers_yaw_when_side_faces_are_unknown() -> None:
    fusion = StickerStateFusion()
    for face in "UD":
        fusion.add(FaceObservation(face, (face,) * 9, .9, 0, source_view="controlled"))
    assert NextBestViewPlanner().choose(fusion, ()) == "yaw"


class _SuccessfulGraspAgent:
    def __init__(self, *args, **kwargs):
        pass

    def run(self, *args, **kwargs):
        return SimpleNamespace(final_success=True, attempts=1)


class _TraceBackend:
    def __init__(self) -> None:
        self.data = SimpleNamespace(time=0.0)
        self.last_observation_diagnostics = []
        self.reoriented = False

    def _advance(self, seconds: float = 0.1) -> None:
        self.data.time += seconds

    def task_align_scan_axes(self):
        self._advance()
        return {"success": True}

    def task_place_release(self):
        self._advance()
        return {"success": True, "released": True, "height_before_m": .8, "height_after_m": .66}

    def task_observe_released(self, frame_offset):
        self._advance()
        return [
            FaceObservation(face, (face,) * 9, .99, frame_offset + i, source_view=f"released:cam_{face}")
            for i, face in enumerate("URFLB")
        ]

    def task_regrasp(self, **kwargs):
        self._advance()
        return {"success": True, "attempts": [{"success": True, "bilateral_contact": True}]}

    def task_observe_held(self, frame_offset, **kwargs):
        self._advance()
        faces = "D" if self.reoriented else "RL"
        return [
            FaceObservation(face, (face,) * 9, .99, frame_offset + i, source_view=f"held:high_{face}")
            for i, face in enumerate(faces)
        ]

    def task_reorient(self, axis, radians, **kwargs):
        self._advance()
        self.reoriented = True
        return {
            "success": True,
            "reorient_target_radians": radians,
            "reorient_actual_radians": radians + .01,
            "reorient_error_radians": .01,
        }


def test_seed0_shape_trace_reports_unique_coverage_and_measured_rotation(monkeypatch) -> None:
    monkeypatch.setattr(
        "cube_relay.embodied.active_inspection_v7.FailureAwareSkillAgent",
        _SuccessfulGraspAgent,
    )
    live_events: list[dict] = []
    result = ContinuousActiveInspector(
        _TraceBackend(), "sequential", event_sink=live_events.append,
    ).run(0, reset_scene=False)

    assert result.success
    perception = [event for event in live_events if event["event_type"] == "perception"]
    assert [(event["evidence"]["unknown_before"], event["evidence"]["unknown_after"])
            for event in perception] == [(54, 9), (9, 9), (9, 0)]
    assert perception[0]["evidence"]["newly_observed"] == 45
    assert len(perception[0]["evidence"]["camera_ids"]) == 5
    assert perception[0]["evidence"]["camera_ids"][0] == "cam_U"
    assert sum(len(indices) for indices in perception[0]["evidence"]["camera_contributions"].values()) == 45

    rotation = next(event for event in live_events if event["name"] == "reorient_pitch_refresh")
    target = rotation["evidence"]["target_parameters"]["radians"]
    measured = rotation["evidence"]["measured_parameters"]["radians"]
    assert target == -np.pi / 2
    assert measured == target + .01
    assert target != measured
    assert any(event["source"] == "deterministic_policy" for event in live_events)


def test_failed_scan_identifies_real_failed_child_node(monkeypatch) -> None:
    class FailedGraspAgent(_SuccessfulGraspAgent):
        def run(self, *args, **kwargs):
            return SimpleNamespace(final_success=False, attempts=({"success": False},))

    monkeypatch.setattr(
        "cube_relay.embodied.active_inspection_v7.FailureAwareSkillAgent",
        FailedGraspAgent,
    )
    events: list[dict] = []
    result = ContinuousActiveInspector(
        _TraceBackend(), "sequential", event_sink=events.append,
    ).run(0, reset_scene=False)
    assert not result.success
    assert result.first_failure_stage == "initial_grasp"
    failed = [event for event in events if event["status"] == "FAILED"]
    assert failed[0]["name"] == "initial_grasp"
    assert failed[0]["source"] == "physical_skill"
