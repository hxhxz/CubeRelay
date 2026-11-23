import React, { useState, useEffect, useRef, useMemo } from 'react';
import {
  Activity,
  AlertTriangle,
  Bot,
  Camera,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  Cpu,
  Database,
  Download,
  FileCode2,
  Film,
  FolderOpen,
  GitBranch,
  Grid,
  History,
  Layers,
  Lock,
  Monitor,
  Play,
  Radio,
  RefreshCw,
  RotateCcw,
  Scan,
  Settings,
  ShieldAlert,
  ShieldCheck,
  Square,
  Upload,
  WifiOff,
  X,
  XCircle,
} from 'lucide-react';

// ============================================================================
// 1. 类型与通信协议定义 (Mission / Plan / Skill / DecisionEvent / MuJoCo)
// ============================================================================

export type RuntimeMode = 'SAMPLE' | 'LIVE' | 'REPLAY';

export type CameraPresetId = 'overview' | 'gripper_closeup' | 'cube_closeup' | 'top_ortho';

export type FaceId = 'U' | 'D' | 'F' | 'B' | 'L' | 'R';

export type FaceletColor = 'W' | 'Y' | 'G' | 'B' | 'O' | 'R' | 'UNKNOWN';

export type StageStatus = 'PENDING' | 'RUNNING' | 'VERIFIED' | 'FAILED' | 'BLOCKED' | 'UNAVAILABLE';

export type MissionType = 'INSPECT_CUBE' | 'VERIFY_PHYSICAL_U_TURN' | 'SOLVE_CUBE' | 'RELAY_SOLVE_CUBE';

export type MissionStatus =
  | 'CREATED'
  | 'OBSERVING'
  | 'PLANNING'
  | 'EXECUTING'
  | 'VERIFYING'
  | 'WAITING_FOR_HUMAN_TURN'
  | 'BLOCKED_CAPABILITY'
  | 'COMPLETED'
  | 'FAILED'
  | 'CANCELLED';

export type RelayPhase =
  | 'IDLE'
  | 'AGENT_REASONING'
  | 'ROBOT_ACTING'
  | 'ROBOT_PERCEIVING'
  | 'WAITING_FOR_HUMAN_TURN'
  | 'AWAITING_HUMAN_CLARIFICATION'
  | 'PREEMPTED_RECOVERING'
  | 'VERIFYING_SOLVED'
  | 'RELAY_COMPLETED_VERIFIED'
  | 'FAILED';

export interface RelayState {
  max_robot_moves_per_turn?: number | null;
  robot_moves_this_turn?: number;
  remaining_turn_quota?: number | null;
  enabled: boolean;
  phase: RelayPhase;
  turn_indicator?: {
    owner: 'HUMAN' | 'CLARIFY' | 'ROBOT' | 'DONE' | 'FAILED' | 'IDLE' | string;
    owner_label_zh: string;
    stage_index: number;
    stage_labels: string[];
    next_action_hint_zh: string;
    is_terminal: boolean;
  };
  scramble_steps: number | string;
  resolved_scramble_steps: number;
  round_number: number;
  banner: {
    tone: 'slate' | 'blue' | 'amber' | 'violet' | 'emerald' | 'red';
    title_zh: string;
    subtitle_zh: string;
  };
  delegation: {
    suggested_moves: string[];
    completed_prefix_count: number;
    deviated_this_turn: boolean;
    delegation_reason_zh: string;
    message_zh: string;
    saved_high_cost_flips_count: number;
  };
  human_pad: {
    active: boolean;
    waiting_for_human: boolean;
    clicks_this_turn: string[];
    can_undo: boolean;
    highlighted_next_move: string | null;
  };
  perturbation: {
    dx_m: number;
    dy_m: number;
    dyaw_deg: number;
    bounds: {
      dx_min_m: number;
      dx_max_m: number;
      dy_min_m: number;
      dy_max_m: number;
      dyaw_min_deg: number;
      dyaw_max_deg: number;
    };
  };
  hri: {
    dialog_history: Array<{
      role: string;
      text: string;
      topic?: string | null;
      sim_time?: number;
      wall_time?: string;
      semantics?: {
        speech_act: string;
        requires_immediate_motion_interrupt: boolean;
        should_wake_robot_from_human_turn: boolean;
        persistent_constraints_to_add: string[];
        constraints_to_clear?: string[];
        deviation_intent?: string;
        rationale_zh?: string;
        confidence?: number;
        latency_ms?: number;
        provenance?: string;
      } | null;
    }>;
    active_constraints: string[];
    clarification_pending: boolean;
    clarification_question_zh: string | null;
    clarification_options: string[];
    clarification_topic: string | null;
    latest_semantics?: {
      speech_act: string;
      requires_immediate_motion_interrupt: boolean;
      should_wake_robot_from_human_turn: boolean;
      persistent_constraints_to_add: string[];
      constraints_to_clear?: string[];
      deviation_intent?: string;
      rationale_zh?: string;
      confidence?: number;
      latency_ms?: number;
      provenance?: string;
    } | null;
  };
  progress: {
    initial_optimal_steps: number | null;
    remaining_optimal_steps: number | null;
    completion_pct: number;
    robot_moves_count: number;
    human_turns_count: number;
    human_moves_inferred_count: number;
    is_solved: boolean;
    post_solve_independent_verified: boolean;
    round_tags: string[];
  };
  belief: {
    deduced_54_unique: boolean;
    ambiguous_facelet_count: number;
    ambiguous_facelet_indices: number[];
    occluded_face: string | null;
    inferred_human_moves: string[];
    human_deviation_detected: boolean;
    undo_conflict_risk: boolean;
    reasoning_summary_zh: string;
  };
  contract: {
    active_contract: {
      max_target_drift_m?: number;
      interrupt_on_human_chat_command?: boolean;
      mid_turn_recovery_mode?: string;
      abort_on_unexpected_flip?: boolean;
    } | null;
    is_lattice_aligned: boolean;
    residual_slice_angle_deg: number;
    latest_preemption: Record<string, unknown> | null;
    stale_guard: {
      current_epoch: number;
      stale_responses_discarded: number;
      last_invalidation_reason: string | null;
    };
    vlm_semantic_diagnosis: Record<string, unknown> | null;
  };
  cognitive_stats: {
    rapid_glance_deduction_successes: number;
    full_bottom_scans: number;
    on_demand_vlm_calls: number;
    fast_loop_contract_interceptions: number;
    stale_responses_discarded: number;
    clarifications_requested: number;
    saved_high_cost_flips: number;
  };
  cube_location?: string;
}

export type PlannerMode = 'DETERMINISTIC_PLANNER' | 'LLM_AGENT' | 'UNCONNECTED';

export type DecisionEventType =
  | 'MISSION_CREATED'
  | 'OBSERVATION_RECEIVED'
  | 'PLAN_CREATED'
  | 'PLAN_UPDATED'
  | 'ACTION_SELECTED'
  | 'SKILL_STARTED'
  | 'SKILL_COMPLETED'
  | 'SKILL_FAILED'
  | 'VERIFICATION_COMPLETED'
  | 'REPLAN_REQUESTED'
  | 'CAPABILITY_BLOCKED'
  | 'MISSION_COMPLETED'
  | 'MISSION_FAILED'
  | 'OBSERVATION_CAPTURED'
  | 'VLM_INFERENCE_STARTED'
  | 'VLM_INFERENCE_COMPLETED'
  | 'PERCEPTION_UPDATED'
  | 'AGENT_DECISION_STARTED'
  | 'AGENT_DECISION_COMPLETED'
  | 'SKILL_VALIDATED'
  | 'SKILL_REJECTED'
  | 'REOBSERVATION_COMPLETED'
  | 'REPLAN_TRIGGERED'
  | 'HANDOVER_COMPLETED'
  | 'HUMAN_TURN_FINISHED'
  | 'CLARIFICATION_REQUESTED'
  | 'HUMAN_CHAT_RECEIVED'
  | 'PREEMPTION_TRIGGERED'
  | 'STALE_RESPONSE_DISCARDED'
  | 'RAPID_GLANCE_DEDUCED';

export interface ObservationReference {
  observation_id: string;
  frame_id: string;
  sim_time: number;
  camera_name: string;
  observed_count: number;
  unknown_count: number;
  conflict_count: number;
  validation_status: string;
  reconstructed_facelets?: string | null;
  cube_center_world_m?: [number, number, number] | null;
  summary: string;
}

export interface MissionState {
  mission_id: string;
  session_id: string;
  mission_type: MissionType;
  user_goal: string;
  success_criteria: string;
  status: MissionStatus;
  current_plan_id?: string | null;
  created_at: string;
  completed_at?: string | null;
  result_summary?: string | null;
  blocked_reason?: string | null;
  blocked_move?: string | null;
  blocked_moves?: string[];
  symbolic_solution?: string[];
  failure_reason?: string | null;
}

export interface PlanStep {
  step_id: string;
  index: number;
  title: string;
  skill_id: string;
  description: string;
  status: StageStatus;
  implemented: boolean;
  parameters?: Record<string, unknown>;
  started_sim_time?: number | null;
  ended_sim_time?: number | null;
  started_wall_time?: string | null;
  ended_wall_time?: string | null;
  elapsed_sec?: number | null;
  result_summary?: string | null;
  failure_reason?: string | null;
  input_reference?: string | null;
  output_reference?: string | null;
}

export interface PlanState {
  plan_id: string;
  mission_id: string;
  mission_type: MissionType;
  planner_name: string;
  planner_mode: PlannerMode;
  created_at: string;
  updated_at: string;
  current_step_id?: string | null;
  steps: PlanStep[];
  rationale_summary: string;
  replan_count: number;
  replan_reason?: string | null;
}

export interface SkillExecutionState {
  execution_id: string;
  mission_id: string;
  plan_id: string;
  step_id: string;
  skill_id: string;
  skill_title: string;
  status: StageStatus;
  started_sim_time: number;
  ended_sim_time?: number | null;
  started_wall_time: string;
  ended_wall_time?: string | null;
  elapsed_sec?: number | null;
  parameters: Record<string, unknown>;
  result_summary: string;
  output_data: Record<string, unknown>;
  verification_passed?: boolean | null;
  failure_code?: string | null;
  failure_reason?: string | null;
}

export interface DecisionEvent {
  event_id: string;
  sequence: number;
  session_id: string;
  mission_id: string;
  plan_id?: string | null;
  event_type: DecisionEventType;
  source: string;
  sim_time?: number | null;
  wall_time: string;
  summary: string;
  decision_rationale_summary: string;
  selected_action?: string | null;
  skill_id?: string | null;
  input_reference?: string | null;
  output_reference?: string | null;
  status: string;
  failure_reason?: string | null;
  planner_mode?: string | null;
  model_provider?: string | null;
  model_name?: string | null;
  observation_id?: string | null;
  input_frame_ids?: string[];
  action_candidates?: string[];
  parameters?: Record<string, unknown>;
  expected_information_gain?: string | null;
  confidence?: number | null;
  validation_result?: string | null;
  skill_execution_id?: string | null;
  feedback_observation_id?: string | null;
  model_latency_ms?: number | null;
  token_usage?: Record<string, unknown> | null;
}

export type TraceEventType =
  | 'mission'
  | 'composite_skill'
  | 'action'
  | 'perception'
  | 'decision'
  | 'verification';

export interface TraceEvent {
  event_id: string;
  parent_event_id?: string | null;
  sequence: number;
  mission_id: string;
  session_id: string;
  skill_id?: string | null;
  event_type: TraceEventType;
  name: string;
  source: string;
  status: string;
  sim_time: number;
  end_sim_time?: number | null;
  wall_time: string;
  duration?: number | null;
  evidence: Record<string, any>;
  failure_reason?: string | null;
}

export interface SkillDescriptor {
  skill_id: string;
  title: string;
  description: string;
  category: string;
  implemented: boolean;
  is_physical_action: boolean;
  required_preconditions: string[];
  required_observations: string[];
  supported_parameters: Record<string, string>;
  supported_physical_actions: string[];
  expected_outputs: string[];
  verification_method: string;
  failure_codes: string[];
}

export interface CapabilityRegistrySnapshot {
  skills: SkillDescriptor[];
  symbolic_supported_moves: string[];
  physical_supported_moves: string[];
  physical_limitations_summary: string;
}

export interface AgentObservabilityState {
  planner_mode: PlannerMode;
  planner_name: string;
  llm_connected: boolean;
  llm_model?: string | null;
  model_provider?: string | null;
  status_label: string;
  latest_observation?: ObservationReference | null;
  current_observation_id?: string | null;
  current_frame_id?: string | null;
  current_camera_id?: string | null;
  current_observation_image_url?: string | null;
  selected_action?: string | null;
  selected_parameters?: Record<string, unknown>;
  selection_rationale?: string | null;
  expected_information_gain?: string | null;
  confidence?: number | null;
  safety_gate_status?: string | null;
  safety_gate_detail?: string | null;
  last_skill_call?: string | null;
  last_execution_feedback?: string | null;
  next_decision_hint?: string | null;
  blocked_or_replan_reason?: string | null;
  model_latency_ms?: number | null;
  total_vlm_calls?: number;
  total_input_tokens?: number;
  total_output_tokens?: number;
  fallback_triggered?: boolean;
  fallback_reason?: string | null;
  perception_model_provider?: string | null;
  perception_model_name?: string | null;
  perception_connected?: boolean;
  perception_latency_ms?: number | null;
  agent_model_provider?: string | null;
  agent_model_name?: string | null;
  agent_connected?: boolean;
  agent_latency_ms?: number | null;
  latest_semantic_observation?: {
    observation_id: string;
    frame_id: string;
    camera_id: string;
    cube_visible: boolean;
    cube_relation_to_gripper: string;
    support_relation: string;
    visible_regions: string[];
    occluded_regions: string[];
    information_gaps: string[];
    suggested_observations: string[];
    visual_conflicts: string[];
    confidence: number;
    summary: string;
  } | null;
}

export interface TaskStage {
  id: string;
  index: number;
  title: string;
  skillName: string;
  status: StageStatus;
  implemented: boolean;
  elapsedSec?: number;
}

export interface FaceletObservation {
  index: number; // 0..53 (U:0-8, R:9-17, F:18-26, D:27-35, L:36-44, B:45-53)
  face: FaceId;
  localIdx: number; // 0..8
  color: FaceletColor;
  confidence?: number;
  observationCount: number;
  hasConflict: boolean;
}

export interface CameraDetectionBox {
  id: string;
  face: FaceId;
  localIdx: number;
  xNorm: number;
  yNorm: number;
  wNorm: number;
  hNorm: number;
  color: FaceletColor;
  confidence: number;
}

export interface RobotTelemetry {
  contactForceN: number | null;
  gripperWidthMm: number | null;
  gripperState: 'OPEN' | 'CLOSING' | 'GRASPED' | 'SLIP_ALERT' | 'UNKNOWN';
  jointPositionsRad: Record<string, number> | null;
  cubePositionMm: [number, number, number] | null;
  layerTurnAngleDeg: number | null;
  targetLayer: string | null;
  collisionDetected: boolean | null;
  slipDetected: boolean | null;
  renderFps: number | null;
  failureReason: string | null;
}

export interface TimelineEvent {
  event_id: string;
  short_label: string;
  sim_time: number;
  wall_time: string;
  skill_name: string;
  stage_id: string;
  duration_sec?: number;
  status: 'STARTED' | 'VERIFIED' | 'FAILED' | 'ABORTED';
  failure_reason?: string;
  summary: string;
  turn_angle_deg: number;
  contact_force_n: number;
  gripper_width_mm: number;
  gripper_state: RobotTelemetry['gripperState'];
  completed_stage_index: number;
}

export interface SimulationSnapshot {
  session_id: string;
  seed: number;
  sim_time: number;
  wall_time: string;
  frame_source?: 'REAL_MUJOCO_RENDERER' | 'SYNTHETIC_SAMPLE' | 'REPLAY_FILE' | 'NONE';
  active_camera: CameraPresetId;
  camera_azimuth_deg: number;
  camera_elevation_deg: number;
  camera_distance_m: number;
  main_frame_url: string | null;
  wrist_rgb_url: string | null;
  wrist_depth_url: string | null;
  depth_range_m: [number, number];
  detections: CameraDetectionBox[];
  task_status: 'IDLE' | 'RUNNING' | 'WAITING_FOR_HUMAN_TURN' | 'PAUSED' | 'COMPLETED' | 'FAILED' | 'STOPPED';
  relay_phase?: RelayPhase;
  relay_state?: RelayState | null;
  current_stage_id: string;
  current_skill: string;
  stages: TaskStage[];
  observed_facelets: FaceletObservation[];
  predicted_facelets: FaceletColor[];
  cube_validation_status: 'UNVERIFIED' | 'INCOMPLETE' | 'CONFLICT' | 'VALID_SOLVABLE' | 'INVALID_STATE';
  telemetry: RobotTelemetry;
  timeline: TimelineEvent[];
  selected_mission_type?: MissionType;
  mission?: MissionState | null;
  plan?: PlanState | null;
  skill_executions?: SkillExecutionState[];
  decision_events?: DecisionEvent[];
  trace_events?: TraceEvent[];
  observations?: Array<{
    observation_id: string;
    frame_id?: string;
    camera_ids: string[];
    frame_refs: string[];
    visual_summary: string;
    coverage: number;
    sim_time: number;
    image_url?: string;
    frame_source?: string;
  }>;
  capabilities?: CapabilityRegistrySnapshot | null;
  agent_state?: AgentObservabilityState | null;
  physical_verification?: Record<string, unknown> | null;
  last_observation_ref?: ObservationReference | null;
  timing_metrics?: {
    sim_time: number;
    skill_duration_sim_s: number;
    total_execution_wall_s: number;
    model_latency_ms: number;
    vlm_calls: number;
    input_tokens: number;
    output_tokens: number;
  } | null;
  running?: boolean;
  run_id?: string | null;
  experiment_recording?: {
    run_id?: string | null;
    status?: string;
    include_audit_ground_truth?: boolean;
    trajectory_sample_hz?: number;
    counts?: Record<string, number>;
  } | null;
}

export interface HistoricalRunSummary {
  run_id: string;
  session_id?: string;
  seed?: number;
  mission_type?: string;
  planner_mode?: string;
  recording_status?: string;
  sim_time?: number;
  updated_utc?: string;
  counts?: Record<string, number>;
}

export interface ReplayTimingFile {
  session_id: string;
  seed: number;
  duration_sec: number;
  frames: Array<{
    video_time_sec: number;
    sim_time: number;
    current_stage_id: string;
    current_skill: string;
    task_status: SimulationSnapshot['task_status'];
    observed_facelets: FaceletObservation[];
    predicted_facelets: FaceletColor[];
    cube_validation_status: SimulationSnapshot['cube_validation_status'];
    telemetry: RobotTelemetry;
  }>;
  timeline: TimelineEvent[];
  trace_events?: TraceEvent[];
  observations?: SimulationSnapshot['observations'];
}

// ============================================================================
// 2. 常量、Mission 定义与内置合成样本包 (严格仅限 SAMPLE 模式使用)
// ============================================================================

const FACE_ORDER: FaceId[] = ['U', 'R', 'F', 'D', 'L', 'B'];

const MISSION_OPTIONS: Array<{
  type: MissionType;
  label: string;
  shortDesc: string;
  capabilityNote: string;
}> = [
  {
    type: 'INSPECT_CUBE',
    label: '六面扫描',
    shortDesc: '主动感知并输出 54 格合法性校验（不转面）',
    capabilityNote: '已实现 · 仅调用 RGB-D 定位、多视角扫描与状态校验',
  },
  {
    type: 'VERIFY_PHYSICAL_U_TURN',
    label: 'U 层物理转动验证',
    shortDesc: 'M3-B 基线：扫描 + 搬运 + 接触拧 U + 21 格复核',
    capabilityNote: '已实现 · 仅支持单次顺时针 U (+90°) 接触驱动',
  },
  {
    type: 'SOLVE_CUBE',
    label: '魔方完整求解',
    shortDesc: '扫描 + Kociemba 求解 + 物理能力边界核查',
    capabilityNote: '受能力限制 · 若含 R/F/L/B/D/U\'/U2 将触发 CAPABILITY_BLOCKED',
  },
  {
    type: 'RELAY_SOLVE_CUBE',
    label: '人机接力复原',
    shortDesc: 'Gemini Agent 全自主接力 + 26-Cubie 物理求解',
    capabilityNote: '全自主闭环 · 1s快瞄/25s翻扫权衡 · 18动作自由盘 + 自然语言契约协同',
  },
];

const COLOR_MAP: Record<FaceletColor, { bg: string; border: string; text: string; label: string }> = {
  W: { bg: '#F1F5F9', border: '#CBD5E1', text: '#0F172A', label: '白 W' },
  Y: { bg: '#FACC15', border: '#EAB308', text: '#0F172A', label: '黄 Y' },
  G: { bg: '#22C55E', border: '#16A34A', text: '#052E16', label: '绿 G' },
  B: { bg: '#3B82F6', border: '#2563EB', text: '#EFF6FF', label: '蓝 B' },
  O: { bg: '#F97316', border: '#EA580C', text: '#FFF7ED', label: '橙 O' },
  R: { bg: '#EF4444', border: '#DC2626', text: '#FEF2F2', label: '红 R' },
  UNKNOWN: { bg: '#182338', border: '#334155', text: '#94A3B8', label: '未知 ?' },
};

const CAMERA_PRESETS: Array<{ id: CameraPresetId; label: string; desc: string; az: number; el: number; dist: number }> = [
  { id: 'cube_closeup', label: '魔方特写', desc: '26-Cubie 魔方跟拍特写（推荐）', az: 132, el: -28, dist: 0.28 },
  { id: 'gripper_closeup', label: '夹爪特写', desc: '末端双指夹持接触局部机位', az: 146, el: -22, dist: 0.36 },
  { id: 'overview', label: '场景总览', desc: '3/4 实验室工作站全局机位', az: 135, el: -28, dist: 1.15 },
  { id: 'top_ortho', label: '俯视相机', desc: '龙门架 XY 平面正交俯视', az: 90, el: -86, dist: 0.95 },
];

const SAMPLE_PREDICTED_COLORS: FaceletColor[] = [
  'W', 'R', 'G', 'B', 'W', 'Y', 'O', 'W', 'B',
  'R', 'B', 'Y', 'G', 'R', 'W', 'O', 'R', 'B',
  'G', 'Y', 'R', 'W', 'G', 'O', 'B', 'G', 'Y',
  'Y', 'W', 'O', 'R', 'Y', 'G', 'W', 'B', 'Y',
  'O', 'G', 'W', 'R', 'O', 'B', 'Y', 'O', 'G',
  'B', 'O', 'W', 'Y', 'B', 'G', 'R', 'B', 'O',
];

function createSampleObservedFacelets(afterTurn: boolean): FaceletObservation[] {
  const uPerm = afterTurn ? [6, 3, 0, 7, 4, 1, 8, 5, 2] : [0, 1, 2, 3, 4, 5, 6, 7, 8];
  const baseColors = [...SAMPLE_PREDICTED_COLORS];

  if (afterTurn) {
    const oldU = baseColors.slice(0, 9);
    uPerm.forEach((srcIdx, dstIdx) => {
      baseColors[dstIdx] = oldU[srcIdx];
    });
    const oldR = baseColors.slice(9, 12);
    const oldF = baseColors.slice(18, 21);
    const oldL = baseColors.slice(36, 39);
    const oldB = baseColors.slice(45, 48);
    baseColors.splice(36, 3, ...oldF);
    baseColors.splice(45, 3, ...oldL);
    baseColors.splice(9, 3, ...oldB);
    baseColors.splice(18, 3, ...oldR);
  }

  return baseColors.map((color, index) => {
    const faceIdx = Math.floor(index / 9);
    const face = FACE_ORDER[faceIdx];
    const localIdx = index % 9;
    const isOccludedBottom = afterTurn && face === 'D';
    return {
      index,
      face,
      localIdx,
      color: isOccludedBottom ? 'UNKNOWN' : color,
      confidence: isOccludedBottom ? undefined : 0.964 + ((index * 7) % 4) * 0.008,
      observationCount: isOccludedBottom ? 0 : 3,
      hasConflict: false,
    };
  });
}

const SAMPLE_TIMELINE: TimelineEvent[] = [
  {
    event_id: 'ev-1',
    short_label: '00:01.20 定位观测',
    sim_time: 1.2,
    wall_time: '03:18:08',
    skill_name: 'observe_workspace',
    stage_id: 'step-1',
    duration_sec: 0.42,
    status: 'VERIFIED',
    summary: '顶部 RGB-D 定位魔方中心 (SYNTHETIC SAMPLE)',
    turn_angle_deg: 0.0,
    contact_force_n: 0.0,
    gripper_width_mm: 256.0,
    gripper_state: 'OPEN',
    completed_stage_index: 1,
  },
  {
    event_id: 'ev-2',
    short_label: '00:34.20 六面扫描',
    sim_time: 34.2,
    wall_time: '03:18:40',
    skill_name: 'active_six_face_scan',
    stage_id: 'step-2',
    duration_sec: 33.0,
    status: 'VERIFIED',
    summary: '完成 54/54 贴片主动扫描与融合 (SYNTHETIC SAMPLE)',
    turn_angle_deg: 0.0,
    contact_force_n: 0.0,
    gripper_width_mm: 256.0,
    gripper_state: 'OPEN',
    completed_stage_index: 3,
  },
  {
    event_id: 'ev-3',
    short_label: '00:58.74 物理转面',
    sim_time: 58.74,
    wall_time: '03:19:05',
    skill_name: 'execute_physical_u_turn',
    stage_id: 'step-5',
    duration_sec: 24.5,
    status: 'VERIFIED',
    summary: '外置夹具接触驱动 U 层转动 +90.0° (SYNTHETIC SAMPLE)',
    turn_angle_deg: 90.0,
    contact_force_n: 3.46,
    gripper_width_mm: 256.0,
    gripper_state: 'OPEN',
    completed_stage_index: 5,
  },
  {
    event_id: 'ev-4',
    short_label: '01:01.17 视觉复核',
    sim_time: 61.17,
    wall_time: '03:19:08',
    skill_name: 'verify_post_turn_state',
    stage_id: 'step-6',
    duration_sec: 2.43,
    status: 'VERIFIED',
    summary: 'U 层相关 21 格视觉复核通过，D 面保持未知 (SYNTHETIC SAMPLE)',
    turn_angle_deg: 90.0,
    contact_force_n: 3.46,
    gripper_width_mm: 256.0,
    gripper_state: 'OPEN',
    completed_stage_index: 6,
  },
];

// ============================================================================
// 3. 合成样本帧生成器 (严禁在 LIVE 模式调用，仅限 SAMPLE 模式合成演示图)
// ============================================================================

