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
    execution_metadata: dict[str, Any] = Field(default_factory=dict)


class PhysicalMoveCapability(BaseModel):
    """Answer to CanExecutePhysicalMove(move, scene_state)."""

    model_config = ConfigDict(extra="forbid")

    move: str
    supported: bool
    skill_id: str | None = None
    symbolic_supported: bool
    physical_model_supported: bool
    estimated_flips: int | None = None
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


_OPPOSITE_FACE = {"U": "D", "D": "U", "F": "B", "B": "F", "R": "L", "L": "R"}


class SkillRegistry:
    """Registry declaring real implemented Skills and exact physical boundaries."""

    def __init__(self, *, physical_full_cube: bool = False) -> None:
        self.physical_full_cube = bool(physical_full_cube)
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
                skill_id="place_and_release",
                title="抓取对齐并放置释放至扫描工位",
                description="若尚未持握则执行安全抓取与轴向对齐，随后将魔方稳定放置并释放到桌面扫描工位以供多视角观测。",
                category="PERCEPTION_AND_MANIPULATION",
                implemented=True,
                is_physical_action=True,
                required_preconditions=["simulation_initialized", "cube_localized"],
                required_observations=["overhead_rgbd"],
                supported_parameters={},
                supported_physical_actions=["GRASP", "ALIGN_SCAN_AXES", "PLACE_RELEASE"],
                expected_outputs=["released", "height_after_m", "world_state_refresh"],
                verification_method="Table contact support and bilateral finger release check",
                failure_codes=["INITIAL_GRASP_FAILED", "ALIGN_SCAN_AXES_FAILED", "PLACE_RELEASE_FAILED"],
            ),
            SkillDescriptor(
                skill_id="observe_visible_faces",
                title="观测当前可见魔方表面",
                description="根据魔方当前处于桌面释放态或夹爪持握态，调用多相机 RGB-D 采集当前可见面并融合至 54 格状态（被桌面或夹爪遮挡的贴片保持 unknown）。",
                category="PERCEPTION",
                implemented=True,
                is_physical_action=False,
                required_preconditions=["simulation_initialized", "cube_localized"],
                required_observations=["scan_cameras_rgbd"],
                supported_parameters={"view_mode": "str (auto | released | held)"},
                supported_physical_actions=[],
                expected_outputs=["newly_observed", "observed_count", "unknown_count", "conflict_count", "observation_id"],
                verification_method="SixFacePerception D4 mapping + StickerStateFusion",
                failure_codes=["NO_VALID_OBSERVATIONS", "HELD_VIEW_GRASP_LOST", "RELEASED_LOCALIZATION_FAILED"],
            ),
            SkillDescriptor(
                skill_id="regrasp_cube",
                title="桌面魔方安全重抓与对齐",
                description="通过 RGB-D 定位桌面上的已释放魔方并执行双指力控重抓及扫描轴对齐，为后续翻转暴露底面做准备。",
                category="PHYSICAL_MANIPULATION",
                implemented=True,
                is_physical_action=True,
                required_preconditions=["simulation_initialized", "cube_localized", "cube_released_on_table"],
                required_observations=["overhead_rgbd"],
                supported_parameters={},
                supported_physical_actions=["REGRASP", "ALIGN_SCAN_AXES"],
                expected_outputs=["success", "bilateral_contact_fraction", "max_relative_slip_m"],
                verification_method="Bilateral contact force + slip check + held orientation refresh",
                failure_codes=["REGRASP_FAILED", "SCAN_ALIGNMENT_CONTACT_LOSS"],
            ),
            SkillDescriptor(
                skill_id="reorient_cube",
                title="持握状态下整体翻转魔方",
                description="在保持双指夹持的条件下，驱动腕部关节旋转 ±90°（pitch 或 yaw）以将此前被遮挡的面转向可见相机。",
                category="PHYSICAL_MANIPULATION",
                implemented=True,
                is_physical_action=True,
                required_preconditions=["simulation_initialized", "cube_held_in_gripper"],
                required_observations=["held_cameras_rgbd"],
                supported_parameters={"axis": "Literal['pitch', 'yaw']", "degrees": "Literal[-90, 90]"},
                supported_physical_actions=["REORIENT"],
                expected_outputs=["axis", "reorient_target_radians", "reorient_actual_radians", "bilateral_contact_fraction"],
                verification_method="Joint target error <= 0.08 rad, bilateral contact >= 0.8, slip <= 0.03 m",
                failure_codes=["REORIENT_JOINT_LIMIT", "REORIENT_BILATERAL_CONTACT_LOST", "REORIENT_SLIP_EXCEEDED"],
            ),
            SkillDescriptor(
                skill_id="finish_inspection",
                title="结束主动视觉扫描并校验完整性",
                description="当且仅当 54 格贴片全部观测完成（unknown=0）且无冲突时，结束主动感知扫描阶段并进入合法性校验。",
                category="PERCEPTION",
                implemented=True,
                is_physical_action=False,
                required_preconditions=["simulation_initialized", "scan_attempted", "all_54_facelets_observed"],
                required_observations=["fused_54_facelets"],
                supported_parameters={},
                supported_physical_actions=[],
                expected_outputs=["observed_count", "unknown_count", "conflict_count"],
                verification_method="StickerStateFusion 54-cell completeness and conflict-free check",
                failure_codes=["SCAN_INCOMPLETE", "UNRESOLVED_CONFLICTS"],
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
                skill_id="execute_physical_face_turn",
                title="全六面翻面喂料与单工位接触式物理转面",
                description=(
                    "基于 26-cubie 物理魔方与单顶层旋转夹具（±90°/180°），由单臂自动完成 "
                    "0/1/2 次翻面喂料（含底面桌面侧躺—松爪—视觉重抓连招），将目标面朝上送入工位完成纯接触摩擦转面。"
                ),
                category="PHYSICAL_MANIPULATION",
                implemented=self.physical_full_cube,
                is_physical_action=True,
                required_preconditions=[
                    "full_26_cubie_scene_enabled",
                    "cube_localized_and_scanned",
                    "turn_station_available",
                    "station_lattice_aligned",
                ],
                required_observations=["overhead_rgbd", "inspection_side_rgbd"],
                supported_parameters={"move": "str in LEGAL_MOVES (U/R/F/D/L/B with '', \"'\", '2')"},
                supported_physical_actions=list(LEGAL_MOVES) if self.physical_full_cube else [],
                expected_outputs=[
                    "actual_angle_rad",
                    "angle_error_deg",
                    "max_slice_misalignment_deg",
                    "flips_executed",
                    "regrasps_executed",
                    "contact_driven",
                ],
                verification_method="Contact-driven top fixture turn within <=8 deg tolerance + independent camera verification",
                failure_codes=[
                    "INVALID_MOVE_NOTATION",
                    "VISUAL_LOCALIZATION_FAILED",
                    "FLIP_AND_FEED_FAILED",
                    "FLIP_PREEMPTED",
                    "SLICE_MISALIGNED_JAM",
                    "CONTACT_DRIVE_FAILED",
                    "SLICE_TURN_INCOMPLETE",
                ],
                execution_metadata={
                    "supports_all_18_moves": True,
                    "estimated_flips_values": [0, 1, 2],
                    "single_top_fixture_angles_deg": [90, -90, 180],
                },
            ),
            SkillDescriptor(
                skill_id="recover_preempted_turn_slice",
                title="半拧抢占晶格纯接触恢复",
                description=(
                    "在顶层夹具转面中途被抢占后，100% 通过夹具上下垫块接触摩擦力矩将半拧顶层"
                    "回退至 0°（UNWIND_TO_ZERO）或对齐至最近 90° 晶格位（ALIGN_NEAREST_DETENT），"
                    "经 validate_lattice_alignment 确认残差 < 2.0° 后才允许松开夹具或切轴。"
                ),
                category="PHYSICAL_MANIPULATION",
                implemented=self.physical_full_cube,
                is_physical_action=True,
                required_preconditions=[
                    "full_26_cubie_scene_enabled",
                    "turn_station_available",
                ],
                required_observations=[],
                supported_parameters={"mode": "Literal['UNWIND_TO_ZERO', 'ALIGN_NEAREST_DETENT']"},
                supported_physical_actions=["UNWIND_TO_ZERO", "ALIGN_NEAREST_DETENT"] if self.physical_full_cube else [],
                expected_outputs=[
                    "is_lattice_aligned",
                    "residual_slice_angle_deg",
                    "max_slice_misalignment_deg",
                    "contact_driven",
                ],
                verification_method="validate_lattice_alignment(tol_deg=8.0) with < 2.0 deg residual before clamp release",
                failure_codes=["SLICE_MISALIGNED_JAM", "FIXTURE_MISALIGNED", "CONTACT_DRIVE_FAILED", "SLICE_RECOVERY_FAILED"],
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
            SkillDescriptor(
                skill_id="observe_tabletop_rapid",
                title="桌面 5 相机 1 秒快瞄与块守恒推导",
                description=(
                    "耗时 <1s、不抓起魔方，采集顶部+四周共 5 路释放态相机视角读取最多 45 格贴片，"
                    "结合交接前信念与三阶魔方 8 角块/12 棱块色守恒判定底面是否唯一锁定 (deduced_54_unique)。"
                    "若唯一锁定可直接跳过 ~25s 的翻底面扫描！"
                ),
                category="PERCEPTION",
                implemented=self.physical_full_cube,
                is_physical_action=False,
                required_preconditions=[
                    "simulation_initialized",
                    "full_26_cubie_scene_enabled",
                    "station_lattice_aligned",
                ],
                required_observations=["overhead_rgbd", "scan_cameras_rgbd"],
                supported_parameters={},
                supported_physical_actions=[],
                expected_outputs=[
                    "observed_count",
                    "deduced_54_unique",
                    "ambiguous_facelet_count",
                    "inferred_human_moves",
                ],
                verification_method="5-camera zero-contact rapid glance + BeliefConservationAnalyzer uniqueness",
                failure_codes=["SLICE_MISALIGNED_JAM", "CUBE_NOT_ON_TABLE", "RAPID_LOCALIZATION_FAILED"],
            ),
            SkillDescriptor(
                skill_id="scan_occluded_bottom_face",
                title="完整主动抓起翻转六面扫描 (含被遮挡底面)",
                description=(
                    "耗时 ~25s：RGB-D 重定位并校正桌面魔方后，抓起并翻转 -90° 扫描全部 6 面 54/54 贴片。"
                    "适用于开局无历史信念 (unknown=54) 或快瞄存在真歧义 (ambiguous_facelet_count>0) 时使用。"
                ),
                category="PERCEPTION_AND_MANIPULATION",
                implemented=self.physical_full_cube,
                is_physical_action=True,
                required_preconditions=[
                    "simulation_initialized",
                    "full_26_cubie_scene_enabled",
                    "station_lattice_aligned",
                ],
                required_observations=["overhead_rgbd", "scan_cameras_rgbd", "inspection_cameras_rgbd"],
                supported_parameters={},
                supported_physical_actions=["RELOCALIZE", "REGRASP", "REORIENT", "INSPECT_ALL_6_FACES"],
                expected_outputs=["reconstructed_facelets", "observed_count", "unknown_count", "conflict_count"],
                verification_method="Independent 2-pass RGB-D 6-face fusion",
                failure_codes=["SLICE_MISALIGNED_JAM", "VISUAL_LOCALIZATION_FAILED", "RESCAN_PICKUP_FAILED"],
            ),
            SkillDescriptor(
                skill_id="request_vlm_scene_semantics",
                title="按需唤醒 VLM 诊断场景语义",
                description=(
                    "仅当传统 CV 定位异常、置信度偏低、贴片冲突或怀疑工作区异常时，主动唤醒视觉语义模型观察桌面场景。"
                ),
                category="PERCEPTION",
                implemented=True,
                is_physical_action=False,
                required_preconditions=["simulation_initialized"],
                required_observations=["overhead_rgbd"],
                supported_parameters={"camera_id": "str (default: overhead)", "reason": "str"},
                supported_physical_actions=[],
                expected_outputs=["semantic_summary", "occluded_regions", "visual_conflicts"],
                verification_method="VLMPerceptionProvider envelope validation",
                failure_codes=["VLM_UNAVAILABLE"],
            ),
            SkillDescriptor(
                skill_id="commit_physical_moves",
                title="提交带契约保护的 1~3 步物理转面序列",
                description=(
                    "在 26-Cubie 场景内按边际代价与人类约束承诺执行 1~3 步标准物理转面，"
                    "同步下发 50Hz 快环监控契约 (max_target_drift_m, interrupt_on_human_chat_command, mid_turn_recovery_mode)。"
                ),
                category="PHYSICAL_MANIPULATION",
                implemented=self.physical_full_cube,
                is_physical_action=True,
                required_preconditions=[
                    "full_26_cubie_scene_enabled",
                    "cube_localized_and_scanned",
                    "turn_station_available",
                    "station_lattice_aligned",
                ],
                required_observations=["overhead_rgbd"],
                supported_parameters={
                    "moves": "list[str] (1..3 moves in LEGAL_MOVES)",
                    "contract": (
                        "dict (ExecutionContractSpec: max_target_drift_m, interrupt_on_human_chat_command, "
                        "mid_turn_recovery_mode='UNWIND_TO_ZERO'|'ALIGN_NEAREST_DETENT' — prefer 'UNWIND_TO_ZERO' for safe reversible preemption)"
                    ),
                },
                supported_physical_actions=list(LEGAL_MOVES) if self.physical_full_cube else [],
                expected_outputs=["executed_moves", "is_lattice_aligned", "preempted"],
                verification_method="FlipAndFeed + contact torque turn + 50Hz ExecutionContract watchdog",
                failure_codes=["PREEMPTED", "FLIP_PREEMPTED", "FLIP_AND_FEED_FAILED", "SLICE_MISALIGNED_JAM"],
            ),
            SkillDescriptor(
                skill_id="handover_to_human",
                title="安全提离工位并移交人类桌面接力",
                description=(
                    "将魔方从机械工位/夹爪安全提离、稳定放回桌面中央交接区，机械臂退回停泊位 (-0.42, 0.25)，"
                    "向人类展示推荐 1~3 步及具身委派说明。"
                ),
                category="HRI_COLLABORATION",
                implemented=self.physical_full_cube,
                is_physical_action=True,
                required_preconditions=[
                    "simulation_initialized",
                    "full_26_cubie_scene_enabled",
                    "station_lattice_aligned",
                ],
                required_observations=[],
                supported_parameters={
                    "message_zh": "str",
                    "suggested_moves": "list[str] (0..3 moves)",
                    "delegation_reason_zh": "str",
                },
                supported_physical_actions=["PLACE_TABLETOP_HANDOVER", "PARK_STANDBY"],
                expected_outputs=["handover_xy", "waiting_for_human"],
                verification_method="Lattice aligned + gripper released + arm parked at (-0.42, 0.25)",
                failure_codes=["SLICE_MISALIGNED_JAM", "HANDOVER_PICKUP_FAILED", "HANDOVER_PARK_FAILED"],
            ),
            SkillDescriptor(
                skill_id="ask_human_clarification",
                title="向人类发起自然语言意图/歧义澄清",
                description=(
                    "当视觉发现人类偏离推荐路线存在 R/R' 逆向抵消风险且意图不明，"
                    "或桌面快瞄存在底面歧义需要确认策略时，暂停动作并在对话栏发起简明中文澄清及快捷选项。"
                ),
                category="HRI_COLLABORATION",
                implemented=True,
                is_physical_action=False,
                required_preconditions=["simulation_initialized"],
                required_observations=[],
                supported_parameters={
                    "question_zh": "str",
                    "options": "list[str]",
                    "clarification_topic": "str",
                },
                supported_physical_actions=[],
                expected_outputs=["clarification_pending"],
                verification_method="Human response recorded into dialog history",
                failure_codes=[],
            ),
            SkillDescriptor(
                skill_id="verify_solved_cube_independent",
                title="全六面独立相机 100% 复原物理核验",
                description=(
                    "在相信魔方已复原后，独立调用全六面多视角 RGB-D 扫描核验 54/54 贴片均已复原 (SOLVED_FACELETS)、"
                    "0 未知、0 冲突且确认零改色/零焊点作弊，随后方可 FINISH。"
                ),
                category="VERIFICATION",
                implemented=self.physical_full_cube,
                is_physical_action=True,
                required_preconditions=[
                    "simulation_initialized",
                    "full_26_cubie_scene_enabled",
                    "station_lattice_aligned",
                ],
                required_observations=["overhead_rgbd", "released_scan_cameras_rgbd", "held_scan_cameras_rgbd"],
                supported_parameters={},
                supported_physical_actions=["VERIFY_54_SOLVED"],
                expected_outputs=["exact_54_solved", "observed_count", "conflict_count", "no_recolor"],
                verification_method="Independent 6-face RGB-D camera scan matching SOLVED_FACELETS with 0 unknown & 0 conflict",
                failure_codes=["SOLVED_VERIFICATION_FAILED", "SLICE_MISALIGNED_JAM"],
            ),
        ]
        for skill in defaults:
            self._skills[skill.skill_id] = skill

    def list_skills(self) -> list[SkillDescriptor]:
        return list(self._skills.values())

    def get(self, skill_id: str) -> SkillDescriptor | None:
        return self._skills.get(skill_id)

    def clone(
        self,
        *,
        disabled_skills: set[str] | list[str] | tuple[str, ...] | None = None,
        removed_skills: set[str] | list[str] | tuple[str, ...] | None = None,
    ) -> "SkillRegistry":
        """Create an isolated copy with optional disabled or removed skills."""
        cloned = SkillRegistry(physical_full_cube=self.physical_full_cube)
        disabled = set(disabled_skills or ())
        removed = set(removed_skills or ())
        cloned._skills = {}
        for skill_id, desc in self._skills.items():
            if skill_id in removed:
                continue
            copy_desc = desc.model_copy(deep=True)
            if skill_id in disabled:
                copy_desc.implemented = False
            cloned._skills[skill_id] = copy_desc
        return cloned

    def validate_parameters(self, skill_id: str, params: dict[str, Any] | None = None, scene_state: dict[str, Any] | None = None) -> tuple[bool, str | None]:
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
        elif skill_id == "execute_physical_face_turn":
            unknown_keys = set(params.keys()) - {"move"}
            if unknown_keys:
                return False, f"PARAMETER_OUT_OF_BOUNDS: execute_physical_face_turn 不支持参数 {sorted(unknown_keys)}"
            move = params.get("move")
            if not isinstance(move, str) or move.strip() not in LEGAL_MOVES:
                return False, f"execute_physical_face_turn 参数 move={move!r} 非法，必须属于 18 种标准魔方动作之一"
        elif skill_id == "recover_preempted_turn_slice":
            unknown_keys = set(params.keys()) - {"mode"}
            if unknown_keys:
                return False, f"PARAMETER_OUT_OF_BOUNDS: recover_preempted_turn_slice 不支持参数 {sorted(unknown_keys)}"
            mode = params.get("mode", "UNWIND_TO_ZERO")
            if mode not in {"UNWIND_TO_ZERO", "ALIGN_NEAREST_DETENT"}:
                return False, (
                    f"PARAMETER_OUT_OF_BOUNDS: recover_preempted_turn_slice mode={mode!r} "
                    "仅允许 'UNWIND_TO_ZERO' 或 'ALIGN_NEAREST_DETENT'"
                )
        elif skill_id == "reorient_cube":
            unknown_keys = set(params.keys()) - {"axis", "degrees"}
            if unknown_keys:
                return False, f"PARAMETER_OUT_OF_BOUNDS: reorient_cube 不支持参数 {sorted(unknown_keys)}"
            axis = params.get("axis", "pitch")
            if axis not in {"pitch", "yaw"}:
                return False, f"PARAMETER_OUT_OF_BOUNDS: reorient_cube axis={axis!r} 仅允许 'pitch' 或 'yaw'"
            default_deg = -90 if axis == "pitch" else 90
            degrees = params.get("degrees", default_deg)
            if isinstance(degrees, bool) or not isinstance(degrees, (int, float)) or float(degrees) not in (-90.0, 90.0):
                return False, f"PARAMETER_OUT_OF_BOUNDS: reorient_cube degrees={degrees!r} 仅允许 -90 或 90"
        elif skill_id == "observe_workspace":
            camera_name = params.get("camera_name", "overhead")
            if camera_name not in {"overhead", "world_top", "scan_top", "inspection_top"}:
                return False, f"PARAMETER_OUT_OF_BOUNDS: observe_workspace camera_name={camera_name!r} 不在允许列表"
        elif skill_id == "observe_visible_faces":
            view_mode = params.get("view_mode", "auto")
            if view_mode not in {"auto", "released", "held"}:
                return False, f"PARAMETER_OUT_OF_BOUNDS: observe_visible_faces view_mode={view_mode!r} 仅允许 auto/released/held"
        elif skill_id == "compute_symbolic_plan":
            target_mode = params.get("target_mode", "solve")
            if target_mode not in {"solve", "single_u_expectation"}:
                return False, f"PARAMETER_OUT_OF_BOUNDS: compute_symbolic_plan target_mode={target_mode!r} 非法"
        elif skill_id == "commit_physical_moves":
            moves = params.get("moves")
            if not isinstance(moves, list) or not (1 <= len(moves) <= 3):
                return False, f"PARAMETER_OUT_OF_BOUNDS: commit_physical_moves moves={moves!r} 必须为 1~3 步列表"
            bad = [m for m in moves if not isinstance(m, str) or m.strip() not in LEGAL_MOVES]
            if bad:
                return False, f"PARAMETER_OUT_OF_BOUNDS: commit_physical_moves 包含非法动作 {bad!r}"
            state = scene_state or {}
            remaining = state.get("remaining_turn_quota")
            if remaining == 0 and not state.get("is_solved"):
                return False, "TURN_QUOTA_EXHAUSTED_MUST_HANDOVER: 本回合配额已满，必须交接给人类"
            if remaining is not None and len(moves) > remaining:
                return False, f"EXCEEDS_REMAINING_TURN_QUOTA: 本回合已拧 {state.get('robot_moves_this_turn', 0)} 步，最多再提交 {remaining} 步"
            contract = params.get("contract")
            if contract is not None:
                if not isinstance(contract, dict):
                    return False, "PARAMETER_OUT_OF_BOUNDS: commit_physical_moves contract 必须为字典"
                from .relay_cognition import ExecutionContractSpec
                try:
                    ExecutionContractSpec.model_validate(contract)
                except Exception as exc:
                    return False, f"PARAMETER_OUT_OF_BOUNDS: ExecutionContractSpec 校验失败: {exc}"
        elif skill_id == "handover_to_human":
            suggested = params.get("suggested_moves", [])
            if not isinstance(suggested, list) or len(suggested) > 3:
                return False, f"PARAMETER_OUT_OF_BOUNDS: handover_to_human suggested_moves 必须为 0~3 步列表"
            bad = [m for m in suggested if not isinstance(m, str) or m.strip() not in LEGAL_MOVES]
            if bad:
                return False, f"PARAMETER_OUT_OF_BOUNDS: handover_to_human suggested_moves 包含非法动作 {bad!r}"
        elif skill_id == "ask_human_clarification":
            q = params.get("question_zh")
            if not isinstance(q, str) or not q.strip():
                return False, "PARAMETER_OUT_OF_BOUNDS: ask_human_clarification 需要非空 question_zh"
        elif skill_id == "request_vlm_scene_semantics":
            cam = params.get("camera_id", "overhead")
            if cam not in {"overhead", "world_top", "scan_top", "inspection_top", "inspection_down_pos_y"}:
                return False, f"PARAMETER_OUT_OF_BOUNDS: request_vlm_scene_semantics camera_id={cam!r} 非法"
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
            elif pre == "cube_released_on_table" and not state.get("cube_released_on_table", False):
                missing.append(pre)
            elif pre == "cube_held_in_gripper" and not state.get("cube_held_in_gripper", False):
                missing.append(pre)
            elif pre == "all_54_facelets_observed" and not state.get("all_54_facelets_observed", False):
                missing.append(pre)
            elif pre == "cube_state_validated" and not state.get("cube_state_validated", False):
                missing.append(pre)
            elif pre == "symbolic_plan_available" and not state.get("symbolic_plan_available", False):
                missing.append(pre)
            elif pre == "physical_u_scene_enabled" and not state.get("physical_u_scene_enabled", False):
                missing.append(pre)
            elif pre == "full_26_cubie_scene_enabled" and not state.get("full_26_cubie_scene_enabled", False):
                missing.append(pre)
            elif pre == "cube_localized_and_scanned" and not state.get("cube_localized_and_scanned", False):
                missing.append(pre)
            elif pre == "turn_station_available" and not state.get("turn_station_available", False):
                missing.append(pre)
            elif pre == "station_lattice_aligned" and not state.get("is_lattice_aligned", True):
                missing.append(pre)
            elif pre == "single_u_turn_not_yet_consumed" and int(state.get("u_turns_completed", 0)) > 0:
                missing.append(pre)
            elif pre == "physical_u_turn_executed" and not (
                state.get("physical_u_turn_executed", False)
                or state.get("physical_face_turn_executed", False)
            ):
                missing.append(pre)
            elif pre == "turn_station_cleared" and not state.get("turn_station_cleared", False):
                missing.append(pre)
            elif pre in {"full_26_cubie_model", "multi_face_reindexing_fixture"}:
                missing.append(pre)
        if (
            descriptor.skill_id in {"regrasp_cube", "reorient_cube"}
            and not state.get("is_lattice_aligned", True)
            and "station_lattice_aligned" not in missing
        ):
            missing.append("station_lattice_aligned")
        return len(missing) == 0, missing

    def estimate_move_flips(
        self,
        move: str,
        scene_state: dict[str, Any] | None = None,
    ) -> int:
        """Estimate flip count (0: top face, 1: side face, 2: bottom face) from tracked cube orientation."""
        face = str(move).strip()[0]
        state = scene_state or {}
        top_face = str(state.get("cube_top_face") or "U")
        bottom_face = str(state.get("cube_bottom_face") or _OPPOSITE_FACE.get(top_face, "D"))
        if face == top_face:
            return 0
        if face == bottom_face:
            return 2
        return 1

    def can_execute_physical_move(
        self,
        move: str,
        scene_state: dict[str, Any] | None = None,
    ) -> PhysicalMoveCapability:
        """Determine whether a single cube move can be physically executed in the current scene."""
        symbolic_ok = move in LEGAL_MOVES
        u_preconditions = list(self._skills["execute_physical_u_turn"].required_preconditions)
        face_preconditions = list(self._skills["execute_physical_face_turn"].required_preconditions)
        full_mode = bool(
            self.physical_full_cube
            or (scene_state is not None and scene_state.get("full_26_cubie_scene_enabled", False))
        )

        if not symbolic_ok:
            return PhysicalMoveCapability(
                move=move,
                supported=False,
                skill_id=None,
                symbolic_supported=False,
                physical_model_supported=False,
                unsupported_reason=f"动作 {move!r} 不属于合法的 18 种魔方标准旋转符号。",
                required_preconditions=face_preconditions if full_mode else u_preconditions,
                missing_preconditions=["valid_cube_move_notation"],
            )

        if full_mode:
            flips = self.estimate_move_flips(move, scene_state)
            face_desc = self._skills["execute_physical_face_turn"]
            if not self.physical_full_cube and scene_state is not None and scene_state.get("full_26_cubie_scene_enabled", False):
                # Scene declares full 26-cubie support; check preconditions directly against scene_state
                missing = []
                if not scene_state.get("full_26_cubie_scene_enabled", False):
                    missing.append("full_26_cubie_scene_enabled")
                if not scene_state.get("cube_localized_and_scanned", False):
                    missing.append("cube_localized_and_scanned")
                if not scene_state.get("turn_station_available", False):
                    missing.append("turn_station_available")
                if not scene_state.get("is_lattice_aligned", True):
                    missing.append("station_lattice_aligned")
                pre_ok = len(missing) == 0
            else:
                pre_ok, missing = self.check_preconditions("execute_physical_face_turn", scene_state)
            if not pre_ok:
                reason_parts = []
                if "full_26_cubie_scene_enabled" in missing:
                    reason_parts.append("未启用 26-cubie 全六面物理场景")
                if "cube_localized_and_scanned" in missing:
                    reason_parts.append("尚未完成视觉定位与六面合法性扫描")
                if "turn_station_available" in missing:
                    reason_parts.append("外部旋转工位与夹爪当前不可用")
                if "station_lattice_aligned" in missing:
                    reason_parts.append("转面工位存在未恢复的半拧晶格偏置，必须先执行 recover_preempted_turn_slice")
                return PhysicalMoveCapability(
                    move=move,
                    supported=False,
                    skill_id="execute_physical_face_turn",
                    symbolic_supported=True,
                    physical_model_supported=True,
                    estimated_flips=flips,
                    unsupported_reason="前置条件未满足：" + "；".join(reason_parts),
                    required_preconditions=face_preconditions,
                    missing_preconditions=missing,
                )
            return PhysicalMoveCapability(
                move=move,
                supported=True,
                skill_id="execute_physical_face_turn",
                symbolic_supported=True,
                physical_model_supported=bool(face_desc.implemented or full_mode),
                estimated_flips=flips,
                unsupported_reason=None,
                required_preconditions=face_preconditions,
                missing_preconditions=[],
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
                if cap.skill_id == "execute_physical_face_turn":
                    simulated_state["physical_turns_completed"] = int(simulated_state.get("physical_turns_completed", 0)) + 1
                    simulated_state["cube_top_face"] = move[0]
                    simulated_state["cube_bottom_face"] = _OPPOSITE_FACE[move[0]]
                else:
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
        if self.physical_full_cube:
            return CapabilityRegistrySnapshot(
                skills=self.list_skills(),
                symbolic_supported_moves=list(LEGAL_MOVES),
                physical_supported_moves=list(LEGAL_MOVES),
                physical_limitations_summary=(
                    "Full 26-cubie MuJoCo model + single ±90°/180° top fixture + Flip-and-Feed controller "
                    "supports all 18 standard moves (U/R/F/D/L/B + ', 2) via 0/1/2 physical flips."
                ),
            )
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
