"""Explicit runtime ground-truth access boundary & provenance guard (Section XII)."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from typing import Iterator

from .schema import DataSourceKind


class TruthAccessCategory(str, Enum):
    EXPERIMENT_INIT_ALLOWED = "EXPERIMENT_INIT_ALLOWED"
    AUDIT_EVALUATION_ALLOWED = "AUDIT_EVALUATION_ALLOWED"
    RUNTIME_LOCALIZATION_FORBIDDEN = "RUNTIME_LOCALIZATION_FORBIDDEN"
    ROBOT_PROPRIOCEPTION_ALLOWED = "ROBOT_PROPRIOCEPTION_ALLOWED"


@dataclass(frozen=True, slots=True)
class TruthAccessViolation(RuntimeError):
    category: TruthAccessCategory
    accessor: str
    context: str

    def __str__(self) -> str:
        return (
            f"Ground-truth leakage boundary violation [{self.category.value}] "
            f"at {self.accessor} during {self.context}"
        )


class TruthAccessBoundary:
    """Tracks execution phase so runtime perception/grasp-planning never reads cube truth."""

    def __init__(self, *, strict: bool = True) -> None:
        self.strict = strict
        self._stack: list[tuple[TruthAccessCategory, str]] = []
        self.audit_access_log: list[dict[str, str]] = []

    @property
    def current_category(self) -> TruthAccessCategory | None:
        return self._stack[-1][0] if self._stack else None

    @property
    def current_context(self) -> str:
        return self._stack[-1][1] if self._stack else "unspecified"

    @contextmanager
    def scope(self, category: TruthAccessCategory, context: str) -> Iterator[None]:
        self._stack.append((category, context))
        try:
            yield
        finally:
            self._stack.pop()

    def assert_cube_truth_allowed(self, accessor: str) -> None:
        cat = self.current_category
        if cat == TruthAccessCategory.RUNTIME_LOCALIZATION_FORBIDDEN:
            raise TruthAccessViolation(cat, accessor, self.current_context)
        self.audit_access_log.append({
            "category": cat.value if cat else "UNSCOPED",
            "accessor": accessor,
            "context": self.current_context,
            "source_kind": DataSourceKind.SIMULATOR_GROUND_TRUTH_AUDIT_ONLY.value,
        })


# Registry mapping source code symbols / helpers to their provenance category.
PROVENANCE_CLASSIFICATION: dict[str, dict[str, str]] = {
    "MuJoCoEmbodiedBackend.reset_random": {
        "category": TruthAccessCategory.EXPERIMENT_INIT_ALLOWED.value,
        "source_kind": DataSourceKind.SIMULATOR_GROUND_TRUTH_AUDIT_ONLY.value,
        "reason": "Initializes free cube qpos and scramble colors before episode start.",
    },
    "MuJoCoEmbodiedBackend.reset_with_perturbation": {
        "category": TruthAccessCategory.EXPERIMENT_INIT_ALLOWED.value,
        "source_kind": DataSourceKind.SIMULATOR_GROUND_TRUTH_AUDIT_ONLY.value,
        "reason": "Controlled initial cube position perturbation before initial observation.",
    },
    "MuJoCoEmbodiedBackend.capture_rgbd": {
        "category": TruthAccessCategory.RUNTIME_LOCALIZATION_FORBIDDEN.value,
        "source_kind": DataSourceKind.SENSOR_RGB.value,
        "reason": "Renders RGB-D sensor frame only; cube truth must not affect detection.",
    },
    "DeterministicCubeLocalizer.locate": {
        "category": TruthAccessCategory.RUNTIME_LOCALIZATION_FORBIDDEN.value,
        "source_kind": DataSourceKind.VISUAL_POSE_ESTIMATE.value,
        "reason": "Estimates 3D center and yaw strictly from RGB pixels, metric depth, and calibration.",
    },
    "DeterministicCubePose6DEstimator.estimate": {
        "category": TruthAccessCategory.RUNTIME_LOCALIZATION_FORBIDDEN.value,
        "source_kind": DataSourceKind.VISUAL_POSE_ESTIMATE.value,
        "reason": "Estimates 6D pose strictly from mapped face corners and RGB-D calibration.",
    },
    "MuJoCoEmbodiedBackend.generate_grasp_candidates": {
        "category": TruthAccessCategory.RUNTIME_LOCALIZATION_FORBIDDEN.value,
        "source_kind": DataSourceKind.CONTROLLER_STATE.value,
        "reason": "Plans grasp candidates from visual detection + robot proprioceptive wrist yaw.",
    },
    "MuJoCoEmbodiedBackend.select_grasp_candidate": {
        "category": TruthAccessCategory.RUNTIME_LOCALIZATION_FORBIDDEN.value,
        "source_kind": DataSourceKind.CONTROLLER_STATE.value,
        "reason": "Selects feasible grasp candidate without accessing cube body pose.",
    },
    "MuJoCoEmbodiedBackend.gripper_axes_world": {
        "category": TruthAccessCategory.ROBOT_PROPRIOCEPTION_ALLOWED.value,
        "source_kind": DataSourceKind.ROBOT_PROPRIOCEPTION.value,
        "reason": "Reads robot forward kinematics (gripper body xpos/xmat) and joint encoders.",
    },
    "MuJoCoEmbodiedBackend._finger_contact_forces": {
        "category": TruthAccessCategory.ROBOT_PROPRIOCEPTION_ALLOWED.value,
        "source_kind": DataSourceKind.ROBOT_PROPRIOCEPTION.value,
        "reason": "Reads finger pad contact presence and solved normal forces.",
    },
    "MuJoCoEmbodiedBackend._contact_debug_sample": {
        "category": TruthAccessCategory.AUDIT_EVALUATION_ALLOWED.value,
        "source_kind": DataSourceKind.SIMULATOR_GROUND_TRUTH_AUDIT_ONLY.value,
        "reason": "Records simulator cube pose/slip strictly for post-hoc audit & contact telemetry.",
    },
    "ExperimentRecorder.record_audit_pose": {
        "category": TruthAccessCategory.AUDIT_EVALUATION_ALLOWED.value,
        "source_kind": DataSourceKind.SIMULATOR_GROUND_TRUTH_AUDIT_ONLY.value,
        "reason": "Writes isolated audit_only_poses.csv; never read by perception or planning.",
    },
}
