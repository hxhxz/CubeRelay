"""Skill Registry & explicit physical capability boundary checker.

Strictly distinguishes:
- Symbolic move planning capability (CubeEngine / CubeSolver supports all 18 moves)
- Physical execution capability in MuJoCo (only contact-driven single clockwise U turn)
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from cube_relay.cube.state import LEGAL_MOVES


class SkillDescriptor(BaseModel):
    """Capability metadata for a single robot or perception/planning Skill."""

    model_config = ConfigDict(extra="forbid")

    skill_id: str
    title: str
    description: str
    category: str
    implemented: bool
    is_physical_action: bool
    required_preconditions: list[str] = Field(default_factory=list)
    required_observations: list[str] = Field(default_factory=list)
    supported_parameters: dict[str, str] = Field(default_factory=dict)
    supported_physical_actions: list[str] = Field(default_factory=list)
    expected_outputs: list[str] = Field(default_factory=list)
    verification_method: str = ""
    failure_codes: list[str] = Field(default_factory=list)


class PhysicalMoveCapability(BaseModel):
    """Answer to CanExecutePhysicalMove(move, scene_state)."""

    model_config = ConfigDict(extra="forbid")

    move: str
    supported: bool
    skill_id: str | None = None
    symbolic_supported: bool
    physical_model_supported: bool
    unsupported_reason: str | None = None
    required_preconditions: list[str] = Field(default_factory=list)
    missing_preconditions: list[str] = Field(default_factory=list)


class CapabilityRegistrySnapshot(BaseModel):
    """Serializable view of registered skills and physical boundaries for frontend & VLM."""

    model_config = ConfigDict(extra="forbid")

    skills: list[SkillDescriptor]
    symbolic_supported_moves: list[str]
    physical_supported_moves: list[str]
    physical_limitations_summary: str


class SkillRegistry:
    """Registry declaring real implemented Skills and exact physical boundaries."""

    def __init__(self) -> None:
        self._skills: dict[str, SkillDescriptor] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        defaults = [
            SkillDescriptor(
                skill_id="observe_workspace",
                title="工作站观测与魔方定位",
                description="通过固定顶部 RGB-D 相机捕获图像并使用 DeterministicCubeLocalizer 定位魔方三维中心与偏航角。",
                category="PERCEPTION",
                implemented=True,
                is_physical_action=False,
                required_preconditions=["simulation_initialized"],
                required_observations=["overhead_rgbd"],
                supported_parameters={"camera_name": "str (default: overhead)"},
                supported_physical_actions=[],
                expected_outputs=["cube_visible", "center_world_m", "yaw_radians", "observation_ref"],
                verification_method="DeterministicCubeLocalizer pixel cluster + metric depth median check",
                failure_codes=["CUBE_NOT_LOCALIZED", "DEPTH_UNAVAILABLE"],
            ),
            SkillDescriptor(
                skill_id="active_six_face_scan",
                title="六面主动扫描与贴片融合",
                description="调用 ContinuousActiveInspector 控制机械臂完成抓取、对齐扫描、释放观测与重抓翻转，融合 54 格贴片颜色。",
                category="PERCEPTION_AND_MANIPULATION",
                implemented=True,
                is_physical_action=True,
                required_preconditions=["simulation_initialized", "cube_localized"],
                required_observations=["overhead_rgbd", "scan_cameras_rgbd", "inspection_cameras_rgbd"],
                supported_parameters={"seed": "int", "mode": "sequential | nbv"},
                supported_physical_actions=["GRASP", "ALIGN_SCAN_AXES", "PLACE_RELEASE", "REGRASP", "REORIENT"],
                expected_outputs=["reconstructed_facelets", "observed_count", "unknown_count", "conflict_count"],
                verification_method="StickerStateFusion 54-cell coverage and multi-view conflict check",
                failure_codes=[
                    "INITIAL_GRASP_FAILED",
                    "ALIGN_SCAN_AXES_FAILED",
                    "PLACE_RELEASE_FAILED",
                    "REGRASP_FAILED",
                    "REORIENT_FAILED",
                    "SCAN_INCOMPLETE",
                ],
            ),
            SkillDescriptor(
                skill_id="validate_cube_state",
                title="魔方状态拓扑合法性校验",
                description="对已观测贴片进行 54 格完整性、中心块唯一性与 Kociemba 群论可解性校验，不修改任何仿真状态。",
                category="VALIDATION",
                implemented=True,
                is_physical_action=False,
                required_preconditions=["scan_attempted"],
                required_observations=["fused_54_facelets"],
                supported_parameters={},
                supported_physical_actions=[],
                expected_outputs=["validation_status", "legal", "solvable"],
                verification_method="StateValidator (count/color parity + Kociemba solvability)",
                failure_codes=["INCOMPLETE_OBSERVATION", "UNRESOLVED_CONFLICTS", "INVALID_CUBE_STATE"],
            ),
            SkillDescriptor(
                skill_id="compute_symbolic_plan",
                title="符号求解与期望状态计算",
                description="基于合法 54 格状态运行 Kociemba 求解器计算符号求解序列或单步期望目标（仅符号推理，不驱动物理关节）。",
                category="SYMBOLIC_PLANNING",
                implemented=True,
                is_physical_action=False,
                required_preconditions=["cube_state_validated"],
                required_observations=["validated_facelets"],
                supported_parameters={"target_mode": "solve | single_u_expectation"},
                supported_physical_actions=[],
                expected_outputs=["symbolic_moves", "expected_facelets_after_u"],
                verification_method="CubeEngine symbolic forward check against SOLVED_FACELETS",
                failure_codes=["INVALID_CUBE_STATE", "SOLVER_FAILED"],
            ),
            SkillDescriptor(
                skill_id="check_physical_capability",
                title="物理执行能力边界核查",
                description="逐动作核对符号规划序列是否具备对应 MuJoCo 物理模型、夹具接触条件与前置约束。",
                category="CAPABILITY_GATE",
                implemented=True,
                is_physical_action=False,
                required_preconditions=["symbolic_plan_available"],
                required_observations=[],
                supported_parameters={"moves": "list[str]"},
                supported_physical_actions=[],
                expected_outputs=["all_supported", "blocked_move", "blocked_moves", "blocked_reason"],
                verification_method="SkillRegistry.CanExecutePhysicalMove audit per planned move",
                failure_codes=["CAPABILITY_UNSUPPORTED", "PRECONDITION_MISSING"],
            ),
            SkillDescriptor(
                skill_id="execute_physical_u_turn",
                title="单层 U 面接触式物理转动",
                description="通过 ContactUTurn 将魔方搬运至旋转工位，底座夹持下两层，顶部外置夹具接触驱动 u_layer_joint 顺时针旋转 90°（-pi/2 rad）。",
                category="PHYSICAL_MANIPULATION",
                implemented=True,
                is_physical_action=True,
                required_preconditions=[
                    "physical_u_scene_enabled",
                    "cube_localized_and_scanned",
                    "turn_station_available",
                    "single_u_turn_not_yet_consumed",
                ],
                required_observations=["inspection_side_rgbd", "overhead_rgbd"],
                supported_parameters={"move": "Literal['U'] (fixed +90 deg clockwise, -pi/2 rad)"},
                supported_physical_actions=["U"],
                expected_outputs=["actual_delta_rad", "layer_error_rad", "base_displacement_m", "contact_evidence"],
                verification_method="Joint angle error < 0.03 rad, paired pad normal force > 0.05 N, zero slip & zero u_brake torque",
                failure_codes=[
                    "UPRIGHT_FAILED",
                    "VISUAL_POSE_MISSING",
                    "TRANSPORT_SAFETY_STOP",
                    "DOCK_SUPPORT_MISSING",
                    "BASE_CONTACT_MISSING",
                    "LAYER_CONTACT_MISSING",
                    "CONTACT_TURN_SAFETY_STOP",
                    "LAYER_OR_ROTOR_NOT_SETTLED",
                    "POST_TURN_SUPPORT_MISSING",
                ],
            ),
            SkillDescriptor(
                skill_id="verify_post_turn_state",
                title="转面后独立相机视觉复核",
                description="机械臂与旋转夹具退避后重新调用多视角 RGB-D 观测，对比物理转动后的实测贴片与符号预期（含 U 层相关 21 格）。",
                category="VERIFICATION",
                implemented=True,
                is_physical_action=False,
                required_preconditions=["physical_u_turn_executed", "turn_station_cleared"],
                required_observations=["released_scan_cameras_rgbd"],
                supported_parameters={},
                supported_physical_actions=[],
                expected_outputs=["affected_21_verified", "observed_state", "differences", "conflicts"],
                verification_method="compare_observations against expected state for all 21 U-affected facelets",
                failure_codes=["VISUAL_MISMATCH", "UNVERIFIED_CONFLICT", "UNVERIFIED_INSUFFICIENT_EVIDENCE"],
            ),
            SkillDescriptor(
                skill_id="execute_physical_non_u_turn",
                title="任意六面/逆向/180° 物理转层",
                description="尚未实现：当前 MuJoCo 场景仅建模单层 u_layer_joint 被动铰链与单一顶部旋转头，不支持 R/F/L/B/D、U'、U2 或多面连续机械翻转夹持。",
                category="PHYSICAL_MANIPULATION",
                implemented=False,
                is_physical_action=True,
                required_preconditions=["full_26_cubie_model", "multi_face_reindexing_fixture"],
                required_observations=["multi_view_rgbd"],
                supported_parameters={},
                supported_physical_actions=[],
                expected_outputs=[],
                verification_method="未实现",
                failure_codes=["CAPABILITY_NOT_IMPLEMENTED"],
            ),
        ]
        for skill in defaults:
            self._skills[skill.skill_id] = skill

    def list_skills(self) -> list[SkillDescriptor]:
        return list(self._skills.values())

    def get(self, skill_id: str) -> SkillDescriptor | None:
        return self._skills.get(skill_id)

    def validate_parameters(self, skill_id: str, params: dict[str, Any] | None = None) -> tuple[bool, str | None]:
        descriptor = self.get(skill_id)
        if descriptor is None:
            return False, f"未注册的 Skill: {skill_id}"
        if not descriptor.implemented:
            return False, f"Skill [{skill_id}] 尚未实现: {descriptor.description}"
        params = params or {}
        if skill_id == "execute_physical_u_turn":
            move = params.get("move", "U")
            if move != "U":
                return False, f"execute_physical_u_turn 仅支持单次顺时针 'U' 动作，拒绝参数 move={move!r}"
        return True, None

    def check_preconditions(
        self,
        skill_id: str,
        scene_state: dict[str, Any] | None = None,
    ) -> tuple[bool, list[str]]:
        descriptor = self.get(skill_id)
        if descriptor is None:
            return False, [f"unknown_skill:{skill_id}"]
        state = scene_state or {}
        missing: list[str] = []
        for pre in descriptor.required_preconditions:
            if pre == "simulation_initialized" and not state.get("simulation_initialized", True):
                missing.append(pre)
            elif pre == "cube_localized" and not state.get("cube_localized", False):
                missing.append(pre)
            elif pre == "scan_attempted" and not state.get("scan_attempted", False):
                missing.append(pre)
            elif pre == "cube_state_validated" and not state.get("cube_state_validated", False):
                missing.append(pre)
            elif pre == "symbolic_plan_available" and not state.get("symbolic_plan_available", False):
                missing.append(pre)
            elif pre == "physical_u_scene_enabled" and not state.get("physical_u_scene_enabled", False):
                missing.append(pre)
            elif pre == "cube_localized_and_scanned" and not state.get("cube_localized_and_scanned", False):
                missing.append(pre)
            elif pre == "turn_station_available" and not state.get("turn_station_available", False):
                missing.append(pre)
            elif pre == "single_u_turn_not_yet_consumed" and int(state.get("u_turns_completed", 0)) > 0:
                missing.append(pre)
            elif pre == "physical_u_turn_executed" and not state.get("physical_u_turn_executed", False):
                missing.append(pre)
            elif pre == "turn_station_cleared" and not state.get("turn_station_cleared", False):
                missing.append(pre)
            elif pre in {"full_26_cubie_model", "multi_face_reindexing_fixture"}:
                missing.append(pre)
        return len(missing) == 0, missing

    def can_execute_physical_move(
        self,
        move: str,
        scene_state: dict[str, Any] | None = None,
    ) -> PhysicalMoveCapability:
        """Determine whether a single cube move can be physically executed in the current scene."""
        symbolic_ok = move in LEGAL_MOVES
        u_preconditions = list(self._skills["execute_physical_u_turn"].required_preconditions)

        if not symbolic_ok:
            return PhysicalMoveCapability(
                move=move,
                supported=False,
                skill_id=None,
                symbolic_supported=False,
                physical_model_supported=False,
                unsupported_reason=f"动作 {move!r} 不属于合法的 18 种魔方标准旋转符号。",
                required_preconditions=u_preconditions,
                missing_preconditions=["valid_cube_move_notation"],
            )

        if move != "U":
            if move in {"U'", "U2"}:
                reason = (
                    f"物理动作 {move} 未在 M3-B 中建立接触控制与视觉验收基线："
                    "当前旋转夹具仅验证单次 U 顺时针 +90° (-π/2 rad) 接触转层。"
                )
            else:
                face = move[0]
                reason = (
                    f"物理动作 {move} 不受支持：当前 MuJoCo 工程模型仅在 cube 顶部建模单层被动铰链 u_layer_joint，"
                    f"缺少 {face} 层实体铰链、26-cubie 互锁机构以及多面翻面重装夹工位。"
                )
            return PhysicalMoveCapability(
                move=move,
                supported=False,
                skill_id=None,
                symbolic_supported=True,
                physical_model_supported=False,
                unsupported_reason=reason,
                required_preconditions=["full_26_cubie_model", "multi_face_reindexing_fixture"],
                missing_preconditions=["full_26_cubie_model", "multi_face_reindexing_fixture"],
            )

        pre_ok, missing = self.check_preconditions("execute_physical_u_turn", scene_state)
        if not pre_ok:
            reason_parts = []
            if "physical_u_scene_enabled" in missing:
                reason_parts.append("未启用 physical_u 单层接触场景")
            if "cube_localized_and_scanned" in missing:
                reason_parts.append("尚未完成视觉定位与六面合法性扫描")
            if "turn_station_available" in missing:
                reason_parts.append("外部旋转工位与夹爪当前不可用")
            if "single_u_turn_not_yet_consumed" in missing:
                reason_parts.append("单次 U 层物理转动基线仅支持当前回合一次验证，不支持连续多步重入")
            return PhysicalMoveCapability(
                move=move,
                supported=False,
                skill_id="execute_physical_u_turn",
                symbolic_supported=True,
                physical_model_supported=True,
                unsupported_reason="前置条件未满足：" + "；".join(reason_parts),
                required_preconditions=u_preconditions,
                missing_preconditions=missing,
            )

        return PhysicalMoveCapability(
            move="U",
            supported=True,
            skill_id="execute_physical_u_turn",
            symbolic_supported=True,
            physical_model_supported=True,
            unsupported_reason=None,
            required_preconditions=u_preconditions,
            missing_preconditions=[],
        )

    def audit_move_sequence(
        self,
        moves: list[str],
        scene_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Inspect a symbolic move sequence against physical capabilities."""
        per_move: list[dict[str, Any]] = []
        blocked: list[PhysicalMoveCapability] = []
        simulated_state = dict(scene_state or {})
        for idx, move in enumerate(moves):
            cap = self.can_execute_physical_move(move, simulated_state)
            per_move.append({"index": idx, **cap.model_dump()})
            if cap.supported:
                simulated_state["u_turns_completed"] = int(simulated_state.get("u_turns_completed", 0)) + 1
            else:
                blocked.append(cap)
        first_blocked = blocked[0] if blocked else None
        return {
            "all_supported": len(blocked) == 0,
            "total_moves": len(moves),
            "supported_count": len(moves) - len(blocked),
            "blocked_count": len(blocked),
            "first_blocked_move": first_blocked.move if first_blocked else None,
            "blocked_moves": [item.move for item in blocked],
            "first_blocked_reason": first_blocked.unsupported_reason if first_blocked else None,
            "checks": per_move,
        }

    def snapshot(self) -> CapabilityRegistrySnapshot:
        return CapabilityRegistrySnapshot(
            skills=self.list_skills(),
            symbolic_supported_moves=list(LEGAL_MOVES),
            physical_supported_moves=["U"],
            physical_limitations_summary=(
                "Symbolic solver supports all 18 standard moves (U/R/F/D/L/B + ', 2). "
                "MuJoCo physical fixture supports only one contact-driven clockwise U (+90°) turn "
                "after 54-sticker visual scan and docking; R/F/L/B/D/U'/U2 are not physically modeled."
            ),
        )
