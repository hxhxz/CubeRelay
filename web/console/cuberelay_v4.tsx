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
  FileCode2,
  Film,
  FolderOpen,
  GitBranch,
  Grid,
  History,
  Layers,
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

export type MissionType = 'INSPECT_CUBE' | 'VERIFY_PHYSICAL_U_TURN' | 'SOLVE_CUBE';

export type MissionStatus =
  | 'CREATED'
  | 'OBSERVING'
  | 'PLANNING'
  | 'EXECUTING'
  | 'VERIFYING'
  | 'BLOCKED_CAPABILITY'
  | 'COMPLETED'
  | 'FAILED'
  | 'CANCELLED';

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
  | 'MISSION_FAILED';

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
  status_label: string;
  latest_observation?: ObservationReference | null;
  selected_action?: string | null;
  selection_rationale?: string | null;
  last_skill_call?: string | null;
  last_execution_feedback?: string | null;
  blocked_or_replan_reason?: string | null;
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
  task_status: 'IDLE' | 'RUNNING' | 'PAUSED' | 'COMPLETED' | 'FAILED' | 'STOPPED';
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
    camera_ids: string[];
    frame_refs: string[];
    visual_summary: string;
    coverage: number;
    sim_time: number;
  }>;
  capabilities?: CapabilityRegistrySnapshot | null;
  agent_state?: AgentObservabilityState | null;
  physical_verification?: Record<string, unknown> | null;
  last_observation_ref?: ObservationReference | null;
  running?: boolean;
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
  { id: 'overview', label: '场景总览', desc: '3/4 实验室工作站全局机位', az: 135, el: -28, dist: 1.15 },
  { id: 'gripper_closeup', label: '夹爪特写', desc: '末端双指夹持接触局部机位', az: 148, el: -20, dist: 0.48 },
  { id: 'cube_closeup', label: '魔方特写', desc: '魔方与转面夹具高倍率视角', az: 125, el: -32, dist: 0.36 },
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
    active_camera: 'overview',
    camera_azimuth_deg: 135,
    camera_elevation_deg: -28,
    camera_distance_m: 1.15,
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
    active_camera: 'overview',
    camera_azimuth_deg: 135,
    camera_elevation_deg: -28,
    camera_distance_m: 1.15,
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
}) => {
  const dragStateRef = useRef<{ active: boolean; lastX: number; lastY: number }>({
    active: false,
    lastX: 0,
    lastY: 0,
  });

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
    onCameraZoomCommand(e.deltaY > 0 ? 0.06 : -0.06);
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
        </div>
      </div>

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
  snapshot: SimulationSnapshot;
  selectedMission: MissionType;
  onSelectMission: (missionType: MissionType) => void;
}

