"""Deterministic Task Planner & Agent-ready DecisionPolicy interface."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .events import now_wall_time
from .models import (
    MissionState,
    MissionType,
    ObservationReference,
    PlanState,
    PlanStep,
    PlanStepStatus,
    PlannerMode,
)
from .skill_registry import SkillRegistry

MISSION_SPECS: dict[MissionType, dict[str, str]] = {
    MissionType.INSPECT_CUBE: {
        "title": "六面扫描",
        "user_goal": "主动感知并扫描魔方全部六个面，融合 54 格贴片状态并校验合法性（不执行物理转面）。",
        "success_criteria": "54 格贴片观测完整（unknown=0）、零冲突且通过拓扑可解性校验；严禁调用物理转层动作。",
    },
    MissionType.VERIFY_PHYSICAL_U_TURN: {
        "title": "U 层物理转动验证",
        "user_goal": "验证机器人能否将魔方搬运至旋转工位，并通过实体接触驱动 U 层顺时针转动 90°（M3-B 基线）。",
        "success_criteria": "实测层转角误差 < 0.03 rad、上下双侧夹爪接触连续且转后 21 个受影响贴片视觉复核一致。",
    },
    MissionType.SOLVE_CUBE: {
        "title": "魔方完整求解",
        "user_goal": "获取当前魔方状态、计算 Kociemba 求解序列，并严格核查物理执行能力边界。",
        "success_criteria": "完成状态合法性校验与符号求解；若序列包含当前未建模物理转层（如 R/F/L/B/D/U'/U2），明确触发 CAPABILITY_BLOCKED。",
    },
}


@dataclass(frozen=True, slots=True)
class SelectedAction:
    """Output of a Planner / VLM decision step, decoupled from Skill execution."""

    decision_kind: str  # EXECUTE_STEP | REQUEST_REPLAN | BLOCK_CAPABILITY | COMPLETE_MISSION | FAIL_MISSION
    step_id: str | None
    skill_id: str | None
    parameters: dict[str, Any]
    rationale_summary: str
    input_reference: str | None = None
    blocked_move: str | None = None
    blocked_moves: tuple[str, ...] = ()
    blocked_reason: str | None = None


class DecisionPolicy(Protocol):
    """Pluggable policy interface allowing DeterministicMissionPlanner or future Gemini VLM Agent."""

    name: str
    mode: PlannerMode
    llm_connected: bool
    llm_model: str | None

    def status_label(self) -> str: ...

    def create_plan(
        self,
        mission: MissionState,
        registry: SkillRegistry,
        *,
        plan_id: str,
    ) -> PlanState: ...

    def select_next_action(
        self,
        mission: MissionState,
        plan: PlanState,
        registry: SkillRegistry,
        scene_state: dict[str, Any],
        latest_observation: ObservationReference | None,
    ) -> SelectedAction: ...


class DeterministicMissionPlanner:
    """Auditable deterministic task orchestrator decoupled from physical Skills."""

    name = "DeterministicMissionPlanner"
    mode = PlannerMode.DETERMINISTIC_PLANNER
    llm_connected = False
    llm_model = None

    def status_label(self) -> str:
        return "当前由确定性任务规划器执行，LLM Agent 尚未接入"

    def create_plan(
        self,
        mission: MissionState,
        registry: SkillRegistry,
        *,
        plan_id: str,
    ) -> PlanState:
        now = now_wall_time()
        if mission.mission_type == MissionType.INSPECT_CUBE:
            blueprint = [
                ("observe_workspace", "工作站观察与定位", {"camera_name": "overhead"}),
                ("active_six_face_scan", "六面主动扫描", {"mode": "sequential"}),
                ("validate_cube_state", "54 格合法性校验", {}),
            ]
            rationale = (
                "任务目标为六面扫描（INSPECT_CUBE）：仅规划感知、主动多视角扫描与合法性校验 3 个阶段，"
                "不生成任何物理转面步骤。"
            )
        elif mission.mission_type == MissionType.VERIFY_PHYSICAL_U_TURN:
            blueprint = [
                ("observe_workspace", "工作站观察与定位", {"camera_name": "overhead"}),
                ("active_six_face_scan", "六面主动扫描", {"mode": "sequential"}),
                ("validate_cube_state", "54 格合法性校验", {}),
                ("compute_symbolic_plan", "计算 U 转动符号期望", {"target_mode": "single_u_expectation"}),
                ("execute_physical_u_turn", "接触驱动 U 层物理转动", {"move": "U"}),
                ("verify_post_turn_state", "转后 21 格视觉复核", {}),
            ]
            rationale = (
                "任务目标为 U 层物理转动验证（VERIFY_PHYSICAL_U_TURN）：规划扫描、校验、U 期望计算、"
                "接触式 U 层转动与转后独立相机复核 6 个阶段。"
            )
        else:  # MissionType.SOLVE_CUBE
            blueprint = [
                ("observe_workspace", "工作站观察与定位", {"camera_name": "overhead"}),
                ("active_six_face_scan", "六面主动扫描", {"mode": "sequential"}),
                ("validate_cube_state", "54 格合法性校验", {}),
                ("compute_symbolic_plan", "Kociemba 符号求解", {"target_mode": "solve"}),
                ("check_physical_capability", "物理能力边界核查", {}),
            ]
            rationale = (
                "任务目标为魔方完整求解（SOLVE_CUBE）：先完成观察、校验与符号求解，"
                "再逐动作检查物理执行能力；发现未支持转层时将阻断执行并报告 CAPABILITY_BLOCKED。"
            )

        steps: list[PlanStep] = []
        for idx, (skill_id, title, params) in enumerate(blueprint, start=1):
            desc = registry.get(skill_id)
            steps.append(
                PlanStep(
                    step_id=f"{plan_id}-s{idx}",
                    index=idx,
                    title=title,
                    skill_id=skill_id,
                    description=desc.description if desc else skill_id,
                    status=PlanStepStatus.PENDING,
                    implemented=bool(desc.implemented) if desc else False,
                    parameters=dict(params),
                )
            )
        return PlanState(
            plan_id=plan_id,
            mission_id=mission.mission_id,
            mission_type=mission.mission_type,
            planner_name=self.name,
            planner_mode=self.mode,
            created_at=now,
            updated_at=now,
            current_step_id=steps[0].step_id if steps else None,
            steps=steps,
            rationale_summary=rationale,
        )

    def select_next_action(
        self,
        mission: MissionState,
        plan: PlanState,
        registry: SkillRegistry,
        scene_state: dict[str, Any],
        latest_observation: ObservationReference | None,
    ) -> SelectedAction:
        obs_ref = latest_observation.observation_id if latest_observation else None
        pending = [step for step in plan.steps if step.status == PlanStepStatus.PENDING]
        if not pending:
            return SelectedAction(
                decision_kind="COMPLETE_MISSION",
                step_id=None,
                skill_id=None,
                parameters={},
                rationale_summary="当前计划所有步骤均已验证完成，任务达到成功标准。",
                input_reference=obs_ref,
            )

        next_step = pending[0]
        param_ok, param_err = registry.validate_parameters(next_step.skill_id, next_step.parameters)
        if not param_ok:
            return SelectedAction(
                decision_kind="BLOCK_CAPABILITY",
                step_id=next_step.step_id,
                skill_id=next_step.skill_id,
                parameters=next_step.parameters,
                rationale_summary=f"参数或能力校验失败：{param_err}",
                input_reference=obs_ref,
                blocked_reason=param_err,
            )

        pre_ok, missing = registry.check_preconditions(next_step.skill_id, scene_state)
        if not pre_ok:
            reason = f"Skill [{next_step.skill_id}] 缺少前置条件：{', '.join(missing)}"
            return SelectedAction(
                decision_kind="BLOCK_CAPABILITY",
                step_id=next_step.step_id,
                skill_id=next_step.skill_id,
                parameters=next_step.parameters,
                rationale_summary=reason,
                input_reference=obs_ref,
                blocked_reason=reason,
            )

        # Extra physical boundary check before executing physical U turn
        if next_step.skill_id == "execute_physical_u_turn":
            move = str(next_step.parameters.get("move", "U"))
            cap = registry.can_execute_physical_move(move, scene_state)
            if not cap.supported:
                return SelectedAction(
                    decision_kind="BLOCK_CAPABILITY",
                    step_id=next_step.step_id,
                    skill_id=next_step.skill_id,
                    parameters=next_step.parameters,
                    rationale_summary=cap.unsupported_reason or "物理能力校验未通过",
                    input_reference=obs_ref,
                    blocked_move=move,
                    blocked_moves=(move,),
                    blocked_reason=cap.unsupported_reason,
                )

        # Build explicit rationale grounded in real state & observation
        if next_step.skill_id == "observe_workspace":
            rationale = "工作站尚未获取当前相机帧与魔方定位信息，因此首先执行顶部 RGB-D 观测与三维定位。"
        elif next_step.skill_id == "active_six_face_scan":
            center_txt = (
                f"定位中心 {tuple(round(v, 3) for v in latest_observation.cube_center_world_m)}"
                if latest_observation and latest_observation.cube_center_world_m
                else "已完成工作站观测"
            )
            rationale = f"{center_txt}，当前未知贴片仍为 {latest_observation.unknown_count if latest_observation else 54}/54，选择执行六面主动扫描。"
        elif next_step.skill_id == "validate_cube_state":
            obs_count = latest_observation.observed_count if latest_observation else 0
            rationale = f"扫描后已采集 {obs_count}/54 贴片，选择执行独立合法性与 Kociemba 群论校验以确认状态完整可信。"
        elif next_step.skill_id == "compute_symbolic_plan":
            if mission.mission_type == MissionType.VERIFY_PHYSICAL_U_TURN:
                rationale = "魔方 54 格状态已校验合法，基于实测状态计算单步 U 顺时针旋转后的符号期望用于后续视觉复核（不修改物理场景）。"
            else:
                rationale = "魔方 54 格状态已校验合法，调用 Kociemba 符号求解器生成完整还原动作序列，供后续物理能力逐项核查。"
        elif next_step.skill_id == "check_physical_capability":
            sol = scene_state.get("symbolic_solution") or []
            rationale = (
                f"符号求解生成 {len(sol)} 步动作序列 {sol[:6]}{'...' if len(sol) > 6 else ''}，"
                "逐动作对照 SkillRegistry 核查 MuJoCo 当前物理模型是否具备执行能力。"
            )
        elif next_step.skill_id == "execute_physical_u_turn":
            rationale = (
                "能力校验确认：当前场景已启用 physical_u 接触模型、已完成 54 格扫描且 U 旋转工位可用，"
                "选择调用 ContactUTurn 执行真实接触式 U 层顺时针 +90° 转动。"
            )
        elif next_step.skill_id == "verify_post_turn_state":
            rationale = "物理 U 层转角与接触记录已达标，机械臂与夹具退避后执行独立相机复核，验证受影响 21 格贴片是否与期望一致。"
        else:
            rationale = f"按当前计划选择执行步骤 {next_step.index}: {next_step.title} ({next_step.skill_id})。"

        return SelectedAction(
            decision_kind="EXECUTE_STEP",
            step_id=next_step.step_id,
            skill_id=next_step.skill_id,
            parameters=dict(next_step.parameters),
            rationale_summary=rationale,
            input_reference=obs_ref,
        )