function generateOffscreenMujocoFrameUrl(
  preset: CameraPresetId,
  turnAngleDeg: number,
  debugOverlays: { contactForces: boolean; collisionGeoms: boolean; tcpFrame: boolean }
): string {
  if (typeof document === 'undefined') return '';

  const W = 1280;
  const H = 720;
  const canvas = document.createElement('canvas');
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext('2d');
  if (!ctx) return '';

  const roomGrad = ctx.createLinearGradient(0, 0, 0, H);
  roomGrad.addColorStop(0, '#232B38');
  roomGrad.addColorStop(0.48, '#19212E');
  roomGrad.addColorStop(1, '#0E141F');
  ctx.fillStyle = roomGrad;
  ctx.fillRect(0, 0, W, H);

  let zoom = 1.0;
  let cx = W * 0.5;
  let cy = H * 0.56;
  let isTop = false;
  if (preset === 'gripper_closeup') {
    zoom = 1.72;
    cy = H * 0.53;
  } else if (preset === 'cube_closeup') {
    zoom = 2.28;
    cy = H * 0.47;
  } else if (preset === 'top_ortho') {
    isTop = true;
    zoom = 1.15;
    cy = H * 0.51;
  }

  ctx.save();
  ctx.translate(cx, cy);
  ctx.scale(zoom, zoom);

  if (!isTop) {
    const tableGrad = ctx.createLinearGradient(0, -45, 0, 225);
    tableGrad.addColorStop(0, '#222B3B');
    tableGrad.addColorStop(1, '#141B27');
    ctx.fillStyle = tableGrad;
    ctx.beginPath();
    ctx.moveTo(-560, 210);
    ctx.lineTo(-365, -42);
    ctx.lineTo(365, -42);
    ctx.lineTo(560, 210);
    ctx.closePath();
    ctx.fill();
    ctx.strokeStyle = '#3B485E';
    ctx.lineWidth = 2;
    ctx.stroke();

    // 龙门架示意
    ctx.fillStyle = '#475569';
    ctx.fillRect(-465, -245, 32, 443);
    ctx.fillRect(433, -245, 32, 443);
    ctx.fillStyle = '#64748B';
    ctx.fillRect(-475, -252, 950, 44);
    ctx.fillStyle = '#0F172A';
    ctx.fillRect(-72, -258, 144, 56);
    ctx.fillStyle = '#38BDF8';
    ctx.fillRect(-58, -248, 116, 4);
  } else {
    ctx.fillStyle = '#1B2332';
    ctx.fillRect(-440, -260, 880, 520);
  }

  const rad = (turnAngleDeg * Math.PI) / 180;
  const isTurned90 = Math.abs(turnAngleDeg - 90) < 0.5;
  const skewShift = Math.sin(rad) * 22;

  if (isTop) {
    ctx.save();
    ctx.rotate(rad);
    ctx.fillStyle = '#0D1117';
    ctx.fillRect(-68, -68, 136, 136);
    const uCols: FaceletColor[] = ['W', 'R', 'G', 'B', 'W', 'Y', 'O', 'W', 'B'];
    uCols.forEach((c, i) => {
      const r = Math.floor(i / 3);
      const col = i % 3;
      ctx.fillStyle = COLOR_MAP[c].bg;
      ctx.fillRect(-58 + col * 40, -58 + r * 40, 36, 36);
    });
    ctx.restore();
  } else {
    ctx.fillStyle = '#0D1117';
    ctx.fillRect(-68, 38, 136, 74);
    const midBotCols: FaceletColor[] = ['W', 'G', 'O', 'B', 'G', 'Y'];
    midBotCols.forEach((c, idx) => {
      const r = Math.floor(idx / 3);
      const col = idx % 3;
      ctx.fillStyle = COLOR_MAP[c].bg;
      ctx.fillRect(-59 + col * 40, 44 + r * 32, 36, 27);
    });

    ctx.save();
    ctx.translate(skewShift * 0.42, 0);
    ctx.fillStyle = '#0D1117';
    ctx.fillRect(-70, 0, 140, 35);
    const topRowCols: FaceletColor[] = isTurned90 ? ['R', 'B', 'Y'] : ['G', 'Y', 'R'];
    topRowCols.forEach((c, col) => {
      ctx.fillStyle = COLOR_MAP[c].bg;
      ctx.fillRect(-60 + col * 41, 5, 37, 25);
    });
    ctx.restore();
  }

  if (debugOverlays.collisionGeoms) {
    ctx.strokeStyle = '#548CFF';
    ctx.setLineDash([6, 4]);
    ctx.lineWidth = 1.8;
    ctx.strokeRect(-74, -6, 148, 122);
    ctx.setLineDash([]);
  }
  if (debugOverlays.contactForces) {
    ctx.fillStyle = '#FFBF69';
    ctx.font = 'bold 13px monospace';
    ctx.fillText('SAMPLE FORCE', -120, 10);
  }
  ctx.restore();

  // 合成样本水印（防止与真实 MuJoCo 渲染混淆）
  ctx.fillStyle = 'rgba(255, 191, 105, 0.9)';
  ctx.font = 'bold 16px monospace';
  ctx.fillText('SYNTHETIC SAMPLE · Canvas 2D (非真实 MuJoCo 帧)', 24, 34);

  return canvas.toDataURL('image/png');
}

function generateSampleCameraFrames(afterTurn: boolean): {
  rgbUrl: string;
  depthUrl: string;
  detections: CameraDetectionBox[];
} {
  if (typeof document === 'undefined') {
    return { rgbUrl: '', depthUrl: '', detections: [] };
  }

  const w = 480;
  const h = 300;
  const rgbCanvas = document.createElement('canvas');
  rgbCanvas.width = w;
  rgbCanvas.height = h;
  const ctx = rgbCanvas.getContext('2d')!;
  ctx.fillStyle = '#111827';
  ctx.fillRect(0, 0, w, h);

  const cubeX = 155;
  const cubeY = 58;
  const cubeSize = 170;
  ctx.fillStyle = '#0f131a';
  ctx.fillRect(cubeX, cubeY, cubeSize, cubeSize);

  const fColors: FaceletColor[] = afterTurn
    ? ['R', 'B', 'Y', 'W', 'G', 'O', 'B', 'G', 'Y']
    : ['G', 'Y', 'R', 'W', 'G', 'O', 'B', 'G', 'Y'];
  const detections: CameraDetectionBox[] = [];
  const pad = 10;
  const gap = 6;
  const cell = (cubeSize - pad * 2 - gap * 2) / 3;

  fColors.forEach((c, idx) => {
    const r = Math.floor(idx / 3);
    const col = idx % 3;
    const x = cubeX + pad + col * (cell + gap);
    const y = cubeY + pad + r * (cell + gap);
    ctx.fillStyle = COLOR_MAP[c].bg;
    ctx.fillRect(x, y, cell, cell);
    detections.push({
      id: `det-F-${idx}`,
      face: 'F',
      localIdx: idx,
      xNorm: x / w,
      yNorm: y / h,
      wNorm: cell / w,
      hNorm: cell / h,
      color: c,
      confidence: 0.975,
    });
  });

  ctx.fillStyle = '#FFBF69';
  ctx.font = '11px monospace';
  ctx.fillText('SYNTHETIC SAMPLE · RGB', 12, 20);

  const depthCanvas = document.createElement('canvas');
  depthCanvas.width = w;
  depthCanvas.height = h;
  const dctx = depthCanvas.getContext('2d')!;
  dctx.fillStyle = '#0f172a';
  dctx.fillRect(0, 0, w, h);
  dctx.fillStyle = '#06b6d4';
  dctx.fillRect(cubeX, cubeY, cubeSize, cubeSize);
  dctx.fillStyle = '#FFBF69';
  dctx.font = '11px monospace';
  dctx.fillText('SYNTHETIC SAMPLE · DEPTH', 12, 20);

  return {
    rgbUrl: rgbCanvas.toDataURL('image/png'),
    depthUrl: depthCanvas.toDataURL('image/png'),
    detections,
  };
}

function createSampleSnapshot(missionType: MissionType, event?: TimelineEvent): SimulationSnapshot {
  const ev = event || SAMPLE_TIMELINE[SAMPLE_TIMELINE.length - 1];
  const isTurnMission = missionType === 'VERIFY_PHYSICAL_U_TURN';
  const afterTurn = isTurnMission && ev.turn_angle_deg >= 89.5;
  const camData = generateSampleCameraFrames(afterTurn);
  const mainFrameUrl = generateOffscreenMujocoFrameUrl(
    'overview',
    isTurnMission ? ev.turn_angle_deg : 0.0,
    { contactForces: true, collisionGeoms: false, tcpFrame: true }
  );

  const planStepsByMission: Record<MissionType, PlanStep[]> = {
    INSPECT_CUBE: [
      {
        step_id: 'smp-s1',
        index: 1,
        title: '工作站观察与定位',
        skill_id: 'observe_workspace',
        description: '顶部 RGB-D 定位魔方中心',
        status: 'VERIFIED',
        implemented: true,
        started_sim_time: 0.4,
        ended_sim_time: 1.2,
        elapsed_sec: 0.8,
        result_summary: '样本：已定位魔方中心 (SYNTHETIC SAMPLE)',
      },
      {
        step_id: 'smp-s2',
        index: 2,
        title: '六面主动扫描',
        skill_id: 'active_six_face_scan',
        description: '主动多视角扫描并融合 54 格',
        status: 'VERIFIED',
        implemented: true,
        started_sim_time: 1.2,
        ended_sim_time: 34.2,
        elapsed_sec: 33.0,
        result_summary: '样本：54/54 贴片观测完整 (SYNTHETIC SAMPLE)',
      },
      {
        step_id: 'smp-s3',
        index: 3,
        title: '54 格合法性校验',
        skill_id: 'validate_cube_state',
        description: '验证 54 格颜色数量与群论可解性',
        status: 'VERIFIED',
        implemented: true,
        started_sim_time: 34.2,
        ended_sim_time: 34.25,
        elapsed_sec: 0.05,
        result_summary: '样本：状态合法可解，未调用任何物理转面',
      },
    ],
    VERIFY_PHYSICAL_U_TURN: [
      {
        step_id: 'smp-u1',
        index: 1,
        title: '工作站观察与定位',
        skill_id: 'observe_workspace',
        description: '顶部 RGB-D 定位',
        status: 'VERIFIED',
        implemented: true,
        started_sim_time: 0.4,
        ended_sim_time: 1.2,
        elapsed_sec: 0.8,
        result_summary: '样本：已定位魔方中心',
      },
      {
        step_id: 'smp-u2',
        index: 2,
        title: '六面主动扫描',
        skill_id: 'active_six_face_scan',
        description: '54 格扫描',
        status: 'VERIFIED',
        implemented: true,
        started_sim_time: 1.2,
        ended_sim_time: 34.2,
        elapsed_sec: 33.0,
        result_summary: '样本：54/54 贴片融合成功',
      },
      {
        step_id: 'smp-u3',
        index: 3,
        title: '54 格合法性校验',
        skill_id: 'validate_cube_state',
        description: '合法性校验',
        status: 'VERIFIED',
        implemented: true,
        started_sim_time: 34.2,
        ended_sim_time: 34.25,
        elapsed_sec: 0.05,
        result_summary: '样本：VALID_SOLVABLE',
      },
      {
        step_id: 'smp-u4',
        index: 4,
        title: '计算 U 转动符号期望',
        skill_id: 'compute_symbolic_plan',
        description: '符号期望计算',
        status: 'VERIFIED',
        implemented: true,
        started_sim_time: 34.25,
        ended_sim_time: 34.26,
        elapsed_sec: 0.01,
        result_summary: '样本：生成单步 U 期望状态',
      },
      {
        step_id: 'smp-u5',
        index: 5,
        title: '接触驱动 U 层物理转动',
        skill_id: 'execute_physical_u_turn',
        description: 'ContactUTurn 夹具接触拧 U',
        status: afterTurn ? 'VERIFIED' : 'RUNNING',
        implemented: true,
        started_sim_time: 34.26,
        ended_sim_time: afterTurn ? 58.74 : undefined,
        elapsed_sec: afterTurn ? 24.48 : undefined,
        result_summary: afterTurn ? '样本：U 层转角 90.0°' : '样本：执行中...',
      },
      {
        step_id: 'smp-u6',
        index: 6,
        title: '转后 21 格视觉复核',
        skill_id: 'verify_post_turn_state',
        description: '独立相机复核受影响 21 格',
        status: afterTurn ? 'VERIFIED' : 'PENDING',
        implemented: true,
        started_sim_time: afterTurn ? 58.74 : undefined,
        ended_sim_time: afterTurn ? 61.17 : undefined,
        elapsed_sec: afterTurn ? 2.43 : undefined,
        result_summary: afterTurn ? '样本：21/21 匹配，D 面保留 UNKNOWN' : undefined,
      },
    ],
    SOLVE_CUBE: [
      {
        step_id: 'smp-k1',
        index: 1,
        title: '工作站观察与定位',
        skill_id: 'observe_workspace',
        description: '顶部 RGB-D 定位',
        status: 'VERIFIED',
        implemented: true,
        started_sim_time: 0.4,
        ended_sim_time: 1.2,
        elapsed_sec: 0.8,
        result_summary: '样本：已定位魔方中心',
      },
      {
        step_id: 'smp-k2',
        index: 2,
        title: '六面主动扫描',
        skill_id: 'active_six_face_scan',
        description: '54 格扫描',
        status: 'VERIFIED',
        implemented: true,
        started_sim_time: 1.2,
        ended_sim_time: 34.2,
        elapsed_sec: 33.0,
        result_summary: '样本：54/54 贴片融合成功',
      },
      {
        step_id: 'smp-k3',
        index: 3,
        title: '54 格合法性校验',
        skill_id: 'validate_cube_state',
        description: '合法性校验',
        status: 'VERIFIED',
        implemented: true,
        started_sim_time: 34.2,
        ended_sim_time: 34.25,
        elapsed_sec: 0.05,
        result_summary: '样本：VALID_SOLVABLE',
      },
      {
        step_id: 'smp-k4',
        index: 4,
        title: 'Kociemba 符号求解',
        skill_id: 'compute_symbolic_plan',
        description: '生成完整还原步序',
        status: 'VERIFIED',
        implemented: true,
        started_sim_time: 34.25,
        ended_sim_time: 34.27,
        elapsed_sec: 0.02,
        result_summary: "样本：符号求解 21 步 [U', F', R2, ...]",
      },
      {
        step_id: 'smp-k5',
        index: 5,
        title: '物理能力边界核查',
        skill_id: 'check_physical_capability',
        description: '检查每步是否具有真实物理 Skill',
        status: 'BLOCKED',
        implemented: true,
        started_sim_time: 34.27,
        ended_sim_time: 34.27,
        elapsed_sec: 0.0,
        result_summary: "样本：能力阻塞于动作 U' / F' / R2",
        failure_reason: '当前仅支持单次顺时针 U 接触物理转面，不支持任意六面连续物理求解。',
      },
    ],
    RELAY_SOLVE_CUBE: [
      {
        step_id: 'smp-r1',
        index: 1,
        title: 'Agent 主动扫描建信与交接',
        skill_id: 'handover_to_human',
        description: 'Gemini-3.8-Flash 自主权衡翻面代价并交接桌面',
        status: 'VERIFIED',
        implemented: true,
        started_sim_time: 0.4,
        ended_sim_time: 35.1,
        elapsed_sec: 34.7,
        result_summary: '样本：已提交低代价 U 并于 2-Flip D2 前安全移交桌面',
      },
    ],
  };

  const steps = planStepsByMission[missionType];
  const missionStatus: MissionStatus =
    missionType === 'SOLVE_CUBE'
      ? 'BLOCKED_CAPABILITY'
      : isTurnMission && !afterTurn
      ? 'EXECUTING'
      : 'COMPLETED';
  const spec = MISSION_OPTIONS.find((m) => m.type === missionType)!;

  const sampleDecisionEvents: DecisionEvent[] = [
    {
      event_id: 'de-smp-1',
      sequence: 1,
      session_id: 'SAMPLE-SEED0',
      mission_id: `msn-smp-${missionType}`,
      plan_id: `plan-smp-${missionType}`,
      event_type: 'MISSION_CREATED',
      source: 'SamplePacket',
      sim_time: 0.4,
      wall_time: '03:18:07',
      summary: `[SYNTHETIC SAMPLE] 创建样本任务 ${spec.label} (${missionType})`,
      decision_rationale_summary: '此为离线 SYNTHETIC SAMPLE 数据包，请切换至 LIVE 实时仿真运行真实 MuJoCo 后端。',
      selected_action: missionType,
      status: 'CREATED',
    },
    {
      event_id: 'de-smp-2',
      sequence: 2,
      session_id: 'SAMPLE-SEED0',
      mission_id: `msn-smp-${missionType}`,
      plan_id: `plan-smp-${missionType}`,
      event_type: missionType === 'SOLVE_CUBE' ? 'CAPABILITY_BLOCKED' : 'MISSION_COMPLETED',
      source: 'DeterministicMissionPlanner',
      sim_time: missionType === 'SOLVE_CUBE' ? 34.27 : 61.17,
      wall_time: '03:19:08',
      summary:
        missionType === 'SOLVE_CUBE'
          ? "[SYNTHETIC SAMPLE] 动作 U' / R2 超出单层物理能力，触发 CAPABILITY_BLOCKED"
          : `[SYNTHETIC SAMPLE] 样本任务 ${spec.label} 展示完成`,
      decision_rationale_summary:
        missionType === 'SOLVE_CUBE'
          ? 'Kociemba 求解生成多面序列，但 SkillRegistry 声明物理能力仅覆盖单次 U 顺时针转层。'
          : '样本演示路径按任务目标生成对应计划（与其它任务不同）。',
      selected_action: steps[steps.length - 1].skill_id,
      skill_id: steps[steps.length - 1].skill_id,
      status: missionStatus,
      failure_reason:
        missionType === 'SOLVE_CUBE'
          ? '物理能力仅支持单次顺时针 U 转面，不支持任意六面物理执行。'
          : null,
    },
  ];

  return {
    session_id: 'SYNTHETIC-SAMPLE-SEED0',
    seed: 0,
    sim_time: isTurnMission ? ev.sim_time : 34.27,
    wall_time: ev.wall_time,
    frame_source: 'SYNTHETIC_SAMPLE',
    active_camera: missionType === 'RELAY_SOLVE_CUBE' ? 'cube_closeup' : 'overview',
    camera_azimuth_deg: missionType === 'RELAY_SOLVE_CUBE' ? 132 : 135,
    camera_elevation_deg: -28,
    camera_distance_m: missionType === 'RELAY_SOLVE_CUBE' ? 0.28 : 1.15,
    main_frame_url: mainFrameUrl || null,
    wrist_rgb_url: camData.rgbUrl || null,
    wrist_depth_url: camData.depthUrl || null,
    depth_range_m: [0.35, 2.25],
    detections: camData.detections,
    task_status:
      missionStatus === 'COMPLETED' ? 'COMPLETED' : missionStatus === 'BLOCKED_CAPABILITY' ? 'FAILED' : 'RUNNING',
    current_stage_id: steps[steps.length - 1].step_id,
    current_skill: steps[steps.length - 1].skill_id,
    stages: steps.map((s) => ({
      id: s.step_id,
      index: s.index,
      title: s.title,
      skillName: s.skill_id,
      status: s.status,
      implemented: s.implemented,
      elapsedSec: s.elapsed_sec ?? undefined,
    })),
    observed_facelets: createSampleObservedFacelets(afterTurn),
    predicted_facelets: SAMPLE_PREDICTED_COLORS,
    cube_validation_status: afterTurn ? 'INCOMPLETE' : 'VALID_SOLVABLE',
    telemetry: {
      contactForceN: isTurnMission ? ev.contact_force_n : 0.0,
      gripperWidthMm: ev.gripper_width_mm,
      gripperState: ev.gripper_state,
      jointPositionsRad: {
        robot_x: 0.35,
        robot_y: -0.32,
        robot_z: -0.02,
        wrist_yaw: 1.57,
        u_layer: afterTurn ? -1.571 : 0.0,
      },
      cubePositionMm: [350.0, -320.0, 665.0],
      layerTurnAngleDeg: isTurnMission ? ev.turn_angle_deg : 0.0,
      targetLayer: isTurnMission ? 'U' : null,
      collisionDetected: false,
      slipDetected: false,
      renderFps: 30.0,
      failureReason: missionType === 'SOLVE_CUBE' ? 'CAPABILITY_BLOCKED' : null,
    },
    timeline: SAMPLE_TIMELINE,
    selected_mission_type: missionType,
    mission: {
      mission_id: `msn-smp-${missionType}`,
      session_id: 'SYNTHETIC-SAMPLE-SEED0',
      mission_type: missionType,
      user_goal: spec.shortDesc,
      success_criteria: spec.capabilityNote,
      status: missionStatus,
      current_plan_id: `plan-smp-${missionType}`,
      created_at: '03:18:07',
      completed_at: '03:19:08',
      result_summary:
        missionType === 'SOLVE_CUBE'
          ? 'SYNTHETIC SAMPLE：符号求解完成，物理执行因能力不足被阻断。'
          : `SYNTHETIC SAMPLE：${spec.label}样本预览。`,
      blocked_reason:
        missionType === 'SOLVE_CUBE'
          ? "当前 MuJoCo 场景仅建模单层 U 顺时针接触夹具，不支持动作 U' / F' / R2。"
          : null,
      blocked_move: missionType === 'SOLVE_CUBE' ? "U'" : null,
      symbolic_solution: missionType === 'SOLVE_CUBE' ? ["U'", "F'", 'R2', "B'", 'L'] : [],
      failure_reason: null,
    },
    plan: {
      plan_id: `plan-smp-${missionType}`,
      mission_id: `msn-smp-${missionType}`,
      mission_type: missionType,
      planner_name: 'DeterministicMissionPlanner (SYNTHETIC SAMPLE)',
      planner_mode: 'DETERMINISTIC_PLANNER',
      created_at: '03:18:07',
      updated_at: '03:19:08',
      current_step_id: steps[steps.length - 1].step_id,
      steps,
      rationale_summary: '离线合成样本包，仅作静态界面布局展示。',
      replan_count: 0,
    },
    decision_events: sampleDecisionEvents,
    agent_state: {
      planner_mode: 'DETERMINISTIC_PLANNER',
      planner_name: 'DeterministicMissionPlanner',
      llm_connected: false,
      llm_model: null,
      status_label: '当前由确定性任务规划器执行，LLM Agent 尚未接入（SYNTHETIC SAMPLE）',
      latest_observation: {
        observation_id: 'obs-sample',
        frame_id: 'frm-sample',
        sim_time: isTurnMission ? ev.sim_time : 34.25,
        camera_name: 'synthetic_canvas2d',
        observed_count: afterTurn ? 45 : 54,
        unknown_count: afterTurn ? 9 : 0,
        conflict_count: 0,
        validation_status: afterTurn ? 'INCOMPLETE' : 'VALID_SOLVABLE',
        summary: 'SYNTHETIC SAMPLE 合成样本观测',
      },
      selected_action: steps[steps.length - 1].skill_id,
      selection_rationale:
        missionType === 'SOLVE_CUBE'
          ? '能力核查发现求解序列含不支持的物理转层，禁止绕过能力边界执行。'
          : '按当前 Mission 目标执行对应步骤序列。',
      last_skill_call: steps[steps.length - 1].skill_id,
      last_execution_feedback: steps[steps.length - 1].result_summary || '',
      blocked_or_replan_reason:
        missionType === 'SOLVE_CUBE'
          ? "动作 U' / F' / R2 超出当前物理模型能力范围"
          : null,
    },
  };
}

function createDisconnectedLiveSnapshot(seed: number, missionType: MissionType): SimulationSnapshot {
  const faces: FaceletObservation[] = [];
  FACE_ORDER.forEach((face, fIdx) => {
    for (let localIdx = 0; localIdx < 9; localIdx++) {
      faces.push({
        index: fIdx * 9 + localIdx,
        face,
        localIdx,
        color: 'UNKNOWN',
        observationCount: 0,
        hasConflict: false,
      });
    }
  });
  return {
    session_id: 'UNCONNECTED',
    seed,
    sim_time: 0,
    wall_time: '--:--:--',
    frame_source: 'NONE',
    active_camera: missionType === 'RELAY_SOLVE_CUBE' ? 'cube_closeup' : 'overview',
    camera_azimuth_deg: missionType === 'RELAY_SOLVE_CUBE' ? 132 : 135,
    camera_elevation_deg: -28,
    camera_distance_m: missionType === 'RELAY_SOLVE_CUBE' ? 0.28 : 1.15,
    main_frame_url: null,
    wrist_rgb_url: null,
    wrist_depth_url: null,
    depth_range_m: [0.35, 2.25],
    detections: [],
    task_status: 'IDLE',
    current_stage_id: '',
    current_skill: 'IDLE',
    stages: [],
    observed_facelets: faces,
    predicted_facelets: Array(54).fill('UNKNOWN'),
    cube_validation_status: 'UNVERIFIED',
    telemetry: {
      contactForceN: null,
      gripperWidthMm: null,
      gripperState: 'UNKNOWN',
      jointPositionsRad: null,
      cubePositionMm: null,
      layerTurnAngleDeg: null,
      targetLayer: null,
      collisionDetected: null,
      slipDetected: null,
      renderFps: null,
      failureReason: null,
    },
    timeline: [],
    selected_mission_type: missionType,
    mission: null,
    plan: null,
    skill_executions: [],
    decision_events: [],
    capabilities: null,
    agent_state: {
      planner_mode: 'UNCONNECTED',
      planner_name: '未连接',
      llm_connected: false,
      llm_model: null,
      status_label: '未连接后端 · Agent 尚未接入',
    },
    physical_verification: null,
    last_observation_ref: null,
    running: false,
    relay_phase: 'IDLE',
    relay_state: null,
  };
}

// ============================================================================
// 4. 辅助状态徽章与格式化组件
// ============================================================================

function formatSimTime(sec: number): string {
  const mins = Math.floor(sec / 60);
  const rem = sec - mins * 60;
  return `${String(mins).padStart(2, '0')}:${rem.toFixed(2).padStart(5, '0')}`;
}