const RightOrchestrationPanel: React.FC<RightOrchestrationPanelProps> = ({
  snapshot,
  selectedMission,
  onSelectMission,
}) => {
  const [rightTab, setRightTab] = useState<'AGENT' | 'SKILL'>('AGENT');
  const [expandedSkills, setExpandedSkills] = useState<Set<string>>(new Set());
  const [expandedTraceEvents, setExpandedTraceEvents] = useState<Set<string>>(new Set());

  const mission = snapshot.mission;
  const plan = snapshot.plan;
  const agent = snapshot.agent_state;
  const decisionEvents = snapshot.decision_events || [];
  const executions = snapshot.skill_executions || [];
  const traceEvents = snapshot.trace_events || [];
  const policyTraceEvents = traceEvents.filter((event) => event.event_type === 'decision');
  const missionSpec = MISSION_OPTIONS.find((m) => m.type === selectedMission)!;

  const completedSteps = plan ? plan.steps.filter((s) => s.status === 'VERIFIED').length : 0;
  const totalSteps = plan ? plan.steps.length : 0;

  return (
    <div className="min-w-0 min-h-0 h-full bg-[#101827] border border-slate-800/90 rounded-lg p-2.5 flex flex-col gap-2">
      {/* 顶部标题与 Mission 选择器 */}
      <div className="space-y-1.5 border-b border-slate-800/90 pb-2 shrink-0">
        <div className="flex items-center justify-between gap-1.5">
          <div className="flex items-center gap-1.5 min-w-0">
            <GitBranch className="w-3.5 h-3.5 text-[#3DE8E5] shrink-0" />
            <span className="text-[11px] font-semibold tracking-wider text-slate-200 uppercase truncate">
              MISSION & ORCHESTRATION
            </span>
          </div>
          <MissionStatusBadge status={mission?.status} />
        </div>

        <div className="grid grid-cols-3 gap-1 bg-[#080D16] p-0.5 rounded border border-slate-800">
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

        <div className="text-[10px] text-slate-400 bg-[#080D16] border border-slate-800/80 rounded px-2 py-1 leading-snug">
          {missionSpec.capabilityNote}
        </div>
      </div>

      {/* 双标签页切换: Agent / 决策 vs Skill / 执行 */}
      <div className="grid grid-cols-2 gap-1 bg-[#080D16] p-0.5 rounded border border-slate-800 shrink-0">
        <button
          type="button"
          onClick={() => setRightTab('AGENT')}
          className={`flex items-center justify-center gap-1.5 py-1 rounded text-[11px] font-semibold transition-colors ${
            rightTab === 'AGENT'
              ? 'bg-[#182338] text-[#3DE8E5] border border-[#3DE8E5]/40'
              : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          <Bot className="w-3.5 h-3.5" /> Agent / 决策
        </button>
        <button
          type="button"
          onClick={() => setRightTab('SKILL')}
          className={`flex items-center justify-center gap-1.5 py-1 rounded text-[11px] font-semibold transition-colors ${
            rightTab === 'SKILL'
              ? 'bg-[#182338] text-[#3DE8E5] border border-[#3DE8E5]/40'
              : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          <Layers className="w-3.5 h-3.5" /> Skill / 执行 ({completedSteps}/{totalSteps})
        </button>
      </div>

      {/* 标签 A: Agent / 决策可观测性 */}
      {rightTab === 'AGENT' && (
        <div className="flex-1 min-h-0 overflow-y-auto space-y-2 pr-0.5 text-[11px]">
          {/* 明确区分规划器 / LLM 状态（无 LLM 连接时禁止伪造思考日志） */}
          <div
            className={`px-2 py-1.5 rounded border text-[10.5px] font-medium flex items-center gap-1.5 ${
              agent?.llm_connected
                ? 'bg-[#30D6A0]/10 border-[#30D6A0]/40 text-[#30D6A0]'
                : agent?.planner_mode === 'DETERMINISTIC_PLANNER'
                ? 'bg-[#548CFF]/15 border-[#548CFF]/40 text-slate-200'
                : 'bg-[#182338] border-slate-700 text-slate-300'
            }`}
          >
            <Bot className="w-3.5 h-3.5 shrink-0 text-[#3DE8E5]" />
            <span className="leading-snug">
              {agent?.llm_connected
                ? `LLM Agent 已连接 (${agent.llm_model || 'Gemini'})`
                : agent?.planner_mode === 'DETERMINISTIC_PLANNER'
                ? agent.status_label || '当前由确定性任务规划器执行，LLM Agent 尚未接入'
                : 'Agent 尚未接入'}
            </span>
          </div>

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

          {/* 观察摘要与决策依据 */}
          <div className="p-2 rounded bg-[#080D16] border border-slate-800/90 space-y-1.5">
            <div>
              <div className="text-[10px] font-mono text-slate-400">最新观察摘要</div>
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

            <div className="pt-1 border-t border-slate-800/80">
              <div className="text-[10px] font-mono text-slate-400">当前选择动作与选择依据</div>
              <div className="font-mono text-[10.5px] text-[#3DE8E5]">
                {agent?.selected_action || '--'}
              </div>
              <div className="text-[10.5px] text-slate-300 leading-snug mt-0.5">
                {agent?.selection_rationale || plan?.rationale_summary || '等待任务启动后由确定性规划器生成计划'}
              </div>
            </div>

            <div className="pt-1 border-t border-slate-800/80">
              <div className="text-[10px] font-mono text-slate-400">最近 Skill 调用与执行反馈</div>
              <div className="font-mono text-[10px] text-slate-200">{agent?.last_skill_call || '--'}</div>
              <div className="text-[10.5px] text-slate-400 leading-snug">
                {agent?.last_execution_feedback || '--'}
              </div>
            </div>
          </div>

          {/* 可审计决策事件流 (DecisionEvent) */}
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
                  .map((ev) => (
                    <div
                      key={ev.event_id}
                      className="p-1.5 rounded bg-[#080D16] border border-slate-800/80 space-y-0.5"
                    >
                      <div className="flex items-center justify-between gap-1 text-[9.5px] font-mono">
                        <span
                          className={
                            ev.event_type === 'CAPABILITY_BLOCKED'
                              ? 'text-[#FFBF69]'
                              : ev.event_type.includes('FAILED')
                              ? 'text-[#FF667B]'
                              : 'text-[#3DE8E5]'
                          }
                        >
                          #{ev.sequence} {ev.event_type}
                        </span>
                        <span className="text-slate-500">
                          {ev.sim_time !== null && ev.sim_time !== undefined ? `${ev.sim_time.toFixed(2)}s` : ev.wall_time}
                        </span>
                      </div>
                      <div className="text-[10.5px] text-slate-200 leading-snug">{ev.summary}</div>
                      <div className="text-[10px] text-slate-400 leading-snug">{ev.decision_rationale_summary}</div>
                    </div>
                  ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* 标签 B: Skill / 执行流水线 (严格来自当前 Mission 动态计划) */}
      {rightTab === 'SKILL' && (
        <div className="flex-1 min-h-0 flex flex-col justify-between gap-1.5 overflow-y-auto pr-0.5">
          <div className="space-y-1 flex-1 overflow-y-auto">
            {!plan || plan.steps.length === 0 ? (
              <div className="p-2.5 rounded bg-[#080D16] border border-slate-800 text-[11px] text-slate-400">
                尚未生成任务计划，请选择 Mission 并启动任务。
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
                  : [];
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

                    {composite && (
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
                          子事件 {childEvents.length} · {composite.status}
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
  const [activeNav, setActiveNav] = useState<'CONSOLE' | 'SETTINGS'>('CONSOLE');
  const [mode, setMode] = useState<RuntimeMode>(() => getDefaultRuntimeMode());
  const [wsUrl, setWsUrl] = useState<string>(() => getDefaultWsUrl());
  const [wsConnected, setWsConnected] = useState<boolean>(false);
  const [seedInput, setSeedInput] = useState<number>(0);
  const [selectedMission, setSelectedMission] = useState<MissionType>('INSPECT_CUBE');

  const [snapshot, setSnapshot] = useState<SimulationSnapshot>(() =>
    getDefaultRuntimeMode() === 'LIVE'
      ? createDisconnectedLiveSnapshot(0, 'INSPECT_CUBE')
      : createSampleSnapshot('INSPECT_CUBE', SAMPLE_TIMELINE[3])
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

  const appendLog = (msg: string) => {
    const ts = new Date().toTimeString().slice(0, 8);
    setCommandLog((prev) => [`[${ts}] ${msg}`, ...prev.slice(0, 29)]);
  };

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
    try {
      const httpBase = wsUrl
        .replace(/^wss:/, 'https:')
        .replace(/^ws:/, 'http:')
        .replace(/\/ws\/session$/, '');
      const resp = await fetch(`${httpBase}/api/m3d/command`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(cmd),
      });
      if (resp.ok) {
        const body = await resp.json();
        if (body.snapshot && body.snapshot.frame_source !== 'SYNTHETIC_SAMPLE') {
          setSnapshot(body.snapshot as SimulationSnapshot);
          setWsConnected(true);
        }
        appendLog(`已通过 HTTP 下发指令: ${label}`);
        return;
      }
    } catch {
      // Fall through to disconnected log
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
      void sendBackendCommand({ type: 'SELECT_MISSION', mission_type: missionType }, `选择 Mission ${missionType}`);
    }
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

      {activeNav === 'CONSOLE' && (
        <main className="flex-1 min-h-0 p-2.5 flex flex-col gap-2.5">
          {/* 中层主工作区: 严格 3:1 宽度比例同行并排 (75% : 25%) */}
          <div
            style={{ gridTemplateColumns: 'minmax(0, 3fr) minmax(300px, 1fr)' }}
            className="flex-1 min-h-0 grid gap-2.5"
          >
            <div className="min-w-0 min-h-0 h-full">
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
              />
            </div>

            <RightOrchestrationPanel
              snapshot={snapshot}
              selectedMission={selectedMission}
              onSelectMission={handleSelectMission}
            />
          </div>

          {/* 下层三等分仪表栏 (h-[222px]) */}
          <div className="h-[222px] shrink-0 grid grid-cols-1 md:grid-cols-3 gap-2.5">
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
                onClick={() =>
                  void sendBackendCommand(
                    { type: 'START_MISSION', mission_type: selectedMission, seed: seedInput },
                    `启动任务 ${selectedMission} (seed=${seedInput})`
                  )
                }
                title={mode === 'LIVE' ? `启动 Mission: ${selectedMission}` : '请切换至 LIVE 实时仿真模式连接后端后启动'}
                className="inline-flex items-center gap-1 px-2.5 py-1 rounded text-[11px] font-semibold bg-[#30D6A0]/20 hover:bg-[#30D6A0]/30 text-[#30D6A0] border border-[#30D6A0]/50 transition-colors"
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
                    { type: 'RESET_SCENE', seed: seedInput, mission_type: selectedMission },
                    `重置场景 (seed=${seedInput}, mission=${selectedMission})`
                  )
                }
                className="inline-flex items-center gap-1 px-2 py-1 rounded text-[11px] font-medium bg-[#182338] hover:bg-slate-700 text-slate-200 border border-slate-700 transition-colors"
              >
                <RotateCcw className="w-3 h-3" /> 重置场景
              </button>
            </div>
          </footer>
        </main>
      )}
    </div>
  );
}