const StageStatusBadge: React.FC<{ status: StageStatus; implemented: boolean }> = ({ status, implemented }) => {
  if (!implemented || status === 'UNAVAILABLE') {
    return (
      <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-slate-800/80 text-slate-400 border border-slate-700/80">
        不可用
      </span>
    );
  }
  switch (status) {
    case 'VERIFIED':
      return (
        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-[#30D6A0]/15 text-[#30D6A0] border border-[#30D6A0]/40">
          <CheckCircle2 className="w-2.5 h-2.5" /> 已完成
        </span>
      );
    case 'RUNNING':
      return (
        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-[#548CFF]/20 text-[#548CFF] border border-[#548CFF]/50">
          <RefreshCw className="w-2.5 h-2.5 animate-spin" /> 执行中
        </span>
      );
    case 'BLOCKED':
      return (
        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-[#FFBF69]/15 text-[#FFBF69] border border-[#FFBF69]/40">
          <ShieldAlert className="w-2.5 h-2.5" /> 能力阻塞
        </span>
      );
    case 'FAILED':
      return (
        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-[#FF667B]/15 text-[#FF667B] border border-[#FF667B]/40">
          <XCircle className="w-2.5 h-2.5" /> 失败
        </span>
      );
    default:
      return (
        <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-[#182338] text-slate-400 border border-slate-700/60">
          等待中
        </span>
      );
  }
};

const MissionStatusBadge: React.FC<{ status?: MissionStatus | null }> = ({ status }) => {
  if (!status) {
    return (
      <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-[#182338] text-slate-400 border border-slate-700">
        IDLE
      </span>
    );
  }
  const styles: Record<MissionStatus, string> = {
    CREATED: 'bg-[#182338] text-slate-300 border-slate-700',
    OBSERVING: 'bg-[#3DE8E5]/15 text-[#3DE8E5] border-[#3DE8E5]/40',
    PLANNING: 'bg-[#548CFF]/20 text-[#548CFF] border-[#548CFF]/40',
    EXECUTING: 'bg-[#548CFF]/20 text-[#548CFF] border-[#548CFF]/50',
    VERIFYING: 'bg-[#3DE8E5]/15 text-[#3DE8E5] border-[#3DE8E5]/40',
    WAITING_FOR_HUMAN_TURN: 'bg-[#FFBF69]/20 text-[#FFBF69] border-[#FFBF69]/50',
    BLOCKED_CAPABILITY: 'bg-[#FFBF69]/20 text-[#FFBF69] border-[#FFBF69]/50',
    COMPLETED: 'bg-[#30D6A0]/15 text-[#30D6A0] border-[#30D6A0]/40',
    FAILED: 'bg-[#FF667B]/15 text-[#FF667B] border-[#FF667B]/40',
    CANCELLED: 'bg-slate-800 text-slate-300 border-slate-600',
  };
  return (
    <span className={`px-1.5 py-0.5 rounded text-[10px] font-mono border ${styles[status]}`}>
      {status}
    </span>
  );
};

// ============================================================================
// 5. 主仿真视口组件 (严格隔离 LIVE 真实 MuJoCo 帧与 SAMPLE 合成帧)
// ============================================================================

interface SimulationViewportProps {
  mode: RuntimeMode;
  wsConnected: boolean;
  wsUrl: string;
  snapshot: SimulationSnapshot;
  debugOverlays: {
    contactForces: boolean;
    collisionGeoms: boolean;
    tcpFrame: boolean;
    hudVisible: boolean;
  };
  onCameraPresetChange: (preset: CameraPresetId) => void;
  onCameraOrbitCommand: (deltaAzimuthDeg: number, deltaElevationDeg: number) => void;
  onCameraZoomCommand: (deltaDistanceM: number) => void;
  previewScreenshotUrl: string | null;
  onUploadPreviewScreenshot: (url: string) => void;
  replayVideoRef: React.RefObject<HTMLVideoElement>;
  replayVideoUrl: string | null;
  onReplayTimeUpdate: (videoTimeSec: number) => void;
  onLoadReplayFiles: (videoFile: File | null, timingFile: File | null) => void;
  onUrgentInterrupt?: () => void;
}

const SimulationViewport: React.FC<SimulationViewportProps> = ({
  mode,
  wsConnected,
  wsUrl,
  snapshot,
  debugOverlays,
  onCameraPresetChange,
  onCameraOrbitCommand,
  onCameraZoomCommand,
  previewScreenshotUrl,
  onUploadPreviewScreenshot,
  replayVideoRef,
  replayVideoUrl,
  onReplayTimeUpdate,
  onLoadReplayFiles,
  onUrgentInterrupt,
}) => {
  const dragStateRef = useRef<{ active: boolean; lastX: number; lastY: number }>({
    active: false,
    lastX: 0,
    lastY: 0,
  });
  const lastWheelRef = useRef<number>(0);

  const handlePointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (mode !== 'LIVE' || !wsConnected) return;
    // Keep toolbar controls clickable. Capturing a pointer that originated on a
    // button retargets the following pointerup to this viewport and cancels the
    // browser's click event.
    const target = e.target as HTMLElement;
    if (target.closest('button, input, select, textarea, a, [role="button"]')) return;
    dragStateRef.current = { active: true, lastX: e.clientX, lastY: e.clientY };
    e.currentTarget.setPointerCapture(e.pointerId);
  };

  const handlePointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!dragStateRef.current.active || mode !== 'LIVE' || !wsConnected) return;
    const dx = e.clientX - dragStateRef.current.lastX;
    const dy = e.clientY - dragStateRef.current.lastY;
    dragStateRef.current.lastX = e.clientX;
    dragStateRef.current.lastY = e.clientY;
    if (Math.abs(dx) > 1 || Math.abs(dy) > 1) {
      onCameraOrbitCommand(-dx * 0.35, dy * 0.25);
    }
  };

  const handlePointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    if (dragStateRef.current.active) {
      dragStateRef.current.active = false;
      e.currentTarget.releasePointerCapture(e.pointerId);
    }
  };

  const handleWheel = (e: React.WheelEvent<HTMLDivElement>) => {
    if (mode !== 'LIVE' || !wsConnected) return;
    e.preventDefault();
    const now = performance.now();
    if (now - lastWheelRef.current < 45) return;
    lastWheelRef.current = now;
    onCameraZoomCommand(e.deltaY > 0 ? 0.04 : -0.04);
  };

  const azRad = (snapshot.camera_azimuth_deg * Math.PI) / 180;
  const elRad = (snapshot.camera_elevation_deg * Math.PI) / 180;
  const axisX = { x: Math.cos(azRad) * 18, y: Math.sin(azRad) * Math.sin(elRad) * 18 };
  const axisY = { x: -Math.sin(azRad) * 18, y: Math.cos(azRad) * Math.sin(elRad) * 18 };
  const axisZ = { x: 0, y: -Math.cos(elRad) * 18 };

  const activeStep = snapshot.plan?.steps.find((s) => s.step_id === snapshot.plan?.current_step_id);

  return (
    <div
      className="relative w-full h-full bg-[#080D16] border border-slate-800/90 rounded-lg overflow-hidden select-none flex flex-col"
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onWheel={handleWheel}
    >
      {/* 视口顶部工具条 */}
      <div className="z-20 flex items-center justify-between gap-2 px-3 py-1.5 bg-[#101827]/95 border-b border-slate-800/90 shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <Monitor className="w-3.5 h-3.5 text-[#3DE8E5] shrink-0" />
          <span className="text-[11px] font-semibold tracking-wider text-slate-200 uppercase truncate">
            实时仿真视口 · MuJoCo Renderer
          </span>
          {mode === 'SAMPLE' && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono bg-[#FFBF69]/15 text-[#FFBF69] border border-[#FFBF69]/40 shrink-0">
              SYNTHETIC SAMPLE · Canvas 2D 样本 (Seed=0)
            </span>
          )}
          {mode === 'LIVE' && (
            <span
              className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono shrink-0 ${
                wsConnected
                  ? 'bg-[#30D6A0]/15 text-[#30D6A0] border border-[#30D6A0]/40'
                  : 'bg-[#FF667B]/15 text-[#FF667B] border border-[#FF667B]/40'
              }`}
            >
              {wsConnected ? 'LIVE · REAL MUJOCO RENDERER' : 'LIVE · 未连接后端'}
            </span>
          )}
          {mode === 'REPLAY' && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono bg-[#548CFF]/15 text-[#548CFF] border border-[#548CFF]/40 shrink-0">
              PREVIEW / REPLAY · 外部录制与截图模式
            </span>
          )}
        </div>

        <div className="flex items-center gap-1 bg-[#080D16] p-0.5 rounded border border-slate-800 shrink-0">
          {CAMERA_PRESETS.map((cam) => {
            const active = snapshot.active_camera === cam.id;
            return (
              <button
                key={cam.id}
                type="button"
                title={cam.desc}
                onClick={() => onCameraPresetChange(cam.id)}
                className={`px-2 py-0.5 rounded text-[11px] font-medium transition-colors ${
                  active
                    ? 'bg-[#548CFF] text-white'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-[#182338]'
                }`}
              >
                {cam.label}
              </button>
            );
          })}
          {mode === 'LIVE' && (
            <>
              <button
                type="button"
                title="拉近镜头放大魔方"
                onClick={() => onCameraZoomCommand(-0.05)}
                className="px-1.5 py-0.5 rounded text-[11px] font-mono text-[#3DE8E5] hover:bg-[#182338]"
              >
                +放大
              </button>
              <button
                type="button"
                title="拉远镜头"
                onClick={() => onCameraZoomCommand(0.05)}
                className="px-1.5 py-0.5 rounded text-[11px] font-mono text-slate-300 hover:bg-[#182338]"
              >
                -缩小
              </button>
            </>
          )}
        </div>
      </div>

      {/* M5 Agent Relay 模块 1 & 模块 6: 清晰回合归属指示灯 + 6阶段回合步进条 + 实时进度 */}
      {(snapshot.selected_mission_type === 'RELAY_SOLVE_CUBE' || snapshot.relay_state?.enabled) && (() => {
        const relay = snapshot.relay_state;
        const tone = relay?.banner?.tone || 'slate';
        const toneClass =
          tone === 'amber'
            ? 'bg-[#FFBF69]/15 border-[#FFBF69]/50 text-[#FFBF69]'
            : tone === 'violet'
            ? 'bg-[#8B5CF6]/15 border-[#8B5CF6]/50 text-[#A78BFA]'
            : tone === 'emerald'
            ? 'bg-[#30D6A0]/15 border-[#30D6A0]/50 text-[#30D6A0]'
            : tone === 'red'
            ? 'bg-[#FF667B]/15 border-[#FF667B]/50 text-[#FF667B]'
            : tone === 'blue'
            ? 'bg-[#548CFF]/15 border-[#548CFF]/50 text-[#3DE8E5]'
            : 'bg-[#182338] border-slate-700 text-slate-300';
        const prog = relay?.progress;
        const pct = prog ? Math.max(0, Math.min(100, prog.completion_pct)) : 0;
        const stats = relay?.cognitive_stats;
        const turnInfo = relay?.turn_indicator;
        const owner = turnInfo?.owner || (
          relay?.phase === 'WAITING_FOR_HUMAN_TURN'
            ? 'HUMAN'
            : relay?.phase === 'AWAITING_HUMAN_CLARIFICATION'
            ? 'CLARIFY'
            : relay?.phase === 'RELAY_COMPLETED_VERIFIED'
            ? 'DONE'
            : relay?.phase === 'ROBOT_ACTING' || relay?.phase === 'AGENT_REASONING' || relay?.phase === 'ROBOT_PERCEIVING' || relay?.phase === 'VERIFYING_SOLVED'
            ? 'ROBOT'
            : 'IDLE'
        );
        const ownerPillCls =
          owner === 'HUMAN'
            ? 'bg-[#FFBF69]/20 text-[#FFBF69] border-[#FFBF69] animate-pulse'
            : owner === 'CLARIFY'
            ? 'bg-[#8B5CF6]/20 text-[#A78BFA] border-[#8B5CF6]/50 animate-pulse'
            : owner === 'ROBOT'
            ? 'bg-[#3DE8E5]/15 text-[#3DE8E5] border-[#3DE8E5]/50 animate-pulse'
            : owner === 'DONE'
            ? 'bg-[#30D6A0]/20 text-[#30D6A0] border-[#30D6A0]/50'
            : 'bg-[#182338] text-slate-300 border-slate-700';
        const ownerText =
          turnInfo?.owner_label_zh ||
          (owner === 'HUMAN'
            ? '🧑 当前回合：人类操作中'
            : owner === 'CLARIFY'
            ? '🟣 当前回合：待你确认'
            : owner === 'ROBOT'
            ? '🤖 当前回合：机器人执行中'
            : owner === 'DONE'
            ? '🎉 100% 复原已完成'
            : '⏸️ 待启动');
        const stageLabels = turnInfo?.stage_labels || ['开局扫面', '机器人操作', '交接/澄清', '人类回合', '快瞄/修复', '复原核验'];
        const stageIdx = typeof turnInfo?.stage_index === 'number'
          ? turnInfo.stage_index
          : owner === 'HUMAN'
          ? 3
          : owner === 'CLARIFY'
          ? 2
          : owner === 'DONE'
          ? 5
          : relay?.phase === 'ROBOT_PERCEIVING'
          ? 0
          : owner === 'ROBOT'
          ? 1
          : 0;

        return (
          <div className="z-20 px-3 py-1.5 bg-[#0C1422] border-b border-slate-800/90 space-y-1.5 shrink-0">
            <div className={`px-2.5 py-1.5 rounded border flex items-center justify-between gap-2 ${toneClass}`}>
              <div className="min-w-0 flex items-center gap-2">
                <span className={`px-2 py-0.5 rounded border text-[10.5px] font-bold shrink-0 ${ownerPillCls}`}>
                  {ownerText}
                </span>
                <div className="min-w-0">
                  <div className="text-[11px] font-semibold truncate">
                    {relay?.banner?.title_zh || '🧑/🤖 Agent 人机接力待命'}
                  </div>
                  <div className="text-[9.5px] opacity-85 truncate">
                    {turnInfo?.next_action_hint_zh || relay?.banner?.subtitle_zh || '选择打乱步数并启动，实时观看魔方 26 块协同复原。'}
                  </div>
                </div>
              </div>
              {snapshot.running && (relay?.phase === 'ROBOT_ACTING' || relay?.phase === 'AGENT_REASONING') && onUrgentInterrupt && (
                <button
                  type="button"
                  onClick={onUrgentInterrupt}
                  className="px-2 py-1 rounded text-[10px] font-semibold bg-[#FF667B]/20 hover:bg-[#FF667B]/30 text-[#FF667B] border border-[#FF667B]/50 shrink-0 transition-colors"
                >
                  ⚡ 紧急刹车/中断
                </button>
              )}
            </div>

            <div className="grid grid-cols-6 gap-1 text-[9.5px] font-mono">
              {stageLabels.map((stLabel, idx) => {
                const isDoneStage = owner === 'DONE' ? true : idx < stageIdx;
                const isCurStage = owner !== 'DONE' && idx === stageIdx;
                const stageCls = isCurStage
                  ? 'bg-[#3DE8E5]/15 text-[#3DE8E5] border-[#3DE8E5]/60 font-semibold'
                  : isDoneStage
                  ? 'bg-[#30D6A0]/10 text-[#30D6A0] border-[#30D6A0]/30'
                  : 'bg-[#080D16] text-slate-500 border-slate-800';
                return (
                  <div key={stLabel} className={`px-1.5 py-0.5 rounded border text-center truncate ${stageCls}`}>
                    {isDoneStage ? '✓ ' : isCurStage ? '● ' : `${idx + 1}. `}
                    {stLabel}
                  </div>
                );
              })}
            </div>

            {relay && (
              <div className="space-y-1">
                <div className="flex items-center justify-between gap-2 text-[10px] font-mono text-slate-300">
                  <div className="flex items-center gap-2 min-w-0 truncate">
                    <span>
                      剩余: <strong className="text-[#3DE8E5]">{prog?.initial_optimal_steps ?? '--'}</strong> →{' '}
                      <strong className="text-[#30D6A0]">{prog?.remaining_optimal_steps ?? '--'}</strong> 步 (
                      {pct.toFixed(0)}%)
                    </span>
                    <span className="text-slate-500">·</span>
                    <span>第 {relay.round_number || 1} 轮</span>
                    <span className="text-slate-500">·</span>
                    <span>🤖{prog?.robot_moves_count ?? 0}步 / 🧑{prog?.human_turns_count ?? 0}轮</span>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0 text-[9.5px]">
                    <span className="px-1.5 py-0.5 rounded bg-[#182338] border border-slate-700 text-[#3DE8E5]">
                      快瞄免翻:{stats?.rapid_glance_deduction_successes ?? 0}
                    </span>
                    <span className="px-1.5 py-0.5 rounded bg-[#182338] border border-slate-700 text-[#FFBF69]">
                      省翻面:{stats?.saved_high_cost_flips ?? 0}
                    </span>
                    <span className="px-1.5 py-0.5 rounded bg-[#182338] border border-slate-700 text-slate-300">
                      抢占:{stats?.fast_loop_contract_interceptions ?? 0}
                    </span>
                  </div>
                </div>
                <div className="w-full h-1.5 bg-[#182338] rounded-full overflow-hidden border border-slate-800">
                  <div
                    className="h-full bg-[#30D6A0] transition-all"
                    style={{ width: `${pct}%` }}
                  />
                </div>
                {prog?.round_tags && prog.round_tags.length > 0 && (
                  <div className="flex items-center gap-1 overflow-x-auto text-[9.5px] font-mono">
                    {prog.round_tags.map((tag, i) => {
                      const isLatest = i === prog.round_tags.length - 1;
                      const tagCls = isLatest
                        ? 'bg-[#3DE8E5]/15 border-[#3DE8E5]/50 text-[#3DE8E5] font-semibold'
                        : 'bg-[#182338] border-slate-700 text-slate-400';
                      return (
                        <span
                          key={`${tag}-${i}`}
                          className={`px-1.5 py-0.5 rounded border shrink-0 ${tagCls}`}
                        >
                          {tag}
                        </span>
                      );
                    })}
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })()}

      {/* 核心画面区域 */}
      <div className="relative flex-1 flex items-center justify-center bg-[#080D16] overflow-hidden">
        {mode === 'SAMPLE' && snapshot.main_frame_url && (
          <img
            src={snapshot.main_frame_url}
            alt="SYNTHETIC SAMPLE Frame"
            className="w-full h-full object-contain"
            draggable={false}
          />
        )}

        {mode === 'LIVE' && (
          <>
            {wsConnected && snapshot.main_frame_url ? (
              <img
                src={snapshot.main_frame_url}
                alt="Real MuJoCo Offscreen Render Frame"
                className="w-full h-full object-contain"
                draggable={false}
              />
            ) : (
              <div className="z-10 max-w-md mx-auto p-5 rounded-lg bg-[#101827]/95 border border-slate-800 text-center space-y-2.5">
                <div className="w-10 h-10 mx-auto rounded-full bg-[#182338] border border-slate-700 flex items-center justify-center text-[#FFBF69]">
                  <WifiOff className="w-5 h-5" />
                </div>
                <div className="text-xs font-semibold text-slate-100">
                  {wsConnected ? '已连接 SimulationSession，等待真实 MuJoCo 首帧...' : '未连接到 Python MuJoCo 仿真后端'}
                </div>
                <p className="text-[11px] text-slate-400 leading-relaxed">
                  LIVE 模式严格接收后端 <code className="text-[#3DE8E5] font-mono">mujoco.Renderer</code> 帧流，绝不使用 Canvas 2D 合成图。
                </p>
                <div className="p-2 rounded bg-[#080D16] border border-slate-800 font-mono text-[10px] text-slate-300 text-left">
                  <div>端点: <span className="text-[#3DE8E5]">{wsUrl}</span></div>
                  <div className="text-slate-500 mt-0.5">启动: python -m cube_relay.server --seed 0 --port 8765</div>
                </div>
              </div>
            )}
          </>
        )}

        {mode === 'REPLAY' && (
          <>
            {replayVideoUrl ? (
              <video
                ref={replayVideoRef}
                src={replayVideoUrl}
                className="w-full h-full object-contain bg-black"
                controls
                onTimeUpdate={(e) => onReplayTimeUpdate(e.currentTarget.currentTime)}
              />
            ) : previewScreenshotUrl ? (
              <img
                src={previewScreenshotUrl}
                alt="Historical MuJoCo Run Screenshot"
                className="w-full h-full object-contain"
              />
            ) : (
              <div className="z-10 max-w-md mx-auto p-5 rounded-lg bg-[#101827]/95 border border-slate-800 text-center space-y-2.5">
                <div className="w-10 h-10 mx-auto rounded-full bg-[#182338] border border-slate-700 flex items-center justify-center text-[#548CFF]">
                  <Film className="w-5 h-5" />
                </div>
                <div className="text-xs font-semibold text-slate-100">离线界面预览 / 导入本地历史运行文件</div>
                <p className="text-[11px] text-slate-400 leading-relaxed">
                  支持导入真实 <code className="text-slate-300 font-mono">episode.mp4</code> +{' '}
                  <code className="text-slate-300 font-mono">episode.timing.json</code> 或历史运行截图。
                </p>
                <div className="flex items-center justify-center gap-2 pt-1">
                  <label className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded bg-[#548CFF] hover:bg-[#4379eb] text-white text-xs font-medium cursor-pointer transition-colors">
                    <FolderOpen className="w-3.5 h-3.5" />
                    导入录像与时间轴
                    <input
                      type="file"
                      accept="video/mp4,application/json"
                      multiple
                      className="hidden"
                      onChange={(e) => {
                        const files = Array.from(e.target.files || []);
                        const vFile = files.find((f) => f.name.endsWith('.mp4')) || null;
                        const tFile = files.find((f) => f.name.endsWith('.json')) || null;
                        onLoadReplayFiles(vFile, tFile);
                      }}
                    />
                  </label>
                  <label className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded bg-[#182338] hover:bg-slate-700 text-slate-200 border border-slate-700 text-xs font-medium cursor-pointer transition-colors">
                    <Upload className="w-3.5 h-3.5 text-[#3DE8E5]" />
                    载入历史截图
                    <input
                      type="file"
                      accept="image/png,image/jpeg,image/webp"
                      className="hidden"
                      onChange={(e) => {
                        const f = e.target.files?.[0];
                        if (f) onUploadPreviewScreenshot(URL.createObjectURL(f));
                      }}
                    />
                  </label>
                </div>
              </div>
            )}
          </>
        )}

        {debugOverlays.hudVisible && (
          <>
            <div className="pointer-events-none absolute top-2.5 left-2.5 z-10 flex flex-col gap-1 bg-[#080D16]/85 backdrop-blur-xs border border-slate-800/90 rounded px-2.5 py-1.5 text-[11px]">
              <div className="flex items-center gap-2">
                <span className="text-slate-400">当前 Mission:</span>
                <span className="font-mono font-semibold text-slate-100">
                  {snapshot.mission?.mission_type || snapshot.selected_mission_type || 'INSPECT_CUBE'}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-slate-400">当前步骤:</span>
                <span className="font-medium text-slate-100">
                  {activeStep?.title || snapshot.stages.find((s) => s.id === snapshot.current_stage_id)?.title || '就绪'}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-slate-400">执行 Skill:</span>
                <span className="font-mono text-[#3DE8E5]">{snapshot.current_skill}</span>
              </div>
              <div className="flex items-center gap-2.5 font-mono text-[10px] text-slate-300 pt-0.5 border-t border-slate-800">
                <span>SIM: {formatSimTime(snapshot.sim_time)}s</span>
                <span>SEED: {snapshot.seed}</span>
                <span>SRC: {snapshot.frame_source || 'NONE'}</span>
              </div>
            </div>

            <div className="pointer-events-none absolute bottom-2.5 left-2.5 z-10 flex items-center gap-2 bg-[#080D16]/85 border border-slate-800/90 rounded px-2 py-1">
              <svg width="42" height="42" viewBox="-22 -22 44 44" className="overflow-visible">
                <line x1="0" y1="0" x2={axisX.x} y2={axisX.y} stroke="#FF667B" strokeWidth="1.8" />
                <text x={axisX.x * 1.25} y={axisX.y * 1.25} fill="#FF667B" fontSize="8" fontFamily="monospace" textAnchor="middle">
                  X
                </text>
                <line x1="0" y1="0" x2={axisY.x} y2={axisY.y} stroke="#30D6A0" strokeWidth="1.8" />
                <text x={axisY.x * 1.25} y={axisY.y * 1.25} fill="#30D6A0" fontSize="8" fontFamily="monospace" textAnchor="middle">
                  Y
                </text>
                <line x1="0" y1="0" x2={axisZ.x} y2={axisZ.y} stroke="#548CFF" strokeWidth="1.8" />
                <text x={axisZ.x * 1.25} y={axisZ.y * 1.25} fill="#548CFF" fontSize="8" fontFamily="monospace" textAnchor="middle">
                  Z
                </text>
              </svg>
              <div className="text-[10px] font-mono text-slate-400 leading-tight">
                <div>AZ: {snapshot.camera_azimuth_deg.toFixed(0)}°</div>
                <div>EL: {snapshot.camera_elevation_deg.toFixed(0)}°</div>
                <div>D: {snapshot.camera_distance_m.toFixed(2)}m</div>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
};

// ============================================================================
// 6. 右侧 25% 面板: Mission 选择器 + [Agent / 决策] & [Skill / 执行] 双标签页
// ============================================================================

interface RightOrchestrationPanelProps {
  mode: RuntimeMode;
  snapshot: SimulationSnapshot;
  selectedMission: MissionType;
  selectedScrambleSteps: number | 'random';
  onSelectMission: (missionType: MissionType) => void;
  onSelectScrambleSteps: (steps: number | 'random') => void;
  onRelayCommand: (cmd: Record<string, unknown>, label: string) => void;
}

const RELAY_FACE_GROUPS: Array<{ face: FaceId; moves: [string, string, string] }> = [
  { face: 'U', moves: ['U', "U'", 'U2'] },
  { face: 'D', moves: ['D', "D'", 'D2'] },
  { face: 'F', moves: ['F', "F'", 'F2'] },
  { face: 'B', moves: ['B', "B'", 'B2'] },
  { face: 'L', moves: ['L', "L'", 'L2'] },
  { face: 'R', moves: ['R', "R'", 'R2'] },
];

const QUICK_HRI_CHIPS = [
  { label: '交给你复原', text: '我不玩了，剩下的全部交给你复原！' },
  { label: '拒拧底面D', text: '底面D我不方便拧，底面由你翻面拧掉，给我留顶面或侧面' },
  { label: '手滑撤回', text: '刚才手滑拧错了，帮我撤回上一步' },
  { label: '顺路线解', text: '我是故意换路线的，请保留我的动作顺着继续往下解' },
  { label: '紧急放回', text: '停一下！先别解了，把魔方安全放回桌面交给我' },
];

const RightOrchestrationPanel: React.FC<RightOrchestrationPanelProps> = ({
  mode,
  snapshot,
  selectedMission,
  selectedScrambleSteps,
  onSelectMission,
  onSelectScrambleSteps,
  onRelayCommand,
}) => {
  const [rightTab, setRightTab] = useState<'AGENT' | 'SKILL'>('AGENT');
  const [showLegacyMissions, setShowLegacyMissions] = useState<boolean>(false);
  const [agentDrawerOpen, setAgentDrawerOpen] = useState<boolean>(false);
  const [skillDrawerOpen, setSkillDrawerOpen] = useState<boolean>(false);
  const [expandedSkills, setExpandedSkills] = useState<Set<string>>(new Set());
  const [expandedTraceEvents, setExpandedTraceEvents] = useState<Set<string>>(new Set());
  const [selectedDecisionObservationId, setSelectedDecisionObservationId] = useState<string | null>(null);
  const [chatDraft, setChatDraft] = useState<string>('');
  const [perturbDxCm, setPerturbDxCm] = useState<number>(0);
  const [perturbDyCm, setPerturbDyCm] = useState<number>(0);
  const [perturbYawDeg, setPerturbYawDeg] = useState<number>(0);

  useEffect(() => {
    if (snapshot.relay_state?.perturbation) {
      setPerturbDxCm(Math.round((snapshot.relay_state.perturbation.dx_m || 0) * 100));
      setPerturbDyCm(Math.round((snapshot.relay_state.perturbation.dy_m || 0) * 100));
      setPerturbYawDeg(Math.round(snapshot.relay_state.perturbation.dyaw_deg || 0));
    }
  }, [snapshot.relay_state?.phase, snapshot.relay_state?.perturbation?.dx_m, snapshot.relay_state?.perturbation?.dy_m, snapshot.relay_state?.perturbation?.dyaw_deg]);

  const mission = snapshot.mission;
  const plan = snapshot.plan;
  const agent = snapshot.agent_state;
  const decisionEvents = snapshot.decision_events || [];
  const executions = snapshot.skill_executions || [];
  const traceEvents = snapshot.trace_events || [];
  const policyTraceEvents = traceEvents.filter((event) => event.event_type === 'decision');
  const vlmCompositeTrace = traceEvents.find(
    (event) => event.event_type === 'composite_skill' && event.skill_id === 'vlm_controlled_inspection'
  );
  const vlmCompositeChildren = vlmCompositeTrace
    ? traceEvents.filter((event) => event.parent_event_id === vlmCompositeTrace.event_id)
    : [];
  const missionSpec = MISSION_OPTIONS.find((m) => m.type === selectedMission)!;
  const selectedDecisionObservation = (snapshot.observations || []).find(
    (observation) => observation.observation_id === selectedDecisionObservationId
  );

  const completedSteps = plan ? plan.steps.filter((s) => s.status === 'VERIFIED').length : 0;
  const totalSteps = plan ? plan.steps.length : 0;
  const isVlmPlanner = agent?.planner_mode === 'LLM_AGENT';
  const plannerBannerStyle = agent?.llm_connected
    ? 'bg-[#30D6A0]/10 border-[#30D6A0]/40 text-[#30D6A0]'
    : isVlmPlanner
    ? 'bg-[#FFBF69]/10 border-[#FFBF69]/40 text-[#FFBF69]'
    : agent?.planner_mode === 'DETERMINISTIC_PLANNER'
    ? 'bg-[#548CFF]/15 border-[#548CFF]/40 text-slate-200'
    : 'bg-[#182338] border-slate-700 text-slate-300';
  const safetyGateStyle =
    agent?.safety_gate_status && agent.safety_gate_status.startsWith('PASSED')
      ? 'text-[#30D6A0]'
      : agent?.safety_gate_status && agent.safety_gate_status.includes('BLOCKED')
      ? 'text-[#FFBF69]'
      : agent?.safety_gate_status
      ? 'text-[#FF667B]'
      : 'text-slate-400';

  const isRelayMission = selectedMission === 'RELAY_SOLVE_CUBE';
  const showAgentPanel = isRelayMission ? agentDrawerOpen : rightTab === 'AGENT';
  const showSkillPanel = isRelayMission ? skillDrawerOpen : rightTab === 'SKILL';

  return (
    <div className="min-w-0 min-h-0 h-full bg-[#101827] border border-slate-800/90 rounded-lg p-2.5 flex flex-col gap-2">
      {/* 顶部标题与精简任务栏（默认聚焦人机接力，历史实验可折叠切换） */}
      <div className="space-y-1.5 border-b border-slate-800/90 pb-2 shrink-0">
        <div className="flex items-center justify-between gap-1.5">
          <div className="flex items-center gap-1.5 min-w-0">
            <GitBranch className="w-3.5 h-3.5 text-[#3DE8E5] shrink-0" />
            <span className="text-[11px] font-semibold tracking-wider text-slate-200 uppercase truncate">
              {isRelayMission ? '🧑/🤖 人机接力主控台' : `实验模式 · ${missionSpec.label}`}
            </span>
          </div>
          <div className="flex items-center gap-1.5 shrink-0">
            <button
              type="button"
              onClick={() => setShowLegacyMissions((v) => !v)}
              title="展开/收起历史单阶段实验（六面扫描 / U层物理转动 / 魔方完整求解）"
              className="px-1.5 py-0.5 rounded text-[9.5px] bg-[#080D16] hover:bg-[#182338] text-slate-400 hover:text-slate-200 border border-slate-800 transition-colors"
            >
              {showLegacyMissions ? '收起历史实验 ▴' : '历史实验 ▾'}
            </button>
            <MissionStatusBadge status={mission?.status} />
          </div>
        </div>

        {(showLegacyMissions || !isRelayMission) && (
          <div className="grid grid-cols-2 gap-1 bg-[#080D16] p-0.5 rounded border border-slate-800">
            {MISSION_OPTIONS.map((opt) => {
              const active = selectedMission === opt.type;
              return (
                <button
                  key={opt.type}
                  type="button"
                  title={opt.shortDesc}
                  onClick={() => onSelectMission(opt.type)}
                  className={`px-1.5 py-1 rounded text-[10.5px] font-medium truncate transition-colors ${
                    active
                      ? 'bg-[#548CFF] text-white'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-[#182338]'
                  }`}
                >
                  {opt.label}
                </button>
              );
            })}
          </div>
        )}

        {isRelayMission && (
          <div className="flex items-center justify-between gap-1 bg-[#080D16] border border-slate-800 rounded px-2 py-1 text-[10px]">
            <span className="text-slate-400 shrink-0">打乱步数:</span>
            <div className="flex items-center gap-1">
              {([4, 5, 6, 8, 'random'] as Array<number | 'random'>).map((opt) => {
                const active = selectedScrambleSteps === opt;
                return (
                  <button
                    key={String(opt)}
                    type="button"
                    onClick={() => onSelectScrambleSteps(opt)}
                    className={`px-1.5 py-0.5 rounded font-mono transition-colors ${
                      active
                        ? 'bg-[#3DE8E5]/20 text-[#3DE8E5] border border-[#3DE8E5]/40'
                        : 'text-slate-400 hover:text-slate-200 bg-[#182338]'
                    }`}
                  >
                    {opt === 'random' ? '随机' : `${opt}步`}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {!isRelayMission && (
          <div className="text-[10px] text-slate-400 bg-[#080D16] border border-slate-800/80 rounded px-2 py-1 leading-snug">
            {missionSpec.capabilityNote}
          </div>
        )}
      </div>

      {/* 非人机接力历史任务时保留双标签页切换 */}
      {!isRelayMission && (
        <div className="grid grid-cols-2 gap-1 bg-[#080D16] p-0.5 rounded border border-slate-800 shrink-0">
          <button
            type="button"
            onClick={() => setRightTab('AGENT')}
            className={`flex items-center justify-center gap-1 py-1 rounded text-[10.5px] font-semibold transition-colors ${
              rightTab === 'AGENT'
                ? 'bg-[#182338] text-[#3DE8E5] border border-[#3DE8E5]/40'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Bot className="w-3 h-3" /> Agent / 决策
          </button>
          <button
            type="button"
            onClick={() => setRightTab('SKILL')}
            className={`flex items-center justify-center gap-1 py-1 rounded text-[10.5px] font-semibold transition-colors ${
              rightTab === 'SKILL'
                ? 'bg-[#182338] text-[#3DE8E5] border border-[#3DE8E5]/40'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Layers className="w-3 h-3" /> Skill / 执行 ({completedSteps}/{totalSteps})
          </button>
        </div>
      )}

      {/* 折叠抽屉栏（人机接力模式下默认折叠在底部） */}
      {isRelayMission && (
        <div className="order-2 shrink-0 grid grid-cols-2 gap-1.5 border-t border-slate-800/90 pt-1.5">
          <button
            type="button"
            onClick={() => setAgentDrawerOpen((v) => !v)}
            className={`flex items-center justify-between gap-1 px-2 py-1 rounded text-[10px] font-semibold border transition-colors ${
              agentDrawerOpen
                ? 'bg-[#182338] text-[#3DE8E5] border-[#3DE8E5]/40'
                : 'bg-[#080D16] text-slate-400 border-slate-800 hover:text-slate-200'
            }`}
          >
            <span className="flex items-center gap-1 truncate">
              <Bot className="w-3 h-3 shrink-0" /> Agent / 决策
            </span>
            <span>{agentDrawerOpen ? '收起 ▾' : '展开 ▸'}</span>
          </button>
          <button
            type="button"
            onClick={() => setSkillDrawerOpen((v) => !v)}
            className={`flex items-center justify-between gap-1 px-2 py-1 rounded text-[10px] font-semibold border transition-colors ${
              skillDrawerOpen
                ? 'bg-[#182338] text-[#3DE8E5] border-[#3DE8E5]/40'
                : 'bg-[#080D16] text-slate-400 border-slate-800 hover:text-slate-200'
            }`}
          >
            <span className="flex items-center gap-1 truncate">
              <Layers className="w-3 h-3 shrink-0" /> Skill / 执行 ({completedSteps}/{totalSteps})
            </span>
            <span>{skillDrawerOpen ? '收起 ▾' : '展开 ▸'}</span>
          </button>
        </div>
      )}

      {/* Agent / 决策可观测性（接力模式下点击折叠开关展开） */}
      {showAgentPanel && (
        <div className={isRelayMission ? 'order-3 max-h-56 shrink-0 overflow-y-auto space-y-2 pr-0.5 text-[11px] border border-slate-800/80 rounded p-1.5 bg-[#0A101B]' : 'flex-1 min-h-0 overflow-y-auto space-y-2 pr-0.5 text-[11px]'}>
          {/* 明确区分规划器 / LLM 状态（只有真实在线调用成功后才显示已连接） */}
          <div className={`px-2 py-1.5 rounded border text-[10.5px] font-medium space-y-1 ${plannerBannerStyle}`}>
            <div className="flex items-center gap-1.5">
              <Bot className="w-3.5 h-3.5 shrink-0 text-[#3DE8E5]" />
              <span className="leading-snug">
                {agent?.llm_connected
                  ? `LLM Agent 已连接 (${agent.llm_model || 'Gemini'})`
                  : isVlmPlanner
                  ? agent?.status_label || `Gemini VLM 未完成在线验证 (${agent?.llm_model || 'unconfigured'})`
                  : agent?.planner_mode === 'DETERMINISTIC_PLANNER'
                  ? agent.status_label || '当前由确定性任务规划器执行，LLM Agent 尚未接入'
                  : 'Agent 尚未接入'}
              </span>
            </div>
            <div className="text-[9.5px] font-mono text-slate-300 flex items-center justify-between gap-1">
              <span>{agent?.planner_name || '--'}</span>
              <span>
                {agent?.total_vlm_calls ? `VLM:${agent.total_vlm_calls}次` : ''}
                {typeof agent?.model_latency_ms === 'number' ? ` · ${agent.model_latency_ms.toFixed(0)}ms` : ''}
              </span>
            </div>
            {agent?.fallback_triggered && (
              <div className="text-[9.5px] text-[#FFBF69] font-mono">
                [FALLBACK] 已回退确定性规划 ({agent.fallback_reason || 'VLM_ERROR'})
              </div>
            )}
          </div>

          {isVlmPlanner && (
            <div className="grid grid-cols-2 gap-1.5">
              <div className="rounded border border-[#3DE8E5]/30 bg-[#3DE8E5]/5 p-1.5 space-y-0.5">
                <div className="text-[9px] font-mono text-[#3DE8E5]">MODEL A · VLM PERCEPTION</div>
                <div className="text-[10px] text-slate-200 truncate">{agent?.perception_model_name || '未配置'}</div>
                <div className="text-[9px] text-slate-500">
                  {agent?.perception_connected ? '已验证' : '未验证'}
                  {typeof agent?.perception_latency_ms === 'number' ? ` · ${agent.perception_latency_ms.toFixed(0)}ms` : ''}
                </div>
              </div>
              <div className="rounded border border-[#548CFF]/30 bg-[#548CFF]/5 p-1.5 space-y-0.5">
                <div className="text-[9px] font-mono text-[#548CFF]">MODEL B · AGENT PLANNER</div>
                <div className="text-[10px] text-slate-200 truncate">{agent?.agent_model_name || '未配置'}</div>
                <div className="text-[9px] text-slate-500">
                  {agent?.agent_connected ? '已验证' : '未验证'}
                  {typeof agent?.agent_latency_ms === 'number' ? ` · ${agent.agent_latency_ms.toFixed(0)}ms` : ''}
                </div>
              </div>
            </div>
          )}

          {agent?.latest_semantic_observation && (
            <div className="rounded border border-slate-800 bg-[#080D16] p-2 space-y-1">
              <div className="text-[9.5px] font-mono text-[#3DE8E5]">
                SEMANTIC OBS · {agent.latest_semantic_observation.observation_id} · {agent.latest_semantic_observation.frame_id}
              </div>
              <div className="text-[10.5px] text-slate-200">{agent.latest_semantic_observation.summary}</div>
              <div className="text-[10px] text-slate-400">
                关系：{agent.latest_semantic_observation.cube_relation_to_gripper} · {agent.latest_semantic_observation.support_relation}
              </div>
              {agent.latest_semantic_observation.information_gaps.length > 0 && (
                <div className="text-[10px] text-[#FFBF69]">
                  信息缺口：{agent.latest_semantic_observation.information_gaps.join('；')}
                </div>
              )}
              {agent.latest_semantic_observation.visual_conflicts.length > 0 && (
                <div className="text-[10px] text-[#FF667B]">
                  感知冲突：{agent.latest_semantic_observation.visual_conflicts.join('；')}
                </div>
              )}
            </div>
          )}

          {/* 能力阻塞或失败显式警告框 */}
          {(mission?.status === 'BLOCKED_CAPABILITY' || mission?.blocked_reason || agent?.blocked_or_replan_reason) && (
            <div className="p-2 rounded bg-[#FFBF69]/10 border border-[#FFBF69]/50 space-y-1">
              <div className="flex items-center gap-1.5 text-[#FFBF69] font-semibold text-[11px]">
                <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
                <span>能力阻塞 · {mission?.blocked_move ? `受阻动作 ${mission.blocked_move}` : 'CAPABILITY_BLOCKED'}</span>
              </div>
              <div className="text-[10.5px] text-slate-200 leading-snug">
                {mission?.blocked_reason || agent?.blocked_or_replan_reason}
              </div>
              {mission?.symbolic_solution && mission.symbolic_solution.length > 0 && (
                <div className="text-[10px] font-mono text-slate-300 bg-[#080D16] px-1.5 py-1 rounded border border-slate-800 break-all">
                  符号序列 ({mission.symbolic_solution.length}步): {mission.symbolic_solution.join(' ')}
                </div>
              )}
            </div>
          )}

          {/* Mission 目标与结果摘要 */}
          <div className="p-2 rounded bg-[#080D16] border border-slate-800/90 space-y-1">
            <div className="flex items-center justify-between text-[10px] font-mono text-slate-400">
              <span>MISSION: {mission?.mission_type || selectedMission}</span>
              <span>{mission?.mission_id || '--'}</span>
            </div>
            <div className="text-[10.5px] text-slate-200 leading-snug">
              <span className="text-slate-400">目标：</span>
              {mission?.user_goal || missionSpec.shortDesc}
            </div>
            {mission?.result_summary && (
              <div className="text-[10.5px] text-[#30D6A0] leading-snug pt-0.5 border-t border-slate-800/80">
                {mission.result_summary}
              </div>
            )}
            {mission?.failure_reason && (
              <div className="text-[10.5px] text-[#FF667B] leading-snug pt-0.5 border-t border-slate-800/80">
                失败原因：{mission.failure_reason}
              </div>
            )}
          </div>

          {/* 观察摘要、实时观测帧引用、决策依据与 Safety Gate */}
          <div className="p-2 rounded bg-[#080D16] border border-slate-800/90 space-y-1.5">
            <div>
              <div className="text-[10px] font-mono text-slate-400">最新观察摘要与真实相机输入</div>
              {agent?.current_observation_image_url && (
                <div className="my-1 rounded overflow-hidden border border-slate-800 bg-black">
                  <img
                    src={agent.current_observation_image_url}
                    alt={agent.current_camera_id || 'VLM Input Frame'}
                    className="w-full aspect-[3/2] object-contain"
                  />
                  <div className="px-1.5 py-0.5 text-[9px] font-mono text-slate-400 flex justify-between">
                    <span>cam:{agent.current_camera_id || 'overhead'}</span>
                    <span>frm:{agent.current_frame_id || '--'}</span>
                  </div>
                </div>
              )}
              <div className="text-[10.5px] text-slate-200 leading-snug">
                {agent?.latest_observation ? (
                  <>
                    <div>{agent.latest_observation.summary}</div>
                    <div className="text-[9.5px] font-mono text-slate-500 mt-0.5">
                      obs:{agent.latest_observation.observation_id} · frm:{agent.latest_observation.frame_id} · t=
                      {agent.latest_observation.sim_time.toFixed(2)}s
                    </div>
                  </>
                ) : (
                  <span className="text-slate-500">尚未采集观测帧</span>
                )}
              </div>
            </div>

            <div className="pt-1 border-t border-slate-800/80 space-y-0.5">
              <div className="flex items-center justify-between text-[10px] font-mono text-slate-400">
                <span>当前选择动作与结构化依据</span>
                {typeof agent?.confidence === 'number' && (
                  <span className="text-[#3DE8E5]">conf:{agent.confidence.toFixed(2)}</span>
                )}
              </div>
              <div className="font-mono text-[10.5px] text-[#3DE8E5] break-all">
                {agent?.selected_action || '--'}
                {agent?.selected_parameters && Object.keys(agent.selected_parameters).length > 0
                  ? ` ${JSON.stringify(agent.selected_parameters)}`
                  : ''}
              </div>
              <div className="text-[10.5px] text-slate-300 leading-snug mt-0.5">
                {agent?.selection_rationale || plan?.rationale_summary || '等待任务启动后由规划器生成决策'}
              </div>
              {agent?.expected_information_gain && (
                <div className="text-[9.5px] text-slate-400 leading-snug">
                  预期信息增益：{agent.expected_information_gain}
                </div>
              )}
            </div>

            {agent?.safety_gate_status && (
              <div className="pt-1 border-t border-slate-800/80">
                <div className="text-[10px] font-mono text-slate-400">Safety Gate 校验结果</div>
                <div className={`font-mono text-[10px] ${safetyGateStyle}`}>
                  {agent.safety_gate_status}
                </div>
              </div>
            )}

            <div className="pt-1 border-t border-slate-800/80">
              <div className="text-[10px] font-mono text-slate-400">最近 Skill 调用与执行反馈</div>
              <div className="font-mono text-[10px] text-slate-200">{agent?.last_skill_call || '--'}</div>
              <div className="text-[10.5px] text-slate-400 leading-snug">
                {agent?.last_execution_feedback || '--'}
              </div>
            </div>
          </div>

          {/* 可审计决策事件流 (DecisionEvent) */}
          {selectedDecisionObservation?.image_url && selectedDecisionObservation.frame_source === 'REAL_MUJOCO_RENDERER' && (
            <div className="rounded border border-[#3DE8E5]/30 bg-black overflow-hidden">
              <div className="px-2 py-1 text-[9px] font-mono text-[#3DE8E5] bg-[#080D16]">
                历史决策图像 · {selectedDecisionObservation.observation_id} · {selectedDecisionObservation.frame_id || '--'}
              </div>
              <img
                src={selectedDecisionObservation.image_url}
                alt={`Historical observation ${selectedDecisionObservation.observation_id}`}
                className="w-full max-h-36 object-contain"
              />
            </div>
          )}
          {policyTraceEvents.length > 0 && (
            <div className="space-y-1">
              <div className="text-[10px] font-mono text-slate-400">
                ACTIVE SCAN POLICY · 确定性策略依据
              </div>
              {policyTraceEvents.slice().reverse().map((event) => (
                <div key={event.event_id} className="p-1.5 rounded bg-[#080D16] border border-[#548CFF]/30">
                  <div className="flex items-center justify-between text-[9.5px] font-mono">
                    <span className="text-[#548CFF]">{event.name}</span>
                    <span className="text-slate-500">t={event.sim_time.toFixed(2)}s</span>
                  </div>
                  <div className="text-[10px] text-slate-300 mt-0.5">
                    {String(event.evidence.reason || '')}
                  </div>
                  <div className="text-[9.5px] text-slate-500 font-mono">
                    unknown={String(event.evidence.remaining_unknown_facelets ?? event.evidence.unknown ?? '--')}
                    {' · '}next={String(event.evidence.selected_action ?? '--')}
                  </div>
                </div>
              ))}
            </div>
          )}

          {snapshot.relay_state?.enabled && (
            <div className="p-2 rounded bg-[#080D16] border border-[#548CFF]/40 space-y-1">
              <div className="text-[10px] font-mono text-[#3DE8E5] font-semibold flex items-center justify-between">
                <span>EXECUTION CONTRACT &amp; BELIEF · 契约与信念透视</span>
                <span className={snapshot.relay_state.contract.is_lattice_aligned ? 'text-[#30D6A0]' : 'text-[#FFBF69]'}>
                  {snapshot.relay_state.contract.is_lattice_aligned ? '晶格对齐' : '半拧保持'}
                </span>
              </div>
              <div className="text-[10px] font-mono text-slate-300 space-y-0.5">
                <div>
                  守恒锁定:{' '}
                  <span className={snapshot.relay_state.belief.deduced_54_unique ? 'text-[#30D6A0]' : 'text-[#FFBF69]'}>
                    {snapshot.relay_state.belief.deduced_54_unique ? '54/54 唯一锁定' : `歧义 ${snapshot.relay_state.belief.ambiguous_facelet_count} 格`}
                  </span>
                  {' · '}视觉反推: {snapshot.relay_state.belief.inferred_human_moves.join(' ') || '无'}
                </div>
                <div>
                  契约模式: {snapshot.relay_state.contract.active_contract?.mid_turn_recovery_mode || 'UNWIND_TO_ZERO'}
                  {' · '}过期响应拦截: {snapshot.relay_state.contract.stale_guard?.stale_responses_discarded ?? 0} 次
                </div>
                {snapshot.relay_state.belief.reasoning_summary_zh && (
                  <div className="text-slate-400 font-sans text-[10px] leading-snug">
                    {snapshot.relay_state.belief.reasoning_summary_zh}
                  </div>
                )}
              </div>
            </div>
          )}

          <div className="space-y-1">
            <div className="text-[10px] font-mono text-slate-400 flex items-center justify-between">
              <span>DECISION EVENTS · 决策审计流</span>
              <span>{decisionEvents.length} 条</span>
            </div>
            {decisionEvents.length === 0 ? (
              <div className="p-2 rounded bg-[#080D16] border border-slate-800 text-[10.5px] text-slate-500">
                暂无决策事件（点击底部「开始任务」执行当前 Mission）
              </div>
            ) : (
              <div className="space-y-1">
                {decisionEvents
                  .slice()
                  .reverse()
                  .map((ev) => {
                    const evColor =
                      ev.event_type === 'CAPABILITY_BLOCKED'
                        ? 'text-[#FFBF69]'
                        : ev.event_type.includes('FAILED')
                        ? 'text-[#FF667B]'
                        : 'text-[#3DE8E5]';
                    const srcColor = ev.source === 'gemini_vlm' ? 'text-[#30D6A0]' : 'text-slate-400';
                    return (
                      <button
                        type="button"
                        key={ev.event_id}
                        onClick={() => ev.observation_id && setSelectedDecisionObservationId(ev.observation_id)}
                        className="w-full text-left p-1.5 rounded bg-[#080D16] border border-slate-800/80 space-y-0.5 hover:border-[#3DE8E5]/40 disabled:cursor-default"
                      >
                        <div className="flex items-center justify-between gap-1 text-[9.5px] font-mono">
                          <span className={evColor}>
                            #{ev.sequence} {ev.event_type}
                          </span>
                          <span className="text-slate-500">
                            {ev.sim_time !== null && ev.sim_time !== undefined ? `${ev.sim_time.toFixed(2)}s` : ev.wall_time}
                          </span>
                        </div>
                        <div className="flex items-center justify-between gap-1 text-[9px] font-mono">
                          <span className={srcColor}>src:{ev.source}</span>
                          <span className="text-slate-500">
                            {ev.validation_result ? ev.validation_result : ''}
                            {typeof ev.model_latency_ms === 'number' ? ` · ${ev.model_latency_ms.toFixed(0)}ms` : ''}
                          </span>
                        </div>
                        <div className="text-[10.5px] text-slate-200 leading-snug">{ev.summary}</div>
                        <div className="text-[10px] text-slate-400 leading-snug">{ev.decision_rationale_summary}</div>
                      </button>
                    );
                  })}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Skill / 执行流水线（接力模式下点击折叠开关展开） */}
      {showSkillPanel && (
        <div className={isRelayMission ? 'order-4 max-h-56 shrink-0 flex flex-col justify-between gap-1.5 overflow-y-auto pr-0.5 border border-slate-800/80 rounded p-1.5 bg-[#0A101B]' : 'flex-1 min-h-0 flex flex-col justify-between gap-1.5 overflow-y-auto pr-0.5'}>
          <div className="space-y-1 flex-1 overflow-y-auto">
            {vlmCompositeTrace && (
              <div className="px-2 py-1.5 rounded border bg-[#0C1422] border-[#30D6A0]/40 space-y-1 text-[11px]">
                <button
                  type="button"
                  onClick={() => setExpandedSkills((previous) => {
                    const next = new Set(previous);
                    next.has(vlmCompositeTrace.event_id)
                      ? next.delete(vlmCompositeTrace.event_id)
                      : next.add(vlmCompositeTrace.event_id);
                    return next;
                  })}
                  className="w-full flex items-center justify-between text-[10px] font-mono text-[#30D6A0]"
                >
                  <span className="flex items-center gap-1">
                    {expandedSkills.has(vlmCompositeTrace.event_id) ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
                    VLM 闭环扫描 Trace · 子事件 {vlmCompositeChildren.length}
                  </span>
                  <span>{vlmCompositeTrace.status}</span>
                </button>
                {expandedSkills.has(vlmCompositeTrace.event_id) && (
                  <div className="ml-1 border-l border-slate-700 pl-2 space-y-1">
                    {vlmCompositeChildren.map((event) => (
                      <div key={event.event_id} className="rounded border p-1 bg-[#080D16] border-slate-800 text-[9.5px]">
                        <div className="flex items-center justify-between font-mono">
                          <span className="text-[#3DE8E5]">{event.event_type.toUpperCase()} {event.name}</span>
                          <span className="text-slate-500">{event.sim_time.toFixed(2)}s</span>
                        </div>
                        <div className="text-slate-400">src:{event.source} · {event.status}</div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
            {!plan || plan.steps.length === 0 ? (
              <div className="p-2.5 rounded bg-[#080D16] border border-slate-800 text-[11px] text-slate-400">
                {isVlmPlanner
                  ? 'Gemini VLM 闭环模式下将按实时视觉观测逐步动态生成动作。'
                  : '尚未生成任务计划，请选择 Mission 并启动任务。'}
              </div>
            ) : (
              plan.steps.map((st) => {
                const isCurrent = st.step_id === plan.current_step_id && st.status === 'RUNNING';
                const execRec = executions.find((ex) => ex.step_id === st.step_id);
                const composite = traceEvents.find(
                  (event) => event.event_type === 'composite_skill' && event.skill_id === st.skill_id
                );
                const childEvents = composite
                  ? traceEvents.filter((event) => event.parent_event_id === composite.event_id)
                  : traceEvents.filter(
                      (event) =>
                        event.skill_id === st.skill_id &&
                        event.event_type !== 'composite_skill' &&
                        event.event_type !== 'mission'
                    );
                const hasChildren = Boolean(composite) || childEvents.length > 0;
                const skillExpanded = expandedSkills.has(st.step_id);
                return (
                  <div
                    key={st.step_id}
                    className={`px-2 py-1.5 rounded border space-y-1 text-[11px] ${
                      isCurrent
                        ? 'bg-[#182338] border-[#548CFF]/60'
                        : st.status === 'BLOCKED'
                        ? 'bg-[#FFBF69]/10 border-[#FFBF69]/50'
                        : 'bg-[#080D16] border-slate-800/80'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-1.5">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-1.5">
                          <span className="font-mono text-[10px] text-slate-500">0{st.index}</span>
                          <span className="font-medium text-slate-200 truncate">{st.title}</span>
                        </div>
                        <div className="font-mono text-[9.5px] text-[#3DE8E5] pl-5 truncate">{st.skill_id}</div>
                      </div>
                      <div className="flex items-center gap-1 shrink-0">
                        {st.elapsed_sec !== null && st.elapsed_sec !== undefined && (
                          <span className="font-mono text-[9.5px] text-slate-400">
                            {st.elapsed_sec.toFixed(2)}s
                          </span>
                        )}
                        <StageStatusBadge status={st.status} implemented={st.implemented} />
                      </div>
                    </div>

                    {(st.started_sim_time !== null && st.started_sim_time !== undefined) && (
                      <div className="text-[9.5px] font-mono text-slate-500 pl-5">
                        sim: {st.started_sim_time.toFixed(2)}s →{' '}
                        {st.ended_sim_time !== null && st.ended_sim_time !== undefined
                          ? `${st.ended_sim_time.toFixed(2)}s`
                          : '...'}
                      </div>
                    )}

                    {(st.result_summary || execRec?.result_summary) && (
                      <div className="text-[10px] text-slate-300 pl-5 leading-snug">
                        {st.result_summary || execRec?.result_summary}
                      </div>
                    )}

                    {st.failure_reason && (
                      <div className="text-[10px] text-[#FF667B] pl-5 leading-snug">
                        原因: {st.failure_reason}
                      </div>
                    )}

                    {hasChildren && (
                      <div className="pl-5 pt-0.5">
                        <button
                          type="button"
                          onClick={() => setExpandedSkills((previous) => {
                            const next = new Set(previous);
                            next.has(st.step_id) ? next.delete(st.step_id) : next.add(st.step_id);
                            return next;
                          })}
                          className="flex items-center gap-1 text-[10px] font-mono text-[#3DE8E5] hover:text-white"
                        >
                          {skillExpanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
                          子事件 {childEvents.length} · {composite ? composite.status : st.status}
                        </button>

                        {skillExpanded && (
                          <div className="mt-1 ml-1 border-l border-slate-700 pl-2 space-y-1">
                            {childEvents.map((event) => {
                              const eventExpanded = expandedTraceEvents.has(event.event_id);
                              const eventFailed = event.status === 'FAILED';
                              const evidence = event.evidence || {};
                              const target = evidence.target_parameters || {};
                              const measured = evidence.measured_parameters || {};
                              return (
                                <div key={event.event_id} className={`rounded border p-1.5 ${
                                  eventFailed
                                    ? 'bg-[#FF667B]/10 border-[#FF667B]/40'
                                    : 'bg-[#0C1422] border-slate-800'
                                }`}>
                                  <button
                                    type="button"
                                    onClick={() => setExpandedTraceEvents((previous) => {
                                      const next = new Set(previous);
                                      next.has(event.event_id) ? next.delete(event.event_id) : next.add(event.event_id);
                                      return next;
                                    })}
                                    className="w-full text-left"
                                  >
                                    <div className="flex items-center justify-between gap-1">
                                      <span className="flex items-center gap-1 font-mono text-[9.5px] text-slate-200">
                                        {eventExpanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
                                        <span className={
                                          event.event_type === 'perception' ? 'text-[#3DE8E5]' :
                                          event.event_type === 'decision' ? 'text-[#548CFF]' :
                                          event.event_type === 'verification' ? 'text-[#30D6A0]' : 'text-[#FFBF69]'
                                        }>{event.event_type.toUpperCase()}</span>
                                        {event.name}
                                      </span>
                                      <span className="font-mono text-[9px] text-slate-500">
                                        {event.sim_time.toFixed(2)}→{(event.end_sim_time ?? event.sim_time).toFixed(2)}s
                                      </span>
                                    </div>
                                    {event.event_type === 'perception' && (
                                      <div className="text-[9.5px] text-slate-400 pl-4 mt-0.5">
                                        {(evidence.camera_ids || []).join(', ') || '无有效相机'} · 新增 {String(evidence.newly_observed ?? 0)} 格 · Unknown {String(evidence.unknown_before)}→{String(evidence.unknown_after)} · 冲突 {String(evidence.conflicts ?? 0)}
                                      </div>
                                    )}
                                    {event.event_type === 'action' && event.name.includes('reorient') && (
                                      <div className="text-[9.5px] text-slate-400 pl-4 mt-0.5">
                                        {String(target.axis || '--')} · 目标 {typeof target.degrees === 'number' ? target.degrees.toFixed(1) : '--'}° · 实测 {typeof measured.degrees === 'number' ? measured.degrees.toFixed(1) : '--'}°
                                      </div>
                                    )}
                                  </button>

                                  {eventExpanded && (
                                    <div className="mt-1 pl-4 space-y-1 text-[9.5px] text-slate-400">
                                      {event.event_type === 'perception' && evidence.camera_contributions && (
                                        <div className="font-mono">
                                          {Object.entries(evidence.camera_contributions).map(([camera, indices]) => (
                                            <div key={camera}>{camera}: [{(indices as number[]).join(', ')}]</div>
                                          ))}
                                        </div>
                                      )}
                                      {Array.isArray(evidence.frame_images) && evidence.frame_images.length > 0 && (
                                        <div className="grid grid-cols-2 gap-1">
                                          {evidence.frame_images.map((frame: any) => (
                                            <figure key={frame.frame_ref} className="bg-black/30 rounded overflow-hidden border border-slate-800">
                                              <img src={frame.image_url} alt={frame.camera_id} className="w-full aspect-[3/2] object-contain" />
                                              <figcaption className="px-1 py-0.5 truncate font-mono text-[8.5px]">{frame.camera_id}</figcaption>
                                            </figure>
                                          ))}
                                        </div>
                                      )}
                                      <details>
                                        <summary className="cursor-pointer text-slate-500">详细参数</summary>
                                        <pre className="mt-1 p-1 rounded bg-black/20 overflow-x-auto whitespace-pre-wrap break-all text-[8.5px]">{JSON.stringify(evidence, null, 2)}</pre>
                                      </details>
                                    </div>
                                  )}
                                </div>
                              );
                            })}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>

          {/* 物理验收证据摘要（如在 VERIFY_PHYSICAL_U_TURN 后） */}
          {snapshot.physical_verification && (
            <div className="p-2 rounded bg-[#080D16] border border-[#30D6A0]/30 text-[10px] font-mono space-y-0.5 shrink-0">
              <div className="text-[#30D6A0] font-semibold">物理接触与视觉复核证据</div>
              <div className="text-slate-300">
                实测转角: {String(snapshot.physical_verification.actual_angle_deg ?? '--')}° · 误差:{' '}
                {typeof snapshot.physical_verification.layer_error_rad === 'number'
                  ? snapshot.physical_verification.layer_error_rad.toExponential(2)
                  : '--'}{' '}
                rad
              </div>
              <div className="text-slate-300">
                接触力(底座/拧头): {String(snapshot.physical_verification.min_base_contact_n ?? '--')}N /{' '}
                {String(snapshot.physical_verification.min_turn_contact_n ?? '--')}N · 21格:{' '}
                {snapshot.physical_verification.affected_21_verified ? 'VERIFIED' : 'PENDING'}
              </div>
            </div>
          )}
        </div>
      )}

      {/* M5 Agent 人机接力主控制面板 (接力模式下直接常驻展开) */}
      {isRelayMission && (() => {
        const relay = snapshot.relay_state;
        const waitingHuman = Boolean(relay?.human_pad?.waiting_for_human);
        const padActive = Boolean(relay?.human_pad?.active) && mode === 'LIVE';
        const suggested = relay?.delegation?.suggested_moves || [];
        const prefDone = relay?.delegation?.completed_prefix_count || 0;
        const deviated = Boolean(relay?.delegation?.deviated_this_turn);
        const nextHint = relay?.human_pad?.highlighted_next_move;
        const clarPending = Boolean(relay?.hri?.clarification_pending);
        const clicks = relay?.human_pad?.clicks_this_turn || [];
        const dialog = relay?.hri?.dialog_history || [];
        const turnInfo = relay?.turn_indicator;
        const owner = turnInfo?.owner || (
          waitingHuman ? 'HUMAN' : clarPending ? 'CLARIFY' : relay?.phase === 'RELAY_COMPLETED_VERIFIED' ? 'DONE' : snapshot.running ? 'ROBOT' : 'IDLE'
        );
        const rightTurnCls =
          owner === 'HUMAN'
            ? 'bg-[#FFBF69]/15 border-[#FFBF69]/60 text-[#FFBF69]'
            : owner === 'CLARIFY'
            ? 'bg-[#8B5CF6]/15 border-[#8B5CF6]/50 text-[#A78BFA]'
            : owner === 'DONE'
            ? 'bg-[#30D6A0]/15 border-[#30D6A0]/50 text-[#30D6A0]'
            : owner === 'ROBOT'
            ? 'bg-[#3DE8E5]/10 border-[#3DE8E5]/40 text-[#3DE8E5]'
            : 'bg-[#080D16] border-slate-800 text-slate-300';

        const applyPerturb = (dxCm: number, dyCm: number, dyawDeg: number, label: string) => {
          setPerturbDxCm(dxCm);
          setPerturbDyCm(dyCm);
          setPerturbYawDeg(dyawDeg);
          onRelayCommand(
            { type: 'HUMAN_PERTURB_POSE', dx_m: dxCm / 100.0, dy_m: dyCm / 100.0, dyaw_deg: dyawDeg },
            label
          );
        };

        const sendChat = (text: string) => {
          const clean = text.trim();
          if (!clean) return;
          onRelayCommand({ type: 'HUMAN_SEND_CHAT', text: clean }, `发送指令: ${clean}`);
          setChatDraft('');
        };

        return (
          <div className="order-1 flex-1 min-h-0 overflow-y-auto space-y-2 pr-0.5 text-[11px]">
            {/* 回合归属醒目指示卡 */}
            <div className={`p-2 rounded border space-y-1 ${rightTurnCls}`}>
              <div className="flex items-center justify-between gap-2 text-[11px] font-bold">
                <span>{turnInfo?.owner_label_zh || (waitingHuman ? '🧑 轮到人类操作' : '🤖 等待/机器人回合')}</span>
                <span className="font-mono text-[10px]">第 {relay?.round_number || 1} 轮</span>
              </div>
              <label className="flex items-center justify-between gap-2">
                本回合机器人步数配额: {relay?.robot_moves_this_turn ?? 0} / {relay?.max_robot_moves_per_turn === null ? '∞' : relay?.max_robot_moves_per_turn ?? 3}
                <select aria-label="每回合机器人步数" className="rounded bg-[#080D16] border border-slate-700"
                  value={relay?.max_robot_moves_per_turn === null ? 'unlimited' : relay?.max_robot_moves_per_turn ?? 3}
                  onChange={e => onRelayCommand({ type: 'SET_TURN_QUOTA', quota: e.target.value === 'unlimited' ? 'unlimited' : Number(e.target.value) }, '设置回合配额')}>
                  <option value="1">1 步</option><option value="2">2 步</option>
                  <option value="3">3 步</option><option value="unlimited">全托管</option>
                </select>
              </label>
              <div className="text-[10px] opacity-85 leading-snug">
                {turnInfo?.next_action_hint_zh || relay?.banner?.subtitle_zh || '等待任务启动。'}
              </div>
            </div>
            {/* 模块 2: 推荐 1~3 步高亮提示与 Agent 具身委派说明卡 */}
            <div className="p-2 rounded bg-[#080D16] border border-[#3DE8E5]/30 space-y-1.5">
              <div className="flex items-center justify-between gap-1 text-[10px] font-mono">
                <span className="text-[#3DE8E5] font-semibold">AGENT DELEGATION · 推荐接力序列</span>
                <span className="text-slate-400">已省高代价翻面 {relay?.delegation?.saved_high_cost_flips_count ?? 0} 次</span>
              </div>
              {suggested.length > 0 ? (
                <div className="flex items-center gap-1 flex-wrap">
                  {suggested.map((mv, idx) => {
                    const done = idx < prefDone && !deviated;
                    const isNext = idx === prefDone && !deviated && waitingHuman;
                    return (
                      <span
                        key={`${mv}-${idx}`}
                        className={`px-2 py-0.5 rounded font-mono text-[10.5px] border ${
                          done
                            ? 'bg-[#30D6A0]/15 text-[#30D6A0] border-[#30D6A0]/40'
                            : isNext
                            ? 'bg-[#FFBF69]/20 text-[#FFBF69] border-[#FFBF69]/60 animate-pulse'
                            : 'bg-[#182338] text-slate-300 border-slate-700'
                        }`}
                      >
                        {done ? '✓ ' : `Step ${idx + 1}: `}
                        {mv}
                      </span>
                    );
                  })}
                </div>
              ) : (
                <div className="text-[10px] text-slate-400">
                  当前无强制推荐序列（可自由点击下方 18 动作或发送自然语言要求）。
                </div>
              )}
              {deviated && (
                <div className="px-2 py-1 rounded bg-[#FFBF69]/15 border border-[#FFBF69]/40 text-[10px] text-[#FFBF69]">
                  ⚡ 检测到自由发挥/偏离推荐路线，交回后 Agent 将靠 RGB-D 重新识别并决定策略
                </div>
              )}
              <div className="text-[10px] text-slate-300 leading-snug">
                {relay?.delegation?.delegation_reason_zh || '等待 Agent 完成感知建信并生成具身代价切分建议。'}
              </div>
            </div>

            {/* 澄清问题回应卡片 (当 Agent 调用 ask_human_clarification) */}
            {clarPending && (
              <div className="p-2 rounded bg-[#FFBF69]/10 border border-[#FFBF69]/50 space-y-1.5">
                <div className="text-[10.5px] font-semibold text-[#FFBF69]">
                  💬 Agent 请求意图澄清
                </div>
                <div className="text-[10.5px] text-slate-200 leading-snug">
                  {relay?.hri?.clarification_question_zh}
                </div>
                <div className="flex flex-col gap-1">
                  {(relay?.hri?.clarification_options || []).map((opt) => (
                    <button
                      key={opt}
                      type="button"
                      disabled={mode !== 'LIVE'}
                      onClick={() => sendChat(opt)}
                      className="text-left px-2 py-1 rounded text-[10px] bg-[#182338] hover:bg-[#548CFF]/20 text-[#3DE8E5] border border-[#3DE8E5]/30 transition-colors disabled:opacity-40"
                    >
                      → {opt}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* 模块 3: 18 动作自由点击盘 (全 18 按钮 100% 开放) */}
            <div className="p-2 rounded bg-[#080D16] border border-slate-800 space-y-1.5">
              <div className="flex items-center justify-between gap-1 text-[10px]">
                <span className="font-mono text-slate-300 font-semibold">18-MOVE PAD · 26-Cubie 真实物理转层</span>
                <button
                  type="button"
                  disabled={!padActive || !relay?.human_pad?.can_undo}
                  onClick={() => onRelayCommand({ type: 'HUMAN_UNDO_MOVE' }, '物理撤销上一步')}
                  className="px-1.5 py-0.5 rounded bg-[#182338] text-slate-300 border border-slate-700 hover:text-white disabled:opacity-40 disabled:cursor-not-allowed text-[9.5px]"
                >
                  撤销上一步
                </button>
              </div>
              <div className="space-y-1">
                {RELAY_FACE_GROUPS.map((grp) => (
                  <div key={grp.face} className="grid grid-cols-3 gap-1">
                    {grp.moves.map((mv) => {
                      const isHint = nextHint === mv && waitingHuman;
                      return (
                        <button
                          key={mv}
                          type="button"
                          disabled={!padActive}
                          onClick={() => onRelayCommand({ type: 'HUMAN_APPLY_MOVE', move: mv }, `人类物理旋转 ${mv}`)}
                          className={`py-1 rounded font-mono text-[10.5px] font-semibold border transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${
                            isHint
                              ? 'bg-[#3DE8E5]/20 text-[#3DE8E5] border-[#3DE8E5] animate-pulse'
                              : 'bg-[#182338] hover:bg-[#548CFF]/30 text-slate-200 border-slate-700'
                          }`}
                        >
                          {mv}
                        </button>
                      );
                    })}
                  </div>
                ))}
              </div>
              {clicks.length > 0 && (
                <div className="text-[10px] font-mono text-slate-400">
                  本轮已拧: <span className="text-[#3DE8E5]">{clicks.join(' → ')}</span>
                </div>
              )}
              <button
                type="button"
                disabled={!waitingHuman || mode !== 'LIVE'}
                onClick={() => onRelayCommand({ type: 'HUMAN_FINISH_TURN' }, '完成本回合，交回机器人')}
                className="w-full py-1.5 rounded text-[11px] font-semibold bg-[#30D6A0]/20 hover:bg-[#30D6A0]/30 text-[#30D6A0] border border-[#30D6A0]/50 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                完成本回合，交回机器人
              </button>
            </div>

            {/* 模块 4: 放回位置微扰控件 */}
            <div className="p-2 rounded bg-[#080D16] border border-slate-800 space-y-1.5">
              <div className="flex items-center justify-between text-[10px] font-mono text-slate-300">
                <span>PUT-BACK PERTURB · 放回桌面位置微扰</span>
                <span className="text-[#FFBF69]">
                  {perturbDxCm >= 0 ? `+${perturbDxCm}` : perturbDxCm}cm,{' '}
                  {perturbDyCm >= 0 ? `+${perturbDyCm}` : perturbDyCm}cm,{' '}
                  {perturbYawDeg >= 0 ? `+${perturbYawDeg}` : perturbYawDeg}°
                </span>
              </div>
              <div className="space-y-1 text-[10px] font-mono text-slate-400">
                <div className="flex items-center justify-between gap-2">
                  <span className="w-16">ΔX (±8cm)</span>
                  <input
                    type="range"
                    min={-8}
                    max={8}
                    step={1}
                    disabled={!padActive}
                    value={perturbDxCm}
                    onChange={(e) => setPerturbDxCm(Number(e.target.value))}
                    onMouseUp={() => applyPerturb(perturbDxCm, perturbDyCm, perturbYawDeg, '调整 ΔX 微扰')}
                    onTouchEnd={() => applyPerturb(perturbDxCm, perturbDyCm, perturbYawDeg, '调整 ΔX 微扰')}
                    className="flex-1"
                  />
                </div>
                <div className="flex items-center justify-between gap-2">
                  <span className="w-16">ΔY (±8cm)</span>
                  <input
                    type="range"
                    min={-8}
                    max={8}
                    step={1}
                    disabled={!padActive}
                    value={perturbDyCm}
                    onChange={(e) => setPerturbDyCm(Number(e.target.value))}
                    onMouseUp={() => applyPerturb(perturbDxCm, perturbDyCm, perturbYawDeg, '调整 ΔY 微扰')}
                    onTouchEnd={() => applyPerturb(perturbDxCm, perturbDyCm, perturbYawDeg, '调整 ΔY 微扰')}
                    className="flex-1"
                  />
                </div>
                <div className="flex items-center justify-between gap-2">
                  <span className="w-16">ΔYaw(±40°)</span>
                  <input
                    type="range"
                    min={-40}
                    max={40}
                    step={1}
                    disabled={!padActive}
                    value={perturbYawDeg}
                    onChange={(e) => setPerturbYawDeg(Number(e.target.value))}
                    onMouseUp={() => applyPerturb(perturbDxCm, perturbDyCm, perturbYawDeg, '调整 ΔYaw 微扰')}
                    onTouchEnd={() => applyPerturb(perturbDxCm, perturbDyCm, perturbYawDeg, '调整 ΔYaw 微扰')}
                    className="flex-1"
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-1 text-[9.5px]">
                <button
                  type="button"
                  disabled={!padActive}
                  onClick={() => applyPerturb(0, 0, 0, '预设: 标准原位')}
                  className="px-1.5 py-1 rounded bg-[#182338] hover:bg-slate-700 text-slate-300 border border-slate-700 disabled:opacity-40"
                >
                  标准原位
                </button>
                <button
                  type="button"
                  disabled={!padActive}
                  onClick={() => applyPerturb(4, 0, 15, '预设: 轻推偏移')}
                  className="px-1.5 py-1 rounded bg-[#182338] hover:bg-slate-700 text-slate-300 border border-slate-700 disabled:opacity-40"
                >
                  轻推偏移 (+4cm,+15°)
                </button>
                <button
                  type="button"
                  disabled={!padActive}
                  onClick={() => applyPerturb(6, -4, 20, '预设: 跨度微扰')}
                  className="px-1.5 py-1 rounded bg-[#182338] hover:bg-slate-700 text-slate-300 border border-slate-700 disabled:opacity-40"
                >
                  跨度微扰 (+6cm,-4cm,+20°)
                </button>
                <button
                  type="button"
                  disabled={!padActive}
                  onClick={() => {
                    const rx = Math.round((Math.random() * 16 - 8));
                    const ry = Math.round((Math.random() * 16 - 8));
                    const ryaw = Math.round((Math.random() * 76 - 38));
                    applyPerturb(rx, ry, ryaw, '预设: 随机随手放');
                  }}
                  className="px-1.5 py-1 rounded bg-[#182338] hover:bg-slate-700 text-[#FFBF69] border border-slate-700 disabled:opacity-40"
                >
                  随机随手放
                </button>
              </div>
            </div>

            {/* 模块 5: 人机自然语言协作对话与快捷意图栏 */}
            <div className="p-2 rounded bg-[#080D16] border border-slate-800 space-y-1.5">
              <div className="flex items-center justify-between gap-1 text-[10px] font-mono">
                <span className="text-[#3DE8E5] font-semibold">
                  LIVE HRI DIALOG · LLM 语义意图路由
                </span>
                {relay?.hri?.latest_semantics && (
                  <span className="px-1.5 py-0.5 rounded bg-[#182338] border border-slate-700 text-[9px] text-[#30D6A0] truncate">
                    {relay.hri.latest_semantics.speech_act}
                    {typeof relay.hri.latest_semantics.latency_ms === 'number'
                      ? ` · ${relay.hri.latest_semantics.latency_ms.toFixed(0)}ms`
                      : ''}
                  </span>
                )}
              </div>
              {(relay?.hri?.active_constraints || []).length > 0 && (
                <div className="flex items-center gap-1 flex-wrap text-[9px]">
                  <span className="text-slate-400 font-mono">持久约束:</span>
                  {(relay?.hri?.active_constraints || []).map((c, idx) => (
                    <span
                      key={`${c}-${idx}`}
                      className="px-1.5 py-0.5 rounded bg-[#30D6A0]/10 border border-[#30D6A0]/30 text-[#30D6A0]"
                    >
                      {c}
                    </span>
                  ))}
                </div>
              )}
              <div className="max-h-36 overflow-y-auto space-y-1 bg-[#0C1422] border border-slate-800/70 rounded p-1.5">
                {dialog.length === 0 ? (
                  <div className="text-[10px] text-slate-500">随时可发送偏好约束、澄清回复或机械臂执行中途紧急刹车指令。</div>
                ) : (
                  dialog.map((msg, i) => {
                    const isHumanMsg = msg.role === 'human';
                    const sem = msg.semantics;
                    const bubbleCls = isHumanMsg
                      ? 'bg-[#548CFF]/15 text-slate-100 border border-[#548CFF]/30'
                      : 'bg-[#182338] text-[#3DE8E5] border border-slate-700';
                    return (
                    <div
                      key={i}
                      className={`px-1.5 py-1 rounded text-[10px] leading-snug space-y-0.5 ${bubbleCls}`}
                    >
                      <div>
                        <span className="font-mono font-semibold mr-1">
                          {isHumanMsg ? '🧑 人类:' : '🤖 Agent:'}
                        </span>
                        <span>{msg.text}</span>
                      </div>
                      {isHumanMsg && sem && (
                        <div className="flex items-center gap-1 flex-wrap text-[9px] font-mono text-slate-300 pt-0.5 border-t border-slate-700/60">
                          <span className="px-1 py-0.2 rounded bg-[#080D16] border border-[#3DE8E5]/40 text-[#3DE8E5]">
                            {sem.speech_act}
                          </span>
                          <span
                            className={`px-1 py-0.2 rounded border ${
                              sem.requires_immediate_motion_interrupt
                                ? 'bg-[#FF667B]/15 border-[#FF667B]/40 text-[#FF667B]'
                                : 'bg-[#30D6A0]/10 border-[#30D6A0]/30 text-[#30D6A0]'
                            }`}
                          >
                            {sem.requires_immediate_motion_interrupt ? '⚡立即中断' : '平滑不中断'}
                          </span>
                          {typeof sem.latency_ms === 'number' && (
                            <span className="text-slate-400">{sem.latency_ms.toFixed(0)}ms</span>
                          )}
                          {sem.persistent_constraints_to_add && sem.persistent_constraints_to_add.length > 0 && (
                            <span className="text-[#FFBF69]">
                              +约束: {sem.persistent_constraints_to_add.join('；')}
                            </span>
                          )}
                        </div>
                      )}
                    </div>
                    );
                  })
                )}
              </div>
              <div className="flex items-center gap-1">
                <input
                  type="text"
                  value={chatDraft}
                  onChange={(e) => setChatDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') sendChat(chatDraft);
                  }}
                  placeholder="输入中文约束/意图/实时打断指令..."
                  disabled={mode !== 'LIVE'}
                  className="flex-1 rounded border border-slate-700 bg-[#0C1422] px-2 py-1 text-[10.5px] text-slate-100 placeholder:text-slate-600 outline-none focus:border-[#30D6A0]"
                />
                <button
                  type="button"
                  disabled={mode !== 'LIVE' || !chatDraft.trim()}
                  onClick={() => sendChat(chatDraft)}
                  className="px-2 py-1 rounded text-[10.5px] font-semibold bg-[#548CFF] text-white disabled:opacity-40"
                >
                  发送
                </button>
              </div>
              <div className="flex items-center gap-1 flex-wrap">
                {QUICK_HRI_CHIPS.map((chip) => (
                  <button
                    key={chip.label}
                    type="button"
                    disabled={mode !== 'LIVE'}
                    title={chip.text}
                    onClick={() => sendChat(chip.text)}
                    className="px-1.5 py-0.5 rounded text-[9.5px] bg-[#182338] hover:bg-slate-700 text-slate-300 border border-slate-700 disabled:opacity-40"
                  >
                    {chip.label}
                  </button>
                ))}
              </div>
            </div>
          </div>
        );
      })()}
    </div>
  );
};

// ============================================================================
// 7. 紧凑型底部三等分仪表栏: (1) 机器人相机 (2) 魔方状态 (3) 遥测监控
// ============================================================================

const CompactRobotCameraCard: React.FC<{
  rgbUrl: string | null;
  depthUrl: string | null;
  depthRangeM: [number, number];
  detections: CameraDetectionBox[];
}> = ({ rgbUrl, depthUrl, depthRangeM, detections }) => {
  const [sensorMode, setSensorMode] = useState<'RGB' | 'DEPTH'>('RGB');
  const [showOverlay, setShowOverlay] = useState<boolean>(true);
  const activeUrl = sensorMode === 'RGB' ? rgbUrl : depthUrl;

  return (
    <div className="bg-[#101827] border border-slate-800/90 rounded-lg p-2.5 flex flex-col justify-between h-full min-h-0">
      <div className="flex items-center justify-between gap-1.5 mb-1.5 shrink-0">
        <div className="flex items-center gap-1.5 min-w-0">
          <Camera className="w-3.5 h-3.5 text-[#3DE8E5] shrink-0" />
          <span className="text-[11px] font-semibold tracking-wider text-slate-200 uppercase truncate">
            ROBOT CAMERA · 机器人相机
          </span>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <button
            type="button"
            onClick={() => setShowOverlay((v) => !v)}
            className={`px-1.5 py-0.5 rounded text-[10px] border transition-colors ${
              showOverlay
                ? 'bg-[#3DE8E5]/15 text-[#3DE8E5] border-[#3DE8E5]/40'
                : 'bg-[#182338] text-slate-400 border-slate-700'
            }`}
          >
            检测框
          </button>
          <div className="flex rounded bg-[#080D16] p-0.5 border border-slate-800 text-[10px] font-mono">
            <button
              type="button"
              onClick={() => setSensorMode('RGB')}
              className={`px-1.5 py-0.2 rounded ${
                sensorMode === 'RGB' ? 'bg-[#548CFF] text-white' : 'text-slate-400'
              }`}
            >
              RGB
            </button>
            <button
              type="button"
              onClick={() => setSensorMode('DEPTH')}
              className={`px-1.5 py-0.2 rounded ${
                sensorMode === 'DEPTH' ? 'bg-[#548CFF] text-white' : 'text-slate-400'
              }`}
            >
              Depth
            </button>
          </div>
        </div>
      </div>

      <div className="relative flex-1 min-h-0 w-full rounded bg-[#080D16] border border-slate-800 overflow-hidden flex items-center justify-center">
        {activeUrl ? (
          <>
            <img src={activeUrl} alt={sensorMode} className="w-full h-full object-contain" />
            {showOverlay && detections.length > 0 && (
              <svg
                viewBox="0 0 100 100"
                preserveAspectRatio="none"
                className="absolute inset-0 w-full h-full pointer-events-none"
              >
                {detections.map((box) => (
                  <g key={box.id}>
                    <rect
                      x={box.xNorm * 100}
                      y={box.yNorm * 100}
                      width={box.wNorm * 100}
                      height={box.hNorm * 100}
                      fill="none"
                      stroke="#3DE8E5"
                      strokeWidth="0.65"
                    />
                  </g>
                ))}
              </svg>
            )}
          </>
        ) : (
          <div className="text-center px-2 space-y-1">
            <Scan className="w-4 h-4 mx-auto text-slate-500" />
            <div className="text-[11px] text-slate-400">相机数据不可用</div>
          </div>
        )}
      </div>

      {sensorMode === 'DEPTH' && (
        <div className="flex items-center justify-between gap-2 pt-1 text-[10px] font-mono text-slate-400 shrink-0">
          <span>{depthRangeM[0].toFixed(2)}m</span>
          <div
            className="flex-1 h-1.5 rounded border border-slate-700"
            style={{
              background:
                'linear-gradient(to right, #0f172a, #1d4ed8, #06b6d4, #22c55e, #eab308, #ef4444)',
            }}
          />
          <span>{depthRangeM[1].toFixed(2)}m</span>
        </div>
      )}
    </div>
  );
};

const CompactCubeStateCard: React.FC<{
  observed: FaceletObservation[];
  predicted: FaceletColor[];
  validationStatus: SimulationSnapshot['cube_validation_status'];
}> = ({ observed, predicted, validationStatus }) => {
  const [viewTab, setViewTab] = useState<'OBSERVED' | 'PREDICTED' | 'COMPARISON'>('OBSERVED');

  const stats = useMemo(() => {
    let observedCount = 0;
    let unknownCount = 0;
    let conflictCount = 0;
    let mismatchCount = 0;
    observed.forEach((cell, idx) => {
      if (cell.color === 'UNKNOWN') {
        unknownCount++;
      } else {
        observedCount++;
        const pred = predicted[idx];
        if (pred && pred !== 'UNKNOWN' && pred !== cell.color) {
          mismatchCount++;
        }
      }
      if (cell.hasConflict) conflictCount++;
    });
    return { observedCount, unknownCount, conflictCount, mismatchCount };
  }, [observed, predicted]);

  const netLayout: Array<{ face: FaceId; row: number; col: number }> = [
    { face: 'U', row: 0, col: 1 },
    { face: 'L', row: 1, col: 0 },
    { face: 'F', row: 1, col: 1 },
    { face: 'R', row: 1, col: 2 },
    { face: 'B', row: 1, col: 3 },
    { face: 'D', row: 2, col: 1 },
  ];

  const renderFace = (face: FaceId) => {
    const baseIdx = FACE_ORDER.indexOf(face) * 9;
    return (
      <div key={face} className="grid grid-cols-3 gap-[1.5px] p-[2px] rounded bg-[#080D16] border border-slate-800">
        {Array.from({ length: 9 }).map((_, localIdx) => {
          const globalIdx = baseIdx + localIdx;
          const obs = observed[globalIdx] || { color: 'UNKNOWN' as FaceletColor };
          const pred = predicted[globalIdx] || 'UNKNOWN';
          let displayColor: FaceletColor = 'UNKNOWN';
          let isMismatch = false;

          if (viewTab === 'OBSERVED') {
            displayColor = obs.color;
          } else if (viewTab === 'PREDICTED') {
            displayColor = pred;
          } else {
            if (obs.color === 'UNKNOWN') {
              displayColor = 'UNKNOWN';
            } else {
              displayColor = obs.color;
              isMismatch = pred !== 'UNKNOWN' && pred !== obs.color;
            }
          }

          const style = COLOR_MAP[displayColor];
          return (
            <div
              key={localIdx}
              title={`${face}${localIdx} | 实测:${obs.color} | 预测:${pred}`}
              style={{
                backgroundColor: style.bg,
                borderColor: isMismatch ? '#FF667B' : style.border,
                color: style.text,
              }}
              className="w-3.5 h-3.5 rounded-[1.5px] border flex items-center justify-center text-[8px] font-mono font-bold leading-none"
            >
              {displayColor === 'UNKNOWN' ? '?' : localIdx === 4 ? face : ''}
            </div>
          );
        })}
      </div>
    );
  };

  return (
    <div className="bg-[#101827] border border-slate-800/90 rounded-lg p-2.5 flex flex-col justify-between h-full min-h-0">
      <div className="flex items-center justify-between gap-1.5 shrink-0">
        <div className="flex items-center gap-1.5 min-w-0">
          <Grid className="w-3.5 h-3.5 text-[#3DE8E5] shrink-0" />
          <span className="text-[11px] font-semibold tracking-wider text-slate-200 uppercase truncate">
            CUBE STATE · {stats.observedCount}/54
          </span>
        </div>
        <div className="flex rounded bg-[#080D16] p-0.5 border border-slate-800 text-[10px] shrink-0">
          <button
            type="button"
            onClick={() => setViewTab('OBSERVED')}
            className={`px-1.5 py-0.2 rounded ${
              viewTab === 'OBSERVED' ? 'bg-[#548CFF] text-white' : 'text-slate-400'
            }`}
          >
            实测
          </button>
          <button
            type="button"
            onClick={() => setViewTab('PREDICTED')}
            className={`px-1.5 py-0.2 rounded ${
              viewTab === 'PREDICTED' ? 'bg-[#548CFF] text-white' : 'text-slate-400'
            }`}
          >
            预测
          </button>
          <button
            type="button"
            onClick={() => setViewTab('COMPARISON')}
            className={`px-1.5 py-0.2 rounded ${
              viewTab === 'COMPARISON' ? 'bg-[#548CFF] text-white' : 'text-slate-400'
            }`}
          >
            对比
          </button>
        </div>
      </div>

      <div className="flex-1 flex items-center justify-center min-h-0 my-1">
        <div className="grid grid-cols-4 gap-1 items-center justify-items-center">
          {Array.from({ length: 12 }).map((_, cellIdx) => {
            const r = Math.floor(cellIdx / 4);
            const c = cellIdx % 4;
            const slot = netLayout.find((n) => n.row === r && n.col === c);
            if (!slot) return <div key={cellIdx} className="w-11 h-11" />;
            return renderFace(slot.face);
          })}
        </div>
      </div>

      <div className="grid grid-cols-4 gap-1 pt-1 border-t border-slate-800 text-[10px] font-mono shrink-0">
        <div className="bg-[#080D16] px-1.5 py-0.5 rounded flex justify-between">
          <span className="text-slate-500">未知</span>
          <span className="text-slate-200">{stats.unknownCount}</span>
        </div>
        <div className="bg-[#080D16] px-1.5 py-0.5 rounded flex justify-between">
          <span className="text-slate-500">冲突</span>
          <span className={stats.conflictCount > 0 ? 'text-[#FFBF69]' : 'text-slate-200'}>
            {stats.conflictCount}
          </span>
        </div>
        <div className="bg-[#080D16] px-1.5 py-0.5 rounded flex justify-between">
          <span className="text-slate-500">偏差</span>
          <span className={stats.mismatchCount > 0 ? 'text-[#FF667B]' : 'text-slate-200'}>
            {stats.mismatchCount}
          </span>
        </div>
        <div className="bg-[#080D16] px-1.5 py-0.5 rounded flex justify-between">
          <span className="text-slate-500">校验</span>
          <span className={validationStatus === 'VALID_SOLVABLE' ? 'text-[#30D6A0]' : 'text-slate-300'}>
            {validationStatus === 'VALID_SOLVABLE' ? '通过' : validationStatus === 'INCOMPLETE' ? '未全' : '待检'}
          </span>
        </div>
      </div>
    </div>
  );
};

const CompactTelemetryCard: React.FC<{ telemetry: RobotTelemetry }> = ({ telemetry: t }) => {
  return (
    <div className="bg-[#101827] border border-slate-800/90 rounded-lg p-2.5 flex flex-col justify-between h-full min-h-0">
      <div className="flex items-center justify-between gap-1.5 mb-1.5 shrink-0">
        <div className="flex items-center gap-1.5">
          <Activity className="w-3.5 h-3.5 text-[#3DE8E5]" />
          <span className="text-[11px] font-semibold tracking-wider text-slate-200 uppercase">
            ROBOT TELEMETRY · 遥测监控
          </span>
        </div>
        <span className="text-[10px] font-mono text-slate-500">mjData</span>
      </div>

      <div className="flex-1 grid grid-cols-2 gap-1.5 text-[11px] min-h-0">
        <div className="bg-[#080D16] border border-slate-800/80 rounded px-2 py-1 flex flex-col justify-center">
          <span className="text-[10px] text-slate-400">接触力</span>
          <span className="font-mono font-semibold text-slate-100">
            {t.contactForceN !== null ? `${t.contactForceN.toFixed(2)} N` : '--'}
          </span>
        </div>

        <div className="bg-[#080D16] border border-slate-800/80 rounded px-2 py-1 flex flex-col justify-center">
          <span className="text-[10px] text-slate-400">夹爪状态</span>
          <span className="font-mono font-semibold text-slate-100 truncate">
            {t.gripperWidthMm !== null ? `${t.gripperWidthMm.toFixed(1)} mm` : '--'}{' '}
            <span className="text-[9px] text-[#30D6A0]">({t.gripperState})</span>
          </span>
        </div>

        <div className="bg-[#080D16] border border-slate-800/80 rounded px-2 py-1 flex flex-col justify-center">
          <span className="text-[10px] text-slate-400">实际层转角</span>
          <span className="font-mono font-semibold text-[#3DE8E5]">
            {t.layerTurnAngleDeg !== null ? `${t.targetLayer || 'U'}: ${t.layerTurnAngleDeg.toFixed(1)}°` : '--'}
          </span>
        </div>

        <div className="bg-[#080D16] border border-slate-800/80 rounded px-2 py-1 flex flex-col justify-center">
          <span className="text-[10px] text-slate-400">碰撞与滑移</span>
          <span className="font-mono font-semibold">
            {t.collisionDetected === null ? (
              <span className="text-slate-400">--</span>
            ) : t.collisionDetected || t.slipDetected ? (
              <span className="text-[#FF667B]">异常告警</span>
            ) : (
              <span className="text-[#30D6A0]">正常 (无滑移)</span>
            )}
          </span>
        </div>

        <div className="col-span-2 bg-[#080D16] border border-slate-800/80 rounded px-2 py-1 flex items-center justify-between gap-2">
          <span className="text-[10px] text-slate-400 shrink-0">物体坐标 & 关节</span>
          <span className="font-mono text-[10px] text-slate-200 truncate">
            {t.cubePositionMm
              ? `XYZ[${t.cubePositionMm.map((v) => v.toFixed(1)).join(',')}] · u:${
                  t.jointPositionsRad?.u_layer ?? '--'
                }rad`
              : '--'}
          </span>
        </div>
      </div>
    </div>
  );
};

// ============================================================================
// 8. 能力边界与系统设置页
// ============================================================================

const CapabilityAndSettingsView: React.FC<{
  wsUrl: string;
  onWsUrlChange: (v: string) => void;
  seedInput: number;
  onSeedChange: (v: number) => void;
  capabilities: CapabilityRegistrySnapshot | null | undefined;
  commandLog: string[];
}> = ({ wsUrl, onWsUrlChange, seedInput, onSeedChange, capabilities, commandLog }) => {
  return (
    <main className="flex-1 overflow-y-auto p-4 max-w-5xl mx-auto w-full space-y-3.5 text-xs">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3.5">
        <div className="bg-[#101827] border border-slate-800 rounded-lg p-4 space-y-3">
          <div className="flex items-center gap-2 border-b border-slate-800 pb-2">
            <Settings className="w-4 h-4 text-[#3DE8E5]" />
            <h2 className="font-semibold text-slate-100">系统设置与后端 SimulationSession 端点</h2>
          </div>
          <div>
            <label className="block text-slate-400 mb-1">WebSocket 地址</label>
            <input
              type="text"
              value={wsUrl}
              onChange={(e) => onWsUrlChange(e.target.value)}
              className="w-full px-3 py-1.5 rounded bg-[#080D16] border border-slate-700 font-mono text-slate-200"
            />
          </div>
          <div>
            <label className="block text-slate-400 mb-1">默认实验随机种子 (Seed)</label>
            <input
              type="number"
              value={seedInput}
              onChange={(e) => onSeedChange(Number(e.target.value) || 0)}
              className="w-32 px-3 py-1.5 rounded bg-[#080D16] border border-slate-700 font-mono text-slate-200"
            />
          </div>
          <div>
            <div className="text-slate-400 mb-1">控制台操作审计日志</div>
            <div className="h-44 overflow-y-auto p-2.5 rounded bg-[#080D16] border border-slate-800 font-mono text-[11px] text-slate-300 space-y-1">
              {commandLog.map((line, i) => (
                <div key={i}>{line}</div>
              ))}
            </div>
          </div>
        </div>

        <div className="bg-[#101827] border border-slate-800 rounded-lg p-4 space-y-2.5">
          <div className="flex items-center justify-between border-b border-slate-800 pb-2">
            <div className="flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-[#30D6A0]" />
              <h2 className="font-semibold text-slate-100">Skill Registry 物理能力边界</h2>
            </div>
            <FileCode2 className="w-4 h-4 text-[#548CFF]" />
          </div>
          {capabilities ? (
            <>
              <div className="p-2 rounded bg-[#080D16] border border-slate-800 text-[11px] text-slate-300">
                {capabilities.physical_limitations_summary}
              </div>
              <div className="space-y-1.5 max-h-60 overflow-y-auto">
                {capabilities.skills.map((sk) => (
                  <div key={sk.skill_id} className="p-2 rounded bg-[#080D16] border border-slate-800 space-y-0.5">
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-[#3DE8E5]">{sk.skill_id}</span>
                      <span
                        className={`px-1.5 py-0.2 rounded text-[10px] font-mono ${
                          sk.implemented ? 'bg-[#30D6A0]/15 text-[#30D6A0]' : 'bg-[#FFBF69]/15 text-[#FFBF69]'
                        }`}
                      >
                        {sk.implemented ? 'IMPLEMENTED' : 'UNIMPLEMENTED'}
                      </span>
                    </div>
                    <div className="text-[10.5px] text-slate-400">{sk.description}</div>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <div className="text-slate-500">连接 LIVE 后端后显示动态注册的 SkillRegistry。</div>
          )}
        </div>
      </div>
    </main>
  );
};

// ============================================================================
// 8.5 Task Agent 能力评估视图 (M4-D Benchmark: Replay / Ablation / MuJoCo)
// ============================================================================

interface M4DMetricValue {
  value: number | null;
  numerator: number;
  denominator: number;
  formula: string;
  ci_95_low?: number | null;
  ci_95_high?: number | null;
  notes?: string | null;
}

interface M4DDimensionSummary {
  dimension: string;
  total_samples: number;
  passed_count: number;
  failed_count: number;
  requires_review_count: number;
  incomparable_count: number;
  not_run_count: number;
  pass_rate: M4DMetricValue;
  attribution_counts: Record<string, number>;
}

interface M4DScorecard {
  group_label: string;
  planner_group: string;
  guide_mode: string;
  execution_source_label: string;
  is_fake_provider: boolean;
  included_in_real_agent_ranking: boolean;
  sample_count: number;
  decision_metrics: Record<string, M4DMetricValue>;
  perception_metrics: Record<string, M4DMetricValue>;
  recovery_metrics: Record<string, M4DMetricValue>;
  closed_loop_metrics: Record<string, M4DMetricValue>;
  per_dimension: Record<string, M4DDimensionSummary>;
  failure_attribution_counts: Record<string, number>;
  latency_summary_ms: Record<string, number | null>;
  token_summary: Record<string, number>;
  notes: string[];
}

interface M4DDecisionRecord {
  record_id: string;
  benchmark_case_id: string;
  capability_dimension: string;
  source_type: string;
  planner_group: string;
  planner_mode: string;
  model_name?: string | null;
  model_provider?: string | null;
  is_fake_provider: boolean;
  is_online_model: boolean;
  execution_source_labels: string[];
  guide_mode: string;
  vlm_ablation_condition?: string | null;
  prompt_sha256?: string | null;
  redacted_prompt_summary?: string | null;
  observation_id?: string | null;
  semantic_observation_id?: string | null;
  decision_kind: string;
  selected_action?: string | null;
  selected_skill?: string | null;
  normalized_action?: string | null;
  parameters: Record<string, unknown>;
  reason_summary: string;
  evidence_references: string[];
  safety_validation: {
    passed: boolean;
    safety_gate_status: string;
    reason: string;
  };
  oracle_result: {
    verdict: string;
    legal_action: boolean;
    evidence_grounded: boolean;
    decision_appropriate: boolean;
    forbidden_violation?: string | null;
    notes: string[];
  };
  failure_attribution: {
    primary_category: string;
    secondary_categories: string[];
    explanation: string;
  };
  latency_ms: number;
  token_usage: { input_tokens?: number; output_tokens?: number; total_tokens?: number };
  model_call_status: string;
  incomparable_reason?: string | null;
}

interface M4DClosedLoopEpisode {
  episode_id: string;
  scenario_id: string;
  mission_type: string;
  planner_group: string;
  guide_mode: string;
  is_fake_provider: boolean;
  is_online_model: boolean;
  execution_source_labels: string[];
  seed: number;
  mission_status: string;
  goal_achieved: boolean;
  failure_reason?: string | null;
  failure_attribution: { primary_category: string; explanation: string };
  skills_executed: string[];
  sim_time_s: number;
  wall_time_s: number;
  run_id?: string | null;
}

interface M4DBenchmarkResult {
  benchmark_run_id: string;
  benchmark_version: string;
  generated_utc: string;
  execution_mode: string;
  contains_fake_provider: boolean;
  decision_records: M4DDecisionRecord[];
  vlm_ablation_records: M4DDecisionRecord[];
  guide_ablation_records: M4DDecisionRecord[];
  closed_loop_episodes: M4DClosedLoopEpisode[];
  real_scorecards: Record<string, M4DScorecard>;
  fake_validation_scorecards: Record<string, M4DScorecard>;
  vlm_ablation_summary?: {
    by_condition?: Record<string, { n: number; comparable_n: number; passed: number; accuracy?: M4DMetricValue; forbidden_rate?: M4DMetricValue; evidence_grounding_rate?: M4DMetricValue }>;
    case_matrix?: Array<Record<string, unknown>>;
    fake_only?: {
      by_condition?: Record<string, { n: number; comparable_n: number; passed: number; accuracy?: M4DMetricValue; forbidden_rate?: M4DMetricValue; evidence_grounding_rate?: M4DMetricValue }>;
    };
  };
  guide_ablation_summary?: Record<string, { guide_full_n: number; guide_full_acc: number; guide_minimal_n: number; guide_minimal_acc: number; delta_minimal_minus_full: number }>;
  incomparabilities: string[];
}

const DIM_LABELS: Record<string, string> = {
  L1_SKILL_SELECTION: 'L1 Skill Selection',
  L2_STATE_AWARE_PLANNING: 'L2 State-Aware Planning',
  L3_PERCEPTION_GROUNDED_REASONING: 'L3 Perception-Grounded',
  L4_FAILURE_RECOVERY: 'L4 Failure Recovery',
  L5_GENERALIZATION: 'L5 Generalization',
};

const SOURCE_BADGE_STYLES: Record<string, string> = {
  REAL_ONLINE_MODEL: 'bg-[#30D6A0]/15 text-[#30D6A0] border-[#30D6A0]/40',
  REAL_MUJOCO: 'bg-[#548CFF]/15 text-[#548CFF] border-[#548CFF]/40',
  OFFLINE_REPLAY: 'bg-[#3DE8E5]/15 text-[#3DE8E5] border-[#3DE8E5]/40',
  COUNTERFACTUAL_TEST: 'bg-[#FFBF69]/15 text-[#FFBF69] border-[#FFBF69]/40',
  DETERMINISTIC_RULE: 'bg-slate-700/60 text-slate-200 border-slate-600',
  FAKE_PROVIDER: 'bg-[#F05D5E]/20 text-[#F05D5E] border-[#F05D5E]/50',
};

function getVerdictBadgeCls(verdict: string): string {
  if (verdict === 'PASS') return 'px-1.5 py-0.2 rounded shrink-0 bg-[#30D6A0]/20 text-[#30D6A0]';
  if (verdict === 'FAIL') return 'px-1.5 py-0.2 rounded shrink-0 bg-[#F05D5E]/20 text-[#F05D5E]';
  return 'px-1.5 py-0.2 rounded shrink-0 bg-slate-800 text-slate-300';
}

const TaskAgentBenchmarkView: React.FC<{ httpBase: string }> = ({ httpBase }) => {
  const [loading, setLoading] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [apiStatus, setApiStatus] = useState<'OK' | 'NOT_RUN' | 'UNCONNECTED'>('NOT_RUN');
  const [runs, setRuns] = useState<Array<{ benchmark_run_id: string; execution_mode: string; generated_utc: string; contains_fake_provider: boolean; decision_count?: number }>>([]);
  const [selectedRunId, setSelectedRunId] = useState<string>('');
  const [sourceBadge, setSourceBadge] = useState<string>('');
  const [result, setResult] = useState<M4DBenchmarkResult | null>(null);
  const [activeSubTab, setActiveSubTab] = useState<'OVERVIEW' | 'ABLATIONS' | 'TRACES' | 'CLOSED_LOOP'>('OVERVIEW');
  const [traceFilterGroup, setTraceFilterGroup] = useState<string>('ALL');
  const [traceFilterVerdict, setTraceFilterVerdict] = useState<string>('ALL');
  const [traceFilterDim, setTraceFilterDim] = useState<string>('ALL');
  const [selectedRecordId, setSelectedRecordId] = useState<string>('');

  const fetchBenchmark = async (runId?: string) => {
    setLoading(true);
    setErrorMsg(null);
    try {
      const qs = runId ? `?run_id=${encodeURIComponent(runId)}` : '';
      const resp = await fetch(`${httpBase}/api/m4d/benchmark/latest${qs}`);
      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}`);
      }
      const data = await resp.json();
      setRuns(Array.isArray(data.available_runs) ? data.available_runs : []);
      if (data.status === 'OK' && data.result) {
        setApiStatus('OK');
        setSourceBadge(String(data.source_badge || ''));
        setResult(data.result);
        setSelectedRunId(String(data.result.benchmark_run_id || ''));
        if (Array.isArray(data.result.decision_records) && data.result.decision_records.length > 0) {
          setSelectedRecordId(data.result.decision_records[0].record_id);
        }
      } else {
        setApiStatus('NOT_RUN');
        setResult(null);
      }
    } catch (err) {
      setApiStatus('UNCONNECTED');
      setErrorMsg(err instanceof Error ? err.message : '无法加载 Benchmark API');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchBenchmark();
  }, [httpBase]);

  const fmtPct = (m?: M4DMetricValue) => {
    if (!m || m.value === null || m.value === undefined) return 'N/A';
    return `${(m.value * 100).toFixed(1)}% (${m.numerator}/${m.denominator})`;
  };

  const filteredRecords = useMemo(() => {
    if (!result) return [];
    const all = [...(result.decision_records || []), ...(result.guide_ablation_records || [])];
    return all.filter((r) => {
      if (traceFilterGroup !== 'ALL' && r.planner_group !== traceFilterGroup) return false;
      if (traceFilterDim !== 'ALL' && r.capability_dimension !== traceFilterDim) return false;
      if (traceFilterVerdict !== 'ALL' && r.oracle_result.verdict !== traceFilterVerdict) return false;
      return true;
    });
  }, [result, traceFilterGroup, traceFilterVerdict, traceFilterDim]);

  const selectedRecord = useMemo(
    () => filteredRecords.find((r) => r.record_id === selectedRecordId) || filteredRecords[0] || null,
    [filteredRecords, selectedRecordId]
  );

  const realCards = Object.values(result?.real_scorecards || {});
  const fakeCards = Object.values(result?.fake_validation_scorecards || {});
  const allCards = [...realCards, ...fakeCards];
  const abConds = result?.vlm_ablation_summary?.by_condition || result?.vlm_ablation_summary?.fake_only?.by_condition || {};

  return (
    <main className="flex-1 overflow-y-auto bg-[#080D16] p-4 space-y-4 text-xs">
      {/* Top Toolbar */}
      <div className="bg-[#101827] border border-slate-800 rounded-lg p-3 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2.5 flex-wrap">
          <Bot className="w-4 h-4 text-[#3DE8E5]" />
          <h2 className="font-semibold text-sm text-slate-100">M4-D Task Agent 能力基准测试 (Benchmark)</h2>
          {result && (
            <>
              <span className={`px-2 py-0.5 rounded border text-[10px] font-mono ${SOURCE_BADGE_STYLES[sourceBadge] || 'bg-slate-800 text-slate-200 border-slate-700'}`}>
                {sourceBadge || result.execution_mode}
              </span>
              <span className="px-2 py-0.5 rounded bg-slate-800 border border-slate-700 text-[10px] font-mono text-slate-300">
                VERSION: {result.benchmark_version}
              </span>
            </>
          )}
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {runs.length > 0 && (
            <select
              value={selectedRunId}
              onChange={(e) => fetchBenchmark(e.target.value)}
              className="px-2.5 py-1 rounded bg-[#080D16] border border-slate-700 text-[11px] font-mono text-slate-200"
            >
              {runs.map((r) => (
                <option key={r.benchmark_run_id} value={r.benchmark_run_id}>
                  {r.benchmark_run_id} ({r.execution_mode} | D={r.decision_count})
                </option>
              ))}
            </select>
          )}
          <button
            onClick={() => fetchBenchmark(selectedRunId || undefined)}
            disabled={loading}
            className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 flex items-center gap-1"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} /> 刷新
          </button>
          {result && (
            <a
              href={`${httpBase}/api/m4d/benchmark/export?run_id=${encodeURIComponent(result.benchmark_run_id)}`}
              className="px-2.5 py-1 rounded bg-[#548CFF]/20 hover:bg-[#548CFF]/30 border border-[#548CFF]/40 text-[#548CFF] flex items-center gap-1"
            >
              <Download className="w-3.5 h-3.5" /> 导出 Benchmark ZIP
            </a>
          )}
        </div>
      </div>

      {/* Warning banner for Fake Provider */}
      {result?.contains_fake_provider && (
        <div className="p-2.5 rounded bg-[#F05D5E]/15 border border-[#F05D5E]/40 text-[#F05D5E] flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          <span>
            当前 Run 包含 <code className="font-mono font-semibold">FAKE_PROVIDER</code> 验证数据：Fake Provider 仅用于验证测试管线，已严格隔离到
            <code className="font-mono"> fake_validation_scorecards</code>，<strong>绝不计入真实 LLM Agent 能力评分</strong>。
          </span>
        </div>
      )}

      {apiStatus === 'NOT_RUN' && (
        <div className="bg-[#101827] border border-slate-800 rounded-lg p-6 text-center space-y-2">
          <div className="text-sm font-semibold text-slate-200">尚未检测到已保存的 M4-D Benchmark 结果 (NOT_RUN)</div>
          <div className="text-slate-400">
            请运行 <code className="font-mono text-[#3DE8E5]">python scripts/run_m4d_benchmark.py --mode online_real --run-vlm-ablation --run-guide-ablation --closed-loop</code> 后点击刷新。
          </div>
        </div>
      )}

      {apiStatus === 'UNCONNECTED' && (
        <div className="bg-[#101827] border border-[#F05D5E]/40 rounded-lg p-4 text-[#F05D5E]">
          无法读取 Benchmark 接口 ({httpBase}/api/m4d/benchmark/latest): {errorMsg}
        </div>
      )}

      {result && (
        <>
          {/* Sub-tabs */}
          <div className="flex items-center gap-1 border-b border-slate-800 pb-2">
            {(
              [
                { id: 'OVERVIEW', label: '五维能力榜单 & 对照组' },
                { id: 'ABLATIONS', label: 'VLM 因果消融 & Guide 消融' },
                { id: 'CLOSED_LOOP', label: `MuJoCo 闭环评估 (${result.closed_loop_episodes.length})` },
                { id: 'TRACES', label: `错误案例与 Decision Trace (${result.decision_records.length})` },
              ] as const
            ).map((t) => (
              <button
                key={t.id}
                onClick={() => setActiveSubTab(t.id)}
                className={`px-3 py-1 rounded text-[11px] font-medium transition-colors ${
                  activeSubTab === t.id
                    ? 'bg-[#3DE8E5]/15 text-[#3DE8E5] border border-[#3DE8E5]/40'
                    : 'text-slate-400 hover:text-slate-200 bg-[#101827] border border-slate-800'
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>

          {activeSubTab === 'OVERVIEW' && (
            <div className="space-y-4">
              {/* Group Comparison Table */}
              <div className="bg-[#101827] border border-slate-800 rounded-lg p-3 overflow-x-auto">
                <h3 className="font-semibold text-slate-200 mb-2">对照组能力指标（L1-L5 独立评分，严禁合并为单一分数）</h3>
                <table className="w-full text-left border-collapse font-mono text-[11px]">
                  <thead>
                    <tr className="border-b border-slate-800 text-slate-400">
                      <th className="py-1.5 pr-3">Planner Group / Guide</th>
                      <th className="py-1.5 pr-3">数据来源</th>
                      <th className="py-1.5 pr-3">Legal</th>
                      <th className="py-1.5 pr-3">Schema</th>
                      <th className="py-1.5 pr-3">Appropriate</th>
                      <th className="py-1.5 pr-3">Forbidden</th>
                      <th className="py-1.5 pr-3">Evidence</th>
                      <th className="py-1.5 pr-3">Mean(ms)</th>
                      <th className="py-1.5">Tokens</th>
                    </tr>
                  </thead>
                  <tbody>
                    {allCards.map((sc) => (
                      <tr key={sc.group_label} className="border-b border-slate-800/60 hover:bg-slate-800/30">
                        <td className="py-1.5 pr-3 text-slate-100">
                          {sc.group_label}
                          {!sc.included_in_real_agent_ranking && (
                            <span className="ml-1.5 px-1 py-0.2 rounded bg-[#F05D5E]/20 text-[#F05D5E] text-[9px]">EXCLUDED_FAKE</span>
                          )}
                        </td>
                        <td className="py-1.5 pr-3">
                          <span className={`px-1.5 py-0.5 rounded border text-[9.5px] ${SOURCE_BADGE_STYLES[sc.execution_source_label] || ''}`}>
                            {sc.execution_source_label}
                          </span>
                        </td>
                        <td className="py-1.5 pr-3">{fmtPct(sc.decision_metrics.legal_action_rate)}</td>
                        <td className="py-1.5 pr-3">{fmtPct(sc.decision_metrics.schema_validity_rate)}</td>
                        <td className="py-1.5 pr-3 font-semibold text-[#3DE8E5]">{fmtPct(sc.decision_metrics.decision_appropriateness_rate)}</td>
                        <td className="py-1.5 pr-3 text-[#F05D5E]">{fmtPct(sc.decision_metrics.forbidden_action_rate)}</td>
                        <td className="py-1.5 pr-3">{fmtPct(sc.decision_metrics.evidence_grounding_rate)}</td>
                        <td className="py-1.5 pr-3">{sc.latency_summary_ms?.mean_ms ?? 'N/A'}</td>
                        <td className="py-1.5">{sc.token_summary?.total_tokens ?? 0}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Per-Dimension Cards + Attribution */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {allCards.map((sc) => (
                  <div key={sc.group_label} className="bg-[#101827] border border-slate-800 rounded-lg p-3 space-y-2.5">
                    <div className="flex items-center justify-between border-b border-slate-800 pb-1.5">
                      <span className="font-mono font-semibold text-slate-100">{sc.group_label}</span>
                      <span className={`px-1.5 py-0.5 rounded border text-[9.5px] font-mono ${SOURCE_BADGE_STYLES[sc.execution_source_label] || ''}`}>
                        {sc.execution_source_label}
                      </span>
                    </div>
                    <div className="space-y-1.5">
                      {Object.entries(sc.per_dimension || {}).map(([dim, ds]) => {
                        const pct = ds.pass_rate.value !== null ? Math.round(ds.pass_rate.value * 100) : 0;
                        return (
                          <div key={dim} className="space-y-0.5">
                            <div className="flex justify-between text-[10.5px] font-mono">
                              <span className="text-slate-300">{DIM_LABELS[dim] || dim}</span>
                              <span className="text-slate-200">
                                {ds.pass_rate.value !== null ? `${pct}% (${ds.passed_count}/${ds.pass_rate.denominator})` : 'N/A'}
                                {ds.incomparable_count > 0 ? ` [INCOMP:${ds.incomparable_count}]` : ''}
                              </span>
                            </div>
                            <div className="h-1.5 bg-slate-800 rounded overflow-hidden">
                              <div
                                className={`h-full ${sc.is_fake_provider ? 'bg-[#F05D5E]' : 'bg-[#3DE8E5]'}`}
                                style={{ width: `${pct}%` }}
                              />
                            </div>
                          </div>
                        );
                      })}
                    </div>
                    <div className="pt-1 border-t border-slate-800/70 flex flex-wrap gap-1.5 text-[10px] font-mono">
                      {Object.entries(sc.failure_attribution_counts || {}).map(([cat, cnt]) => (
                        <span key={cat} className="px-1.5 py-0.5 rounded bg-[#080D16] border border-slate-800 text-slate-300">
                          {cat}: {cnt}
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {activeSubTab === 'ABLATIONS' && (
            <div className="space-y-4">
              {/* VLM Ablation Table */}
              <div className="bg-[#101827] border border-slate-800 rounded-lg p-3 space-y-2">
                <h3 className="font-semibold text-slate-200">L3 VLM 语义因果消融 (VLM_TRUE vs ABSENT / SWAPPED / CONTRADICTORY / LOW_CONFIDENCE)</h3>
                {Object.keys(abConds).length === 0 ? (
                  <div className="text-slate-500">当前 Run 未包含 L3 VLM 消融记录。</div>
                ) : (
                  <table className="w-full text-left border-collapse font-mono text-[11px]">
                    <thead>
                      <tr className="border-b border-slate-800 text-slate-400">
                        <th className="py-1.5 pr-3">Condition</th>
                        <th className="py-1.5 pr-3">N (Comparable)</th>
                        <th className="py-1.5 pr-3">Pass</th>
                        <th className="py-1.5 pr-3">Accuracy</th>
                        <th className="py-1.5 pr-3">Forbidden Rate</th>
                        <th className="py-1.5">Evidence Grounding</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(abConds).map(([cond, st]) => (
                        <tr key={cond} className="border-b border-slate-800/60">
                          <td className="py-1.5 pr-3 text-[#3DE8E5]">{cond}</td>
                          <td className="py-1.5 pr-3">{st.comparable_n} / {st.n}</td>
                          <td className="py-1.5 pr-3">{st.passed}</td>
                          <td className="py-1.5 pr-3">{fmtPct(st.accuracy)}</td>
                          <td className="py-1.5 pr-3 text-[#F05D5E]">{fmtPct(st.forbidden_rate)}</td>
                          <td className="py-1.5">{fmtPct(st.evidence_grounding_rate)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>

              {/* Guide Ablation Table */}
              <div className="bg-[#101827] border border-slate-800 rounded-lg p-3 space-y-2">
                <h3 className="font-semibold text-slate-200">Prompt Guide 消融 (GUIDE_FULL vs GUIDE_MINIMAL)</h3>
                {!result.guide_ablation_summary || Object.keys(result.guide_ablation_summary).length === 0 ? (
                  <div className="text-slate-500">当前 Run 未包含 Prompt Guide 消融对照。</div>
                ) : (
                  <table className="w-full text-left border-collapse font-mono text-[11px]">
                    <thead>
                      <tr className="border-b border-slate-800 text-slate-400">
                        <th className="py-1.5 pr-3">Planner Group</th>
                        <th className="py-1.5 pr-3">GUIDE_FULL Acc (N)</th>
                        <th className="py-1.5 pr-3">GUIDE_MINIMAL Acc (N)</th>
                        <th className="py-1.5">Delta (MIN - FULL)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(result.guide_ablation_summary).map(([grp, st]) => (
                        <tr key={grp} className="border-b border-slate-800/60">
                          <td className="py-1.5 pr-3 text-slate-100">{grp}</td>
                          <td className="py-1.5 pr-3">{(st.guide_full_acc * 100).toFixed(1)}% ({st.guide_full_n})</td>
                          <td className="py-1.5 pr-3">{(st.guide_minimal_acc * 100).toFixed(1)}% ({st.guide_minimal_n})</td>
                          <td className="py-1.5 text-[#3DE8E5]">{(st.delta_minimal_minus_full * 100 >= 0 ? '+' : '')}{(st.delta_minimal_minus_full * 100).toFixed(1)}%</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </div>
          )}

          {activeSubTab === 'CLOSED_LOOP' && (
            <div className="bg-[#101827] border border-slate-800 rounded-lg p-3 space-y-2 overflow-x-auto">
              <h3 className="font-semibold text-slate-200">Layer B 真实 MuJoCo 闭环评估 Episodes (区分 Agent 决策与物理 Skill 成败)</h3>
              {result.closed_loop_episodes.length === 0 ? (
                <div className="text-slate-500">当前 Run 未包含 Closed-Loop MuJoCo Episodes。</div>
              ) : (
                <table className="w-full text-left border-collapse font-mono text-[11px]">
                  <thead>
                    <tr className="border-b border-slate-800 text-slate-400">
                      <th className="py-1.5 pr-3">Scenario</th>
                      <th className="py-1.5 pr-3">Group</th>
                      <th className="py-1.5 pr-3">Sources</th>
                      <th className="py-1.5 pr-3">Status</th>
                      <th className="py-1.5 pr-3">Goal</th>
                      <th className="py-1.5 pr-3">Attribution</th>
                      <th className="py-1.5 pr-3">Skills Executed</th>
                      <th className="py-1.5">Wall(s)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.closed_loop_episodes.map((ep) => (
                      <tr key={ep.episode_id} className="border-b border-slate-800/60">
                        <td className="py-1.5 pr-3 text-slate-100">{ep.scenario_id}</td>
                        <td className="py-1.5 pr-3">{ep.planner_group}</td>
                        <td className="py-1.5 pr-3">
                          <div className="flex gap-1 flex-wrap">
                            {ep.execution_source_labels.map((lb) => (
                              <span key={lb} className={`px-1 py-0.2 rounded border text-[9px] ${SOURCE_BADGE_STYLES[lb] || ''}`}>{lb}</span>
                            ))}
                          </div>
                        </td>
                        <td className="py-1.5 pr-3">{ep.mission_status}</td>
                        <td className={`py-1.5 pr-3 ${ep.goal_achieved ? 'text-[#30D6A0]' : 'text-[#F05D5E]'}`}>
                          {String(ep.goal_achieved)}
                        </td>
                        <td className="py-1.5 pr-3">{ep.failure_attribution.primary_category}</td>
                        <td className="py-1.5 pr-3 text-slate-300">{ep.skills_executed.join(' -> ')}</td>
                        <td className="py-1.5">{ep.wall_time_s.toFixed(2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}

          {activeSubTab === 'TRACES' && (
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-3">
              <div className="lg:col-span-7 bg-[#101827] border border-slate-800 rounded-lg p-3 space-y-2">
                <div className="flex flex-wrap gap-2 items-center justify-between">
                  <h3 className="font-semibold text-slate-200">决策记录与失败案例过滤 ({filteredRecords.length})</h3>
                  <div className="flex flex-wrap gap-1.5 font-mono text-[10.5px]">
                    <select value={traceFilterGroup} onChange={(e) => setTraceFilterGroup(e.target.value)} className="px-2 py-0.5 rounded bg-[#080D16] border border-slate-700 text-slate-200">
                      <option value="ALL">All Groups</option>
                      <option value="DETERMINISTIC_BASELINE">DETERMINISTIC</option>
                      <option value="LLM_AGENT_CV_ONLY">LLM_CV_ONLY</option>
                      <option value="LLM_AGENT_CV_VLM">LLM_CV_VLM</option>
                      <option value="SINGLE_MODEL_BASELINE">SINGLE_MODEL</option>
                    </select>
                    <select value={traceFilterDim} onChange={(e) => setTraceFilterDim(e.target.value)} className="px-2 py-0.5 rounded bg-[#080D16] border border-slate-700 text-slate-200">
                      <option value="ALL">All Dimensions</option>
                      {Object.keys(DIM_LABELS).map((d) => (
                        <option key={d} value={d}>{d}</option>
                      ))}
                    </select>
                    <select value={traceFilterVerdict} onChange={(e) => setTraceFilterVerdict(e.target.value)} className="px-2 py-0.5 rounded bg-[#080D16] border border-slate-700 text-slate-200">
                      <option value="ALL">All Verdicts</option>
                      <option value="FAIL">FAIL Only</option>
                      <option value="PASS">PASS Only</option>
                      <option value="INCOMPARABLE">INCOMPARABLE</option>
                    </select>
                  </div>
                </div>
                <div className="max-h-96 overflow-y-auto space-y-1 font-mono text-[10.5px]">
                  {filteredRecords.map((r) => (
                    <button
                      key={r.record_id}
                      onClick={() => setSelectedRecordId(r.record_id)}
                      className={`w-full text-left p-2 rounded border flex items-center justify-between gap-2 ${
                        selectedRecord?.record_id === r.record_id
                          ? 'bg-[#3DE8E5]/10 border-[#3DE8E5]/50'
                          : 'bg-[#080D16] border-slate-800 hover:border-slate-700'
                      }`}
                    >
                      <div className="truncate">
                        <span className="text-slate-100">{r.benchmark_case_id}</span>{' '}
                        <span className="text-slate-400">[{r.planner_group} / {r.guide_mode}]</span>{' '}
                        <span className="text-[#3DE8E5]">-&gt; {r.normalized_action}</span>
                      </div>
                      <span className={getVerdictBadgeCls(r.oracle_result.verdict)}>
                        {r.oracle_result.verdict}
                      </span>
                    </button>
                  ))}
                </div>
              </div>

              <div className="lg:col-span-5 bg-[#101827] border border-slate-800 rounded-lg p-3 space-y-2 font-mono text-[10.5px]">
                <h3 className="font-sans font-semibold text-xs text-slate-200">Decision Trace 详情</h3>
                {selectedRecord ? (
                  <div className="space-y-2">
                    <div className="flex flex-wrap gap-1">
                      {selectedRecord.execution_source_labels.map((lb) => (
                        <span key={lb} className={`px-1.5 py-0.5 rounded border text-[9.5px] ${SOURCE_BADGE_STYLES[lb] || ''}`}>{lb}</span>
                      ))}
                    </div>
                    <div className="p-2 rounded bg-[#080D16] border border-slate-800 space-y-1 text-slate-300">
                      <div>Case: <span className="text-slate-100">{selectedRecord.benchmark_case_id}</span> ({selectedRecord.source_type})</div>
                      <div>Action: <span className="text-[#3DE8E5]">{selectedRecord.normalized_action}</span> params={JSON.stringify(selectedRecord.parameters)}</div>
                      <div>Model: {selectedRecord.model_name} | Latency: {selectedRecord.latency_ms}ms | Call: {selectedRecord.model_call_status}</div>
                      <div>Evidence Refs: {JSON.stringify(selectedRecord.evidence_references)}</div>
                      <div>Safety Gate: {selectedRecord.safety_validation.safety_gate_status} ({selectedRecord.safety_validation.reason})</div>
                      <div>Oracle Verdict: <span className={selectedRecord.oracle_result.verdict === 'PASS' ? 'text-[#30D6A0]' : 'text-[#F05D5E]'}>{selectedRecord.oracle_result.verdict}</span> | Attribution: {selectedRecord.failure_attribution.primary_category}</div>
                    </div>
                    <div className="p-2 rounded bg-[#080D16] border border-slate-800 text-slate-300 font-sans">
                      <div className="text-slate-400 text-[10px] mb-0.5">Reason Summary & Oracle Notes</div>
                      <div>{selectedRecord.reason_summary || '—'}</div>
                      {selectedRecord.oracle_result.notes.length > 0 && (
                        <div className="mt-1 text-[#FFBF69] font-mono text-[10px]">{selectedRecord.oracle_result.notes.join('; ')}</div>
                      )}
                    </div>
                    {selectedRecord.prompt_sha256 && (
                      <div className="text-[10px] text-slate-500 truncate">
                        prompt_sha256: {selectedRecord.prompt_sha256}
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="text-slate-500">选择一条记录查看详细 Trace。</div>
                )}
              </div>
            </div>
          )}
        </>
      )}
    </main>
  );
};

// ============================================================================
// 9. 主控制台应用 (CubeRelay M3-D 单屏 3:1 紧凑控制中心)
// ============================================================================

function getDefaultWsUrl(): string {
  if (typeof window !== 'undefined' && window.location.protocol.startsWith('http')) {
    const wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const base = window.location.pathname === '/cube-relay' || window.location.pathname.startsWith('/cube-relay/')
      ? '/cube-relay'
      : '';
    return `${wsProto}//${window.location.host}${base}/ws/session`;
  }
  return 'ws://127.0.0.1:8765/ws/session';
}

function getDefaultRuntimeMode(): RuntimeMode {
  if (typeof window !== 'undefined' && window.location.protocol.startsWith('http')) {
    return 'LIVE';
  }
  return 'SAMPLE';
}

export default function App() {
  const [activeNav, setActiveNav] = useState<'CONSOLE' | 'SETTINGS' | 'BENCHMARK'>('CONSOLE');
  const [mode, setMode] = useState<RuntimeMode>(() => getDefaultRuntimeMode());
  const [wsUrl, setWsUrl] = useState<string>(() => getDefaultWsUrl());
  const [wsConnected, setWsConnected] = useState<boolean>(false);
  const [seedInput, setSeedInput] = useState<number>(0);
  const [selectedMission, setSelectedMission] = useState<MissionType>('RELAY_SOLVE_CUBE');
  const [selectedScrambleSteps, setSelectedScrambleSteps] = useState<number | 'random'>(5);
  const [techDrawerOpen, setTechDrawerOpen] = useState<boolean>(false);

  const [snapshot, setSnapshot] = useState<SimulationSnapshot>(() =>
    getDefaultRuntimeMode() === 'LIVE'
      ? createDisconnectedLiveSnapshot(0, 'RELAY_SOLVE_CUBE')
      : createSampleSnapshot('RELAY_SOLVE_CUBE', SAMPLE_TIMELINE[3])
  );
  const [selectedEventId, setSelectedEventId] = useState<string>('ev-4');
  const [commandLog, setCommandLog] = useState<string[]>(['[INIT] CubeRelay M3-D 控制台已初始化']);

  const [debugOverlays, setDebugOverlays] = useState({
    contactForces: true,
    collisionGeoms: false,
    tcpFrame: true,
    hudVisible: true,
  });

  const [previewScreenshotUrl, setPreviewScreenshotUrl] = useState<string | null>(null);
  const replayVideoRef = useRef<HTMLVideoElement>(null);
  const [replayVideoUrl, setReplayVideoUrl] = useState<string | null>(null);
  const [replayTiming, setReplayTiming] = useState<ReplayTimingFile | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const [startModalOpen, setStartModalOpen] = useState<boolean>(false);
  const [startModalPassword, setStartModalPassword] = useState<string>('');
  const [startModalError, setStartModalError] = useState<string | null>(null);
  const [startModalSubmitting, setStartModalSubmitting] = useState<boolean>(false);
  const [exportModalOpen, setExportModalOpen] = useState<boolean>(false);
  const [exportScope, setExportScope] = useState<'full_mission' | 'grasp_causal_chain' | 'events_only'>('full_mission');
  const [exportIncludeRgbd, setExportIncludeRgbd] = useState<boolean>(true);
  const [exportIncludeHighFreq, setExportIncludeHighFreq] = useState<boolean>(true);
  const [exportIncludeAuditTruth, setExportIncludeAuditTruth] = useState<boolean>(false);
  const [exportSelectedRunId, setExportSelectedRunId] = useState<string>('');
  const [exportRuns, setExportRuns] = useState<HistoricalRunSummary[]>([]);
  const [exportSubmitting, setExportSubmitting] = useState<boolean>(false);
  const [exportStatusMsg, setExportStatusMsg] = useState<string | null>(null);
  const [exportErrorMsg, setExportErrorMsg] = useState<string | null>(null);
  const startPasswordInputRef = useRef<HTMLInputElement>(null);

  const appendLog = (msg: string) => {
    const ts = new Date().toTimeString().slice(0, 8);
    setCommandLog((prev) => [`[${ts}] ${msg}`, ...prev.slice(0, 29)]);
  };

  useEffect(() => {
    if (!startModalOpen) return;
    const focusTimer = window.setTimeout(() => {
      startPasswordInputRef.current?.focus();
    }, 0);
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !startModalSubmitting) {
        setStartModalPassword('');
        setStartModalError(null);
        setStartModalOpen(false);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => {
      window.clearTimeout(focusTimer);
      window.removeEventListener('keydown', onKeyDown);
    };
  }, [startModalOpen, startModalSubmitting]);

  // SAMPLE 模式下，仅更新 SYNTHETIC SAMPLE 帧；LIVE 模式严禁调用合成样本函数
  useEffect(() => {
    if (mode !== 'SAMPLE') return;
    const url = generateOffscreenMujocoFrameUrl(
      snapshot.active_camera,
      snapshot.telemetry.layerTurnAngleDeg ?? 0.0,
      debugOverlays
    );
    if (url) {
      setSnapshot((prev) => ({ ...prev, main_frame_url: url, frame_source: 'SYNTHETIC_SAMPLE' }));
    }
  }, [
    mode,
    snapshot.active_camera,
    snapshot.telemetry.layerTurnAngleDeg,
    debugOverlays.contactForces,
    debugOverlays.collisionGeoms,
    debugOverlays.tcpFrame,
  ]);

  const handleSwitchMode = (nextMode: RuntimeMode) => {
    setMode(nextMode);
    setStartModalPassword('');
    setStartModalError(null);
    if (nextMode === 'SAMPLE') {
      const targetEv = SAMPLE_TIMELINE.find((e) => e.event_id === selectedEventId) || SAMPLE_TIMELINE[3];
      setSnapshot(createSampleSnapshot(selectedMission, targetEv));
      appendLog(`已切换至 SAMPLE 模式（SYNTHETIC SAMPLE · ${selectedMission}）`);
    } else if (nextMode === 'LIVE') {
      setSnapshot(createDisconnectedLiveSnapshot(seedInput, selectedMission));
      appendLog(`已切换至 LIVE 实时仿真模式，正在连接 ${wsUrl}...`);
    } else if (nextMode === 'REPLAY') {
      if (!replayVideoUrl && !previewScreenshotUrl) {
        setSnapshot(createDisconnectedLiveSnapshot(seedInput, selectedMission));
      }
      appendLog('已切换至 PREVIEW / REPLAY 离线预览模式');
    }
  };

  // LIVE 模式 WebSocket 订阅（含连接失败时清零连接状态，绝不回退至 SAMPLE）
  useEffect(() => {
    if (mode !== 'LIVE') {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      setWsConnected(false);
      return;
    }

    let cancelled = false;
    let reconnectTimer: number | null = null;

    const connect = () => {
      if (cancelled) return;
      try {
        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onopen = () => {
          if (cancelled) return;
          setWsConnected(true);
          appendLog(`已连接 MuJoCo SimulationSession (${wsUrl})`);
          ws.send(JSON.stringify({ type: 'GET_STATE' }));
        };

        ws.onmessage = (event) => {
          if (cancelled) return;
          try {
            const data = JSON.parse(event.data);
            if (data.type === 'STATE_UPDATE' && data.payload) {
              const next = data.payload as SimulationSnapshot;
              // 防止任何样本帧泄漏到 LIVE 模式
              if (next.frame_source === 'SYNTHETIC_SAMPLE') {
                return;
              }
              setSnapshot(next);
              if (next.selected_mission_type) {
                setSelectedMission(next.selected_mission_type);
              }
            } else if (data.type === 'COMMAND_RESULT' && data.ok === false) {
              appendLog(`后端拒绝指令: ${data.error || 'UNKNOWN_ERROR'}`);
            }
          } catch {
            // 忽略非 JSON 心跳
          }
        };

        ws.onclose = () => {
          if (cancelled) return;
          setWsConnected(false);
          reconnectTimer = window.setTimeout(connect, 2500);
        };

        ws.onerror = () => ws.close();
      } catch {
        setWsConnected(false);
      }
    };

    connect();
    return () => {
      cancelled = true;
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [mode, wsUrl]);

  const getHttpBase = () =>
    wsUrl
      .replace(/^wss:/, 'https:')
      .replace(/^ws:/, 'http:')
      .replace(/\/ws\/session$/, '');

  const postBackendCommand = async (
    cmd: Record<string, unknown>
  ): Promise<{ ok: boolean; status: number; body: Record<string, any> | null; detail?: string }> => {
    try {
      const resp = await fetch(`${getHttpBase()}/api/m3d/command`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(cmd),
      });
      const body = (await resp.json().catch(() => null)) as Record<string, any> | null;
      if (!resp.ok) {
        return {
          ok: false,
          status: resp.status,
          body,
          detail: typeof body?.detail === 'string' ? body.detail : `HTTP ${resp.status}`,
        };
      }
      if (body) {
        if (body.snapshot && body.snapshot.frame_source !== 'SYNTHETIC_SAMPLE') {
          setSnapshot(body.snapshot as SimulationSnapshot);
          setWsConnected(true);
        }
      }
      return { ok: true, status: resp.status, body };
    } catch {
      return { ok: false, status: 0, body: null, detail: 'NETWORK_ERROR' };
    }
  };

  const sendBackendCommand = async (cmd: Record<string, unknown>, label: string) => {
    if (mode !== 'LIVE') {
      appendLog(`当前为 ${mode} 只读模式，指令 [${label}] 仅在 LIVE 连接后端时执行`);
      return;
    }
    if (wsConnected && wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(cmd));
      appendLog(`已通过 WebSocket 下发指令: ${label}`);
      return;
    }
    // HTTP 同源回退通道（仅当 LIVE 且页面由后端提供或显式配置 HTTP 时）
    const res = await postBackendCommand(cmd);
    if (res.ok) {
      appendLog(`已通过 HTTP 下发指令: ${label}`);
      return;
    }
    if (res.status > 0) {
      appendLog(`后端拒绝指令 [${label}]: ${res.detail || `HTTP ${res.status}`}`);
      return;
    }
    appendLog(`指令未发送 [${label}]: MuJoCo 后端未连接`);
  };

  const handleSelectMission = (missionType: MissionType) => {
    setSelectedMission(missionType);
    if (mode === 'SAMPLE') {
      const targetEv = SAMPLE_TIMELINE.find((e) => e.event_id === selectedEventId) || SAMPLE_TIMELINE[3];
      setSnapshot(createSampleSnapshot(missionType, targetEv));
      appendLog(`SAMPLE 模式切换 Mission: ${missionType}`);
      return;
    }
    if (mode === 'LIVE') {
      const cmd: Record<string, unknown> = { type: 'SELECT_MISSION', mission_type: missionType };
      if (missionType === 'RELAY_SOLVE_CUBE') {
        cmd.scramble_steps = selectedScrambleSteps;
      }
      void sendBackendCommand(cmd, `选择 Mission ${missionType}`);
    }
  };

  const handleSelectScrambleSteps = (steps: number | 'random') => {
    setSelectedScrambleSteps(steps);
    if (mode === 'LIVE') {
      void sendBackendCommand({ type: 'SET_SCRAMBLE_STEPS', scramble_steps: steps }, `设置打乱步数 ${steps}`);
    }
  };

  const handleRelayCommand = (cmd: Record<string, unknown>, label: string) => {
    if (mode !== 'LIVE') {
      appendLog(`当前为 ${mode} 模式，仅 LIVE 模式支持实时接力控制 [${label}]`);
      return;
    }
    void sendBackendCommand(cmd, label);
  };

  const openStartMissionModal = () => {
    if (mode === 'LIVE' && snapshot.running) {
      appendLog('当前已有任务正在运行，请先点击「安全停止」后再启动新任务');
      return;
    }
    setStartModalPassword('');
    setStartModalError(null);
    setStartModalSubmitting(false);
    setStartModalOpen(true);
  };

  const closeStartMissionModal = () => {
    if (startModalSubmitting) return;
    setStartModalPassword('');
    setStartModalError(null);
    setStartModalOpen(false);
  };

  const handleLaunchMission = async (plannerMode: 'LLM_AGENT' | 'DETERMINISTIC_PLANNER') => {
    if (mode !== 'LIVE') {
      setStartModalError(`当前为 ${mode} 只读模式，仅 LIVE 模式支持模型校验与任务启动`);
      appendLog(`当前为 ${mode} 只读模式，无法启动任务 ${selectedMission}`);
      return;
    }
    if (plannerMode === 'LLM_AGENT' && !startModalPassword) {
      setStartModalError('请输入启用密码以启用 Agent 模型和 VLM 模型');
      startPasswordInputRef.current?.focus();
      return;
    }

    const suppliedPassword = startModalPassword;
    setStartModalSubmitting(true);
    setStartModalError(null);

    const modeCommand: Record<string, unknown> = {
      type: 'SET_PLANNER_MODE',
      planner_mode: plannerMode,
    };
    if (plannerMode === 'LLM_AGENT') {
      modeCommand.enable_password = suppliedPassword;
    }

    const modeRes = await postBackendCommand(modeCommand);
    setStartModalPassword('');

    if (!modeRes.ok) {
      setStartModalSubmitting(false);
      if (modeRes.status === 403) {
        setStartModalError(`密码校验失败，未能启用 Agent 与 VLM 模型 (${modeRes.detail || 'HTTP 403'})`);
        appendLog(`后端拒绝启用 Agent/VLM 模型: ${modeRes.detail || 'HTTP 403'}`);
        window.setTimeout(() => startPasswordInputRef.current?.focus(), 0);
        return;
      }
      if (modeRes.status === 503) {
        setStartModalError(`服务端未配置启用密码 (${modeRes.detail || 'HTTP 503'})`);
        appendLog(`后端未配置模型启用密码: ${modeRes.detail || 'HTTP 503'}`);
        return;
      }
      if (modeRes.status === 0) {
        setStartModalError(`无法连接后端服务 (${getHttpBase()})，请确认仿真后端已运行`);
        appendLog(`启动任务失败 [${selectedMission}]: MuJoCo 后端未连接`);
        return;
      }
      setStartModalError(`切换规划器失败 (${modeRes.detail || `HTTP ${modeRes.status}`})`);
      appendLog(`后端拒绝切换 Planner: ${modeRes.detail || `HTTP ${modeRes.status}`}`);
      return;
    }

    if (modeRes.body?.snapshot?.running) {
      setStartModalSubmitting(false);
      setStartModalError('当前已有任务正在运行，请先点击「安全停止」');
      appendLog(`任务启动被跳过 [${selectedMission}]: 当前已有任务运行中`);
      return;
    }

    const startCmd: Record<string, unknown> = {
      type: 'START_MISSION',
      mission_type: selectedMission,
      seed: seedInput,
    };
    if (selectedMission === 'RELAY_SOLVE_CUBE') {
      startCmd.scramble_steps = selectedScrambleSteps;
      startCmd.full_26_cubie = true;
    }
    const startRes = await postBackendCommand(startCmd);
    setStartModalSubmitting(false);

    if (!startRes.ok) {
      const msg =
        startRes.status === 0
          ? `无法连接后端服务 (${getHttpBase()})，请确认仿真后端已运行`
          : `启动任务被拒绝 (${startRes.detail || `HTTP ${startRes.status}`})`;
      setStartModalError(msg);
      appendLog(`后端拒绝指令 [启动任务 ${selectedMission}]: ${startRes.detail || `HTTP ${startRes.status}`}`);
      return;
    }

    if (startRes.body?.ok === false || startRes.body?.ack?.accepted === false) {
      const reason = String(startRes.body?.ack?.reason || 'MISSION_NOT_ACCEPTED');
      setStartModalError(
        reason === 'mission_already_running'
          ? '当前已有任务正在运行，请先点击「安全停止」'
          : `任务未启动: ${reason}`
      );
      appendLog(`任务未启动 [${selectedMission}]: ${reason}`);
      return;
    }

    setStartModalError(null);
    setStartModalOpen(false);
    appendLog(
      plannerMode === 'LLM_AGENT'
        ? `已通过密码启用 Agent + VLM 模型并启动任务 ${selectedMission} (seed=${seedInput})`
        : `已使用确定性 Baseline 启动任务 ${selectedMission} (seed=${seedInput})`
    );
  };

  const toggleDebugFlag = (key: keyof typeof debugOverlays, label: string) => {
    setDebugOverlays((prev) => {
      const next = { ...prev, [key]: !prev[key] };
      if (mode === 'LIVE' && wsConnected) {
        void sendBackendCommand({ type: 'SET_RENDER_FLAGS', flags: next }, `切换渲染调试层 ${label}`);
      }
      return next;
    });
  };

  const handleLoadReplayFiles = async (videoFile: File | null, timingFile: File | null) => {
    if (videoFile) {
      setReplayVideoUrl(URL.createObjectURL(videoFile));
      appendLog(`已载入历史录像: ${videoFile.name}`);
    }
    if (timingFile) {
      try {
        const text = await timingFile.text();
        const parsed = JSON.parse(text) as ReplayTimingFile;
        setReplayTiming(parsed);
        setSnapshot((prev) => ({
          ...prev,
          session_id: parsed.session_id,
          seed: parsed.seed,
          timeline: parsed.timeline || [],
          trace_events: parsed.trace_events || [],
          observations: parsed.observations || [],
        }));
        appendLog(`已载入时间轴元数据: ${timingFile.name}`);
      } catch {
        appendLog(`解析 ${timingFile.name} 失败`);
      }
    }
  };

  const handleReplayTimeUpdate = (videoTimeSec: number) => {
    if (mode !== 'REPLAY' || !replayTiming?.frames?.length) return;
    let matched = replayTiming.frames[0];
    for (const f of replayTiming.frames) {
      if (f.video_time_sec <= videoTimeSec) matched = f;
      else break;
    }
    setSnapshot((prev) => ({
      ...prev,
      sim_time: matched.sim_time,
      current_stage_id: matched.current_stage_id,
      current_skill: matched.current_skill,
      task_status: matched.task_status,
      observed_facelets: matched.observed_facelets,
      predicted_facelets: matched.predicted_facelets,
      cube_validation_status: matched.cube_validation_status,
      telemetry: matched.telemetry,
    }));
  };

  const handleTimelineEventClick = (ev: TimelineEvent) => {
    if (mode === 'LIVE') {
      appendLog('LIVE 模式下时间线为只读审计流，禁止回溯篡改物理仿真状态');
      return;
    }
    setSelectedEventId(ev.event_id);
    if (mode === 'SAMPLE') {
      const nextSnap = createSampleSnapshot(selectedMission, ev);
      nextSnap.active_camera = snapshot.active_camera;
      setSnapshot(nextSnap);
    } else if (mode === 'REPLAY' && replayVideoRef.current && replayTiming?.frames?.length) {
      const target = replayTiming.frames.find((f) => f.sim_time >= ev.sim_time);
      if (target) replayVideoRef.current.currentTime = target.video_time_sec;
    }
  };

  const refreshExportRuns = async () => {
    setExportErrorMsg(null);
    if (mode === 'SAMPLE' || snapshot.frame_source === 'SYNTHETIC_SAMPLE') {
      setExportRuns([]);
      return;
    }
    try {
      const resp = await fetch(`${getHttpBase()}/api/m3d/runs`);
      if (!resp.ok) {
        setExportErrorMsg(`获取历史实验列表失败: HTTP ${resp.status}`);
        return;
      }
      const data = (await resp.json()) as { current_run_id?: string | null; runs?: HistoricalRunSummary[] };
      const runs = Array.isArray(data.runs) ? data.runs : [];
      setExportRuns(runs);
      const preferred = data.current_run_id || snapshot.run_id || (runs[0]?.run_id ?? '');
      if (preferred && !exportSelectedRunId) {
        setExportSelectedRunId(preferred);
      }
    } catch {
      setExportErrorMsg('无法连接后端获取历史实验运行列表（请确认 LIVE 服务已启动）');
    }
  };

  const openExportModal = () => {
    setExportModalOpen(true);
    setExportErrorMsg(null);
    if (snapshot.run_id) {
      setExportSelectedRunId(snapshot.run_id);
    }
    if (mode !== 'SAMPLE') {
      void refreshExportRuns();
    }
  };

  const handleDownloadExperimentZip = async () => {
    setExportStatusMsg(null);
    setExportErrorMsg(null);
    if (mode === 'SAMPLE' || snapshot.frame_source === 'SYNTHETIC_SAMPLE') {
      setExportErrorMsg('SAMPLE_MODE_FORBIDDEN: SYNTHETIC_SAMPLE 仅用于离线演示，禁止作为真实物理实验导出');
      return;
    }
    const targetRunId = (exportSelectedRunId || snapshot.run_id || '').trim() || null;
    setExportSubmitting(true);
    try {
      const resp = await fetch(`${getHttpBase()}/api/m3d/export`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          run_id: targetRunId,
          scope: exportScope,
          include_rgbd: exportIncludeRgbd,
          include_high_freq_trajectory: exportIncludeHighFreq,
          include_audit_ground_truth: exportIncludeAuditTruth,
        }),
      });
      if (!resp.ok) {
        const errBody = (await resp.json().catch(() => null)) as Record<string, any> | null;
        const detail = typeof errBody?.detail === 'string' ? errBody.detail : `HTTP ${resp.status}`;
        setExportErrorMsg(`导出失败: ${detail}`);
        appendLog(`实验包导出失败: ${detail}`);
        return;
      }
      const blob = await resp.blob();
      const disp = resp.headers.get('Content-Disposition') || '';
      const match = /filename="([^"]+)"/.exec(disp);
      const filename = match ? match[1] : `cuberelay_${targetRunId || 'export'}_${exportScope}.zip`;
      const objectUrl = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = objectUrl;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(objectUrl);
      const kb = (blob.size / 1024).toFixed(1);
      setExportStatusMsg(`已导出 ${filename} (${kb} KB)`);
      appendLog(`已从后端导出完整实验包: ${filename} (${kb} KB)`);
    } catch {
      setExportErrorMsg('导出失败: 后端连接不可用或请求被中断');
    } finally {
      setExportSubmitting(false);
    }
  };

  return (
    <div className="h-screen w-screen overflow-hidden bg-[#080D16] text-slate-100 flex flex-col font-sans select-none">
      {/* 1. 顶部精简导航栏 (44px) */}
      <header className="h-11 shrink-0 bg-[#101827] border-b border-slate-800/90 px-3.5 flex items-center justify-between gap-3">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded bg-[#182338] border border-[#3DE8E5]/40 flex items-center justify-center">
              <Cpu className="w-3.5 h-3.5 text-[#3DE8E5]" />
            </div>
            <span className="text-xs font-bold tracking-wider text-slate-100">CUBERELAY</span>
            <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-[#182338] text-[#3DE8E5] border border-slate-700">
              M3-D
            </span>
          </div>

          <nav className="flex items-center gap-1">
            {[
              { id: 'CONSOLE', label: '任务控制台' },
              { id: 'SETTINGS', label: '能力注册表 & 设置' },
              { id: 'BENCHMARK', label: 'Task Agent 评估' },
            ].map((tab) => (
              <button
                key={tab.id}
                type="button"
                onClick={() => setActiveNav(tab.id as typeof activeNav)}
                className={`px-2.5 py-1 rounded text-[11px] font-medium transition-colors ${
                  activeNav === tab.id
                    ? 'bg-[#182338] text-[#3DE8E5] border border-[#3DE8E5]/30'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </nav>
        </div>

        <div className="hidden lg:flex items-center gap-2 text-[11px] font-mono tracking-widest text-slate-400">
          <span>{selectedMission}</span>
          <span className="text-slate-600">|</span>
          <span className="text-[#3DE8E5]">{snapshot.session_id}</span>
        </div>

        <div className="flex items-center gap-2">
          <div className="flex items-center bg-[#080D16] p-0.5 rounded border border-slate-800 text-[11px]">
            <button
              type="button"
              onClick={() => handleSwitchMode('SAMPLE')}
              className={`px-2 py-0.5 rounded font-medium flex items-center gap-1 transition-colors ${
                mode === 'SAMPLE'
                  ? 'bg-[#FFBF69]/20 text-[#FFBF69] border border-[#FFBF69]/40'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Database className="w-3 h-3" /> SYNTHETIC SAMPLE
            </button>
            <button
              type="button"
              onClick={() => handleSwitchMode('LIVE')}
              className={`px-2 py-0.5 rounded font-medium flex items-center gap-1 transition-colors ${
                mode === 'LIVE'
                  ? 'bg-[#30D6A0]/20 text-[#30D6A0] border border-[#30D6A0]/40'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Radio className="w-3 h-3" /> LIVE 实时仿真
            </button>
            <button
              type="button"
              onClick={() => handleSwitchMode('REPLAY')}
              className={`px-2 py-0.5 rounded font-medium flex items-center gap-1 transition-colors ${
                mode === 'REPLAY'
                  ? 'bg-[#548CFF]/20 text-[#548CFF] border border-[#548CFF]/40'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <History className="w-3 h-3" /> PREVIEW 离线预览
            </button>
          </div>

          <div className="hidden sm:flex items-center gap-1.5 text-[11px] font-mono text-slate-300 bg-[#080D16] px-2 py-0.5 rounded border border-slate-800">
            <Clock className="w-3 h-3 text-[#3DE8E5]" />
            <span>{formatSimTime(snapshot.sim_time)}s</span>
          </div>

          <button
            type="button"
            onClick={openExportModal}
            className="inline-flex items-center gap-1 px-2 py-1 rounded text-[11px] font-medium bg-[#182338] hover:bg-slate-700 text-[#3DE8E5] border border-[#3DE8E5]/30 transition-colors"
            title="Experiment / Trace Export (后端真实实验包 ZIP 导出)"
          >
            <Download className="w-3 h-3" /> 实验导出
          </button>

          <button
            type="button"
            onClick={() => setActiveNav(activeNav === 'SETTINGS' ? 'CONSOLE' : 'SETTINGS')}
            className="p-1.5 rounded bg-[#182338] hover:bg-slate-700 text-slate-300 border border-slate-700/80"
            title="能力注册表与系统设置"
          >
            <Settings className="w-3.5 h-3.5" />
          </button>
        </div>
      </header>

      {/* 2. 主工作区路由 */}
      {activeNav === 'SETTINGS' && (
        <CapabilityAndSettingsView
          wsUrl={wsUrl}
          onWsUrlChange={setWsUrl}
          seedInput={seedInput}
          onSeedChange={setSeedInput}
          capabilities={snapshot.capabilities}
          commandLog={commandLog}
        />
      )}

      {activeNav === 'BENCHMARK' && <TaskAgentBenchmarkView httpBase={getHttpBase()} />}

      {activeNav === 'CONSOLE' && (
        <main className="flex-1 min-h-0 p-2.5 flex flex-col gap-2">
          {/* 中层主工作区: 左侧高大仿真视口 (含折叠监控抽屉) vs 右侧人机接力主控台 */}
          <div
            style={{ gridTemplateColumns: 'minmax(0, 1.65fr) minmax(360px, 1fr)' }}
            className="flex-1 min-h-0 grid gap-2.5"
          >
            <div className="min-w-0 min-h-0 h-full flex flex-col gap-2">
              <div className="flex-1 min-h-0">
                <SimulationViewport
                  mode={mode}
                  wsConnected={wsConnected}
                  wsUrl={wsUrl}
                  snapshot={snapshot}
                  debugOverlays={debugOverlays}
                  onCameraPresetChange={(preset) => {
                    const found = CAMERA_PRESETS.find((c) => c.id === preset);
                    setSnapshot((prev) => ({
                      ...prev,
                      active_camera: preset,
                      camera_azimuth_deg: found?.az ?? prev.camera_azimuth_deg,
                      camera_elevation_deg: found?.el ?? prev.camera_elevation_deg,
                      camera_distance_m: found?.dist ?? prev.camera_distance_m,
                    }));
                    if (mode === 'LIVE') {
                      void sendBackendCommand({ type: 'SET_CAMERA_PRESET', camera: preset }, `切换相机 ${preset}`);
                    }
                  }}
                  onCameraOrbitCommand={(dAz, dEl) => {
                    void sendBackendCommand(
                      { type: 'CAMERA_ORBIT', delta_azimuth: dAz, delta_elevation: dEl },
                      '旋转相机视角'
                    );
                  }}
                  onCameraZoomCommand={(dDist) => {
                    void sendBackendCommand({ type: 'CAMERA_ZOOM', delta_distance: dDist }, '缩放相机视角');
                  }}
                  previewScreenshotUrl={previewScreenshotUrl}
                  onUploadPreviewScreenshot={(url) => {
                    setPreviewScreenshotUrl(url);
                    appendLog('已在 PREVIEW 模式载入外部历史截图');
                  }}
                  replayVideoRef={replayVideoRef}
                  replayVideoUrl={replayVideoUrl}
                  onReplayTimeUpdate={handleReplayTimeUpdate}
                  onLoadReplayFiles={handleLoadReplayFiles}
                  onUrgentInterrupt={() =>
                    handleRelayCommand({ type: 'URGENT_INTERRUPT', reason: '横幅紧急刹车/接管' }, '紧急刹车中断')
                  }
                />
              </div>

              {/* 左侧底部折叠收起的监控抽屉: 机器人相机 / Cube State / 遥测监控 */}
              <div className="shrink-0 bg-[#101827] border border-slate-800/90 rounded-lg px-2.5 py-1.5 space-y-2">
                <button
                  type="button"
                  onClick={() => setTechDrawerOpen((v) => !v)}
                  className="w-full flex items-center justify-between gap-2 text-[10.5px] font-medium text-slate-300 hover:text-white transition-colors"
                >
                  <span className="flex items-center gap-2 min-w-0 truncate">
                    <span className="font-semibold text-[#3DE8E5]">
                      {techDrawerOpen ? '▾' : '▸'} 机器人相机 · Cube State · 遥测监控
                    </span>
                    <span className="font-mono text-[10px] text-slate-400 truncate">
                      ({snapshot.observed_facelets.filter((f) => f.color !== 'UNKNOWN').length}/54 格 · 夹爪{' '}
                      {snapshot.telemetry.gripperState || 'UNKNOWN'})
                    </span>
                  </span>
                  <span className="px-1.5 py-0.5 rounded bg-[#080D16] border border-slate-800 text-[9.5px] font-mono text-slate-400 shrink-0">
                    {techDrawerOpen ? '收起监控 ▴' : '展开监控 ▾'}
                  </span>
                </button>
                {techDrawerOpen && (
                  <div className="h-[210px] grid grid-cols-1 md:grid-cols-3 gap-2.5">
                    <CompactRobotCameraCard
                      rgbUrl={snapshot.wrist_rgb_url}
                      depthUrl={snapshot.wrist_depth_url}
                      depthRangeM={snapshot.depth_range_m}
                      detections={snapshot.detections}
                    />
                    <CompactCubeStateCard
                      observed={snapshot.observed_facelets}
                      predicted={snapshot.predicted_facelets}
                      validationStatus={snapshot.cube_validation_status}
                    />
                    <CompactTelemetryCard telemetry={snapshot.telemetry} />
                  </div>
                )}
              </div>
            </div>

            <RightOrchestrationPanel
              mode={mode}
              snapshot={snapshot}
              selectedMission={selectedMission}
              selectedScrambleSteps={selectedScrambleSteps}
              onSelectMission={handleSelectMission}
              onSelectScrambleSteps={handleSelectScrambleSteps}
              onRelayCommand={handleRelayCommand}
            />
          </div>

          {/* 底部统一时间线与任务控制条 (40px) */}
          <footer className="h-10 shrink-0 bg-[#101827] border border-slate-800/90 rounded-lg px-3 flex items-center justify-between gap-3">
            <div className="flex items-center gap-1.5 overflow-x-auto min-w-0 py-0.5">
              <span className="text-[10px] font-mono text-slate-500 shrink-0 mr-0.5">TIMELINE:</span>
              {snapshot.timeline.length === 0 ? (
                <span className="text-[11px] font-mono text-slate-500">00:00.00 · IDLE</span>
              ) : (
                snapshot.timeline.map((ev) => {
                  const active = ev.event_id === selectedEventId;
                  return (
                    <button
                      key={ev.event_id}
                      type="button"
                      onClick={() => handleTimelineEventClick(ev)}
                      className={`px-2 py-0.5 rounded text-[11px] font-mono shrink-0 border transition-colors ${
                        active
                          ? 'bg-[#182338] text-[#3DE8E5] border-[#3DE8E5]/50'
                          : 'bg-[#080D16] text-slate-400 border-slate-800 hover:text-slate-200'
                      }`}
                    >
                      {ev.short_label}
                    </button>
                  );
                })
              )}
            </div>

            <div className="flex items-center gap-1.5 shrink-0">
              <button
                type="button"
                onClick={() => toggleDebugFlag('contactForces', '接触力')}
                className={`hidden xl:inline-flex px-2 py-1 rounded text-[11px] border transition-colors ${
                  debugOverlays.contactForces
                    ? 'bg-[#FFBF69]/15 text-[#FFBF69] border-[#FFBF69]/40'
                    : 'bg-[#080D16] text-slate-400 border-slate-800'
                }`}
              >
                接触力
              </button>
              <button
                type="button"
                onClick={() => toggleDebugFlag('collisionGeoms', '碰撞点')}
                className={`hidden xl:inline-flex px-2 py-1 rounded text-[11px] border transition-colors ${
                  debugOverlays.collisionGeoms
                    ? 'bg-[#548CFF]/15 text-[#548CFF] border-[#548CFF]/40'
                    : 'bg-[#080D16] text-slate-400 border-slate-800'
                }`}
              >
                碰撞点
              </button>

              <div className="h-4 w-px bg-slate-800 mx-0.5 hidden xl:block" />

              <button
                type="button"
                onClick={openStartMissionModal}
                disabled={mode === 'LIVE' && snapshot.running}
                title={
                  mode !== 'LIVE'
                    ? '请切换至 LIVE 实时仿真模式连接后端后启动'
                    : snapshot.running
                    ? '当前任务正在运行中，请先点击「安全停止」'
                    : `启动前输入密码启用 Agent 与 VLM 模型: ${selectedMission}`
                }
                className="inline-flex items-center gap-1 px-2.5 py-1 rounded text-[11px] font-semibold bg-[#30D6A0]/20 hover:bg-[#30D6A0]/30 text-[#30D6A0] border border-[#30D6A0]/50 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <Play className="w-3 h-3" /> 开始任务 ({MISSION_OPTIONS.find((m) => m.type === selectedMission)?.label})
              </button>

              <button
                type="button"
                onClick={() => void sendBackendCommand({ type: 'STOP_MISSION' }, '安全停止任务')}
                className="inline-flex items-center gap-1 px-2.5 py-1 rounded text-[11px] font-semibold bg-[#FF667B]/15 hover:bg-[#FF667B]/25 text-[#FF667B] border border-[#FF667B]/40 transition-colors"
              >
                <Square className="w-3 h-3" /> 安全停止
              </button>

              <button
                type="button"
                onClick={() =>
                  void sendBackendCommand(
                    {
                      type: 'RESET_SCENE',
                      seed: seedInput,
                      mission_type: selectedMission,
                      ...(selectedMission === 'RELAY_SOLVE_CUBE'
                        ? { scramble_steps: selectedScrambleSteps, full_26_cubie: true }
                        : {}),
                    },
                    `重置场景 (seed=${seedInput}, mission=${selectedMission})`
                  )
                }
                className="inline-flex items-center gap-1 px-2 py-1 rounded text-[11px] font-medium bg-[#182338] hover:bg-slate-700 text-slate-200 border border-slate-700 transition-colors"
              >
                <RotateCcw className="w-3 h-3" /> 重置场景
              </button>
            </div>
          </footer>

          {startModalOpen && (
            <div
              className="fixed inset-0 z-40 bg-black/50 flex items-end justify-end p-3 pb-14"
              onClick={closeStartMissionModal}
            >
              <div
                role="dialog"
                aria-modal="true"
                aria-labelledby="start-mission-modal-title"
                onClick={(e) => e.stopPropagation()}
                className="w-full max-w-sm bg-[#101827] border border-[#3DE8E5]/40 rounded-lg p-3.5 space-y-2.5 shadow-2xl"
              >
                <div className="flex items-center justify-between gap-2 border-b border-slate-800 pb-2">
                  <div className="flex items-center gap-1.5 min-w-0">
                    <Lock className="w-3.5 h-3.5 text-[#3DE8E5] shrink-0" />
                    <h3 id="start-mission-modal-title" className="text-xs font-semibold text-slate-100 truncate">
                      启动前密码启用 Agent &amp; VLM 模型
                    </h3>
                  </div>
                  <button
                    type="button"
                    aria-label="关闭弹窗"
                    disabled={startModalSubmitting}
                    onClick={closeStartMissionModal}
                    className="p-1 rounded text-slate-400 hover:text-slate-200 hover:bg-[#182338] transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>

                <div className="bg-[#080D16] border border-slate-800 rounded p-2 space-y-1 text-[10.5px]">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-slate-400">待启动任务</span>
                    <span className="font-mono text-[#3DE8E5]">
                      {MISSION_OPTIONS.find((m) => m.type === selectedMission)?.label} · Seed {seedInput}
                    </span>
                  </div>
                  <div className="grid grid-cols-2 gap-1.5 pt-1 border-t border-slate-800/80">
                    <div className="rounded border border-[#3DE8E5]/30 bg-[#3DE8E5]/5 px-1.5 py-1">
                      <div className="text-[9px] font-mono text-[#3DE8E5]">VLM 模型 · 感知</div>
                      <div className="text-[10px] text-slate-200 truncate">
                        {snapshot.agent_state?.perception_model_name || 'Visual Perception'}
                      </div>
                    </div>
                    <div className="rounded border border-[#548CFF]/30 bg-[#548CFF]/5 px-1.5 py-1">
                      <div className="text-[9px] font-mono text-[#548CFF]">Agent 模型 · 规划</div>
                      <div className="text-[10px] text-slate-200 truncate">
                        {snapshot.agent_state?.agent_model_name || 'Action Planner'}
                      </div>
                    </div>
                  </div>
                </div>

                {mode !== 'LIVE' && (
                  <div className="bg-[#FFBF69]/10 border border-[#FFBF69]/40 rounded px-2 py-1.5 text-[10.5px] text-[#FFBF69] leading-snug flex items-center justify-between gap-2">
                    <span>当前为 {mode} 只读模式，需切换至 LIVE 模式后启动。</span>
                    <button
                      type="button"
                      onClick={() => {
                        handleSwitchMode('LIVE');
                        setStartModalError(null);
                      }}
                      className="px-2 py-0.5 rounded text-[10px] font-semibold bg-[#30D6A0]/20 text-[#30D6A0] border border-[#30D6A0]/40 shrink-0"
                    >
                      切换 LIVE
                    </button>
                  </div>
                )}

                <form
                  className="space-y-2"
                  onSubmit={(e) => {
                    e.preventDefault();
                    void handleLaunchMission('LLM_AGENT');
                  }}
                >
                  <div className="space-y-1">
                    <label htmlFor="start-model-enable-password" className="block text-[10.5px] text-slate-300">
                      模型启用密码（每次启动前校验并启用 Agent 与 VLM 模型）
                    </label>
                    <input
                      id="start-model-enable-password"
                      ref={startPasswordInputRef}
                      type="password"
                      value={startModalPassword}
                      autoComplete="current-password"
                      aria-label="Agent 与 VLM 模型启用密码"
                      placeholder="输入密码启用 Agent 模型和 VLM 模型"
                      disabled={startModalSubmitting}
                      onChange={(e) => {
                        setStartModalPassword(e.target.value);
                        if (startModalError) setStartModalError(null);
                      }}
                      className="w-full rounded border border-slate-700 bg-[#080D16] px-2.5 py-1.5 text-[11px] text-slate-100 outline-none focus:border-[#30D6A0] placeholder:text-slate-600"
                    />
                    <div className="text-[9.5px] leading-tight text-slate-500">
                      密码仅用于本次后端校验，不会写入任务 Trace 或页面快照。
                    </div>
                  </div>

                  {startModalError && (
                    <div className="bg-[#FF667B]/10 border border-[#FF667B]/40 rounded px-2 py-1.5 text-[10.5px] text-[#FF667B] leading-snug">
                      {startModalError}
                    </div>
                  )}

                  <div className="flex items-center justify-between gap-2 pt-1 border-t border-slate-800">
                    <button
                      type="button"
                      disabled={startModalSubmitting || mode !== 'LIVE'}
                      onClick={() => void handleLaunchMission('DETERMINISTIC_PLANNER')}
                      className="shrink-0 px-2 py-1.5 rounded text-[10.5px] font-medium bg-[#182338] hover:bg-slate-700 text-slate-300 border border-slate-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                      确定性 Baseline 启动
                    </button>
                    <div className="flex items-center gap-1.5 shrink-0">
                      <button
                        type="button"
                        disabled={startModalSubmitting}
                        onClick={closeStartMissionModal}
                        className="shrink-0 px-2.5 py-1.5 rounded text-[11px] font-medium bg-[#182338] hover:bg-slate-700 text-slate-300 border border-slate-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                      >
                        取消
                      </button>
                      <button
                        type="submit"
                        disabled={startModalSubmitting || !startModalPassword || mode !== 'LIVE'}
                        className="shrink-0 inline-flex items-center justify-center gap-1.5 px-2.5 py-1.5 rounded text-[11px] font-semibold bg-[#30D6A0]/20 hover:bg-[#30D6A0]/30 text-[#30D6A0] border border-[#30D6A0]/50 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                      >
                        {startModalSubmitting ? (
                          <>
                            <RefreshCw className="w-3 h-3 animate-spin" /> 校验中...
                          </>
                        ) : (
                          <>
                            <Play className="w-3 h-3" /> 启用并开始任务
                          </>
                        )}
                      </button>
                    </div>
                  </div>
                </form>
              </div>
            </div>
          )}
        </main>
      )}

      {exportModalOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 flex items-center justify-center p-3"
          onClick={() => {
            if (!exportSubmitting) setExportModalOpen(false);
          }}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="experiment-export-modal-title"
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-md bg-[#101827] border border-[#3DE8E5]/40 rounded-lg p-3.5 space-y-2.5 shadow-2xl"
          >
            <div className="flex items-center justify-between gap-2 border-b border-slate-800 pb-2">
              <div className="flex items-center gap-1.5 min-w-0">
                <Download className="w-3.5 h-3.5 text-[#3DE8E5] shrink-0" />
                <h3 id="experiment-export-modal-title" className="text-xs font-semibold text-slate-100 truncate">
                  Experiment / Trace Export · 因果审计实验包
                </h3>
              </div>
              <button
                type="button"
                aria-label="关闭导出弹窗"
                disabled={exportSubmitting}
                onClick={() => setExportModalOpen(false)}
                className="p-1 rounded text-slate-400 hover:text-slate-200 hover:bg-[#182338] transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>

            {mode === 'SAMPLE' || snapshot.frame_source === 'SYNTHETIC_SAMPLE' ? (
              <div className="bg-[#FF667B]/10 border border-[#FF667B]/40 rounded p-2 text-[10.5px] text-[#FF667B] leading-snug">
                当前为 SYNTHETIC_SAMPLE 合成演示模式：SAMPLE 数据严禁作为真实物理实验数据包导出，请切换至 LIVE 实时仿真。
              </div>
            ) : (
              <div className="bg-[#080D16] border border-slate-800 rounded p-2 space-y-1 text-[10.5px]">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-slate-400">当前 run_id</span>
                  <span className="font-mono text-[#3DE8E5] truncate">
                    {snapshot.run_id || '未创建运行记录'}
                  </span>
                </div>
                <div className="flex items-center justify-between gap-2">
                  <span className="text-slate-400">数据采集状态</span>
                  <span className="font-mono text-[#30D6A0]">
                    {snapshot.experiment_recording?.status || 'IDLE'}
                  </span>
                </div>
                <div className="grid grid-cols-3 gap-1 pt-1 border-t border-slate-800/80 font-mono text-[9.5px] text-slate-300">
                  <span>Frames: {snapshot.experiment_recording?.counts?.frames ?? 0}</span>
                  <span>Poses: {snapshot.experiment_recording?.counts?.pose_estimates ?? 0}</span>
                  <span>Targets: {snapshot.experiment_recording?.counts?.grasp_targets ?? 0}</span>
                  <span>States: {snapshot.experiment_recording?.counts?.robot_states ?? 0}</span>
                  <span>Contacts: {snapshot.experiment_recording?.counts?.contact_samples ?? 0}</span>
                  <span>Verifs: {snapshot.experiment_recording?.counts?.contact_verifications ?? 0}</span>
                </div>
              </div>
            )}

            <div className="space-y-2 text-[10.5px]">
              <div className="space-y-1">
                <div className="flex items-center justify-between">
                  <label htmlFor="export-run-select" className="text-slate-300">
                    历史实验运行列表 (按 run_id 导出)
                  </label>
                  <button
                    type="button"
                    onClick={() => void refreshExportRuns()}
                    disabled={mode === 'SAMPLE' || exportSubmitting}
                    className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9.5px] bg-[#182338] text-slate-300 border border-slate-700 hover:text-white disabled:opacity-40"
                  >
                    <RefreshCw className="w-2.5 h-2.5" /> 刷新列表
                  </button>
                </div>
                <select
                  id="export-run-select"
                  value={exportSelectedRunId}
                  disabled={mode === 'SAMPLE' || exportSubmitting}
                  onChange={(e) => setExportSelectedRunId(e.target.value)}
                  className="w-full rounded border border-slate-700 bg-[#080D16] px-2 py-1 text-[10.5px] font-mono text-slate-100 outline-none focus:border-[#30D6A0]"
                >
                  <option value="">
                    {snapshot.run_id ? `当前运行 (${snapshot.run_id})` : '当前最新运行'}
                  </option>
                  {exportRuns.map((run) => (
                    <option key={run.run_id} value={run.run_id}>
                      {run.run_id} · {run.mission_type || 'MISSION'} · seed={run.seed ?? 0} · {run.recording_status || 'READY'}
                    </option>
                  ))}
                </select>
              </div>

              <div className="space-y-1">
                <label htmlFor="export-scope-select" className="block text-slate-300">
                  导出范围
                </label>
                <select
                  id="export-scope-select"
                  value={exportScope}
                  disabled={mode === 'SAMPLE' || exportSubmitting}
                  onChange={(e) => setExportScope(e.target.value as typeof exportScope)}
                  className="w-full rounded border border-slate-700 bg-[#080D16] px-2 py-1 text-[10.5px] font-mono text-slate-100 outline-none focus:border-[#30D6A0]"
                >
                  <option value="full_mission">full_mission（完整 Mission + 视觉 + 轨迹 + 接触验证）</option>
                  <option value="grasp_causal_chain">grasp_causal_chain（抓取视觉因果链专项包）</option>
                  <option value="events_only">events_only（仅事件流 / Snapshot / 校验报告）</option>
                </select>
              </div>

              <div className="space-y-1 bg-[#080D16] border border-slate-800 rounded p-2">
                <label className="flex items-center gap-2 text-slate-300">
                  <input
                    type="checkbox"
                    checked={exportIncludeRgbd}
                    disabled={mode === 'SAMPLE' || exportSubmitting}
                    onChange={(e) => setExportIncludeRgbd(e.target.checked)}
                  />
                  <span>包含原始 RGB (.png) 与米制 Depth (.npy) + 标定内/外参</span>
                </label>
                <label className="flex items-center gap-2 text-slate-300">
                  <input
                    type="checkbox"
                    checked={exportIncludeHighFreq}
                    disabled={mode === 'SAMPLE' || exportSubmitting}
                    onChange={(e) => setExportIncludeHighFreq(e.target.checked)}
                  />
                  <span>包含高频机器人轨迹与接触时序 (robot_states / contact_samples)</span>
                </label>
                <label className="flex items-center gap-2 text-slate-300">
                  <input
                    type="checkbox"
                    checked={exportIncludeAuditTruth}
                    disabled={mode === 'SAMPLE' || exportSubmitting}
                    onChange={(e) => setExportIncludeAuditTruth(e.target.checked)}
                  />
                  <span>包含隔离审计真值 (audit_only_poses.csv，仅离线审计用)</span>
                </label>
              </div>
            </div>

            {exportStatusMsg && (
              <div className="bg-[#30D6A0]/15 border border-[#30D6A0]/40 rounded px-2 py-1.5 text-[10.5px] text-[#30D6A0] leading-snug">
                {exportStatusMsg}
              </div>
            )}

            {exportErrorMsg && (
              <div className="bg-[#FF667B]/10 border border-[#FF667B]/40 rounded px-2 py-1.5 text-[10.5px] text-[#FF667B] leading-snug">
                {exportErrorMsg}
              </div>
            )}

            <div className="flex items-center justify-end gap-2 pt-1 border-t border-slate-800">
              <button
                type="button"
                disabled={exportSubmitting}
                onClick={() => setExportModalOpen(false)}
                className="px-2.5 py-1.5 rounded text-[11px] font-medium bg-[#182338] hover:bg-slate-700 text-slate-300 border border-slate-700 transition-colors disabled:opacity-40"
              >
                关闭
              </button>
              <button
                type="button"
                disabled={exportSubmitting || mode === 'SAMPLE' || snapshot.frame_source === 'SYNTHETIC_SAMPLE'}
                onClick={() => void handleDownloadExperimentZip()}
                className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded text-[11px] font-semibold bg-[#3DE8E5]/20 hover:bg-[#3DE8E5]/30 text-[#3DE8E5] border border-[#3DE8E5]/40 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {exportSubmitting ? (
                  <>
                    <RefreshCw className="w-3 h-3 animate-spin" /> 打包下载中...
                  </>
                ) : (
                  <>
                    <Download className="w-3 h-3" /> 导出完整 ZIP 实验包
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
