# CubeRelay M4-E Phase 2–6：Perception Evidence 契约与架构规整规范

> 本文档定义 CubeRelay 在 M4-E 规整后的统一感知—决策—安全门控—执行契约，对应实现位于
> `src/cube_relay/perception/`、`src/cube_relay/mission/`、`src/cube_relay/embodied/` 与 `src/cube_relay/benchmark/`。

---

## 1. 核心分层与不可变原则（P1–P5）

```text
RGB-D Observation
  ├── Deterministic CV Stack (P1)
  │     └── DeterministicCubeLocalizer / Pose6D / PerspectiveFaceletMapper / SixFacePerception
  │     └── StickerStateFusion / solve_canonical_mapping / compare_observations / verify_post_turn_state
  │     └── 适应器 -> GeometricObservationPayload
  │
  └── [可选] VLMPerceptionProvider (P2, 仅当 use_vlm_perception=True)
        └── 输出 SemanticSceneObservation -> SemanticObservationEnvelope (严格标定 REAL_VLM / provenance)
              │
              ▼ (若 CV_ONLY: semantic_observation=None, semantic_source=NONE)
     PerceptionEvidenceBundle (`src/cube_relay/perception/evidence.py`)
              │
              ▼
       EvidenceValidator (`src/cube_relay/perception/validator.py`, Cases 1–7)
              │
              ▼ (不选择高层 Skill，不进行不透明融合)
     AgentPlanningProvider + LLMAgentDecisionPolicy (P3, 不接收 RGB 像素)
              │
              ▼
   _SafetyGatedPolicyBase + SkillRegistry Preconditions + StateValidator (P4)
              │
              ▼
       SimulationSession / SkillRuntime / MuJoCo Controllers + 物理接触校验
```

### 基线隔离策略（P3 & P5）
- **`LLMAgentDecisionPolicy` (`ACTIVE_MAINLINE`)** 与 **`GeminiMissionPlanner` (`BENCHMARK_BASELINE`, M4-A)** 解耦为平级兄弟类，共同继承 `_SafetyGatedPolicyBase` 的确定性 `SkillRegistry` 安全门控与 prompt 上下文校验，而非让双模型策略继承单模型基线。
- `LLMAgentDecisionPolicy` 的 Planning Model（`AgentPlanningProvider`）**永不接收原始 RGB 像素**；其 `CV_ONLY` 模式 (`use_vlm_perception=False`) 在 `semantic=None` 与 `rgb=None` 下可合法运行。
- `GeminiMissionPlanner`（M4-A 单模型基线）仅由 Benchmark Group E 与历史 M4-A 脚本调用，不作为 LIVE `SimulationSession.set_planner_mode("LLM_AGENT")` 的运行目标。

---

## 2. Unified Perception Evidence Protocol (`src/cube_relay/perception/evidence.py`)

在不重写既有 `AgentObservation`、`ObservationReference` 与 `SemanticSceneObservation` 的前提下，通过 Adapter 函数 `build_perception_evidence_bundle(...)` 构造 `PerceptionEvidenceBundle`：

| 字段 | 职责 |
| :--- | :--- |
| `bundle_id` | 每次证据组装生成唯一 ID (`ev-...`)，贯穿 Decision / Execution / Export 全链路 |
| `observation_id`, `mission_id`, `session_id` | 严格保留原始 `AgentObservation.observation_id` 与任务关联 |
| `primary_camera_id`, `primary_frame_id`, `captured_sim_time`, `wall_time_utc` | 保留主视角的相机 ID、帧 ID、仿真时间戳与 UTC 墙钟时间 |
| `frames: list[FrameEvidenceRef]` | 支持多相机与多帧引用（从 `camera_metadata.multiview_frames/frames` 与额外帧提取） |
| `geometric_observation: GeometricObservationPayload` | 定量 CV 状态（定位、6D 位姿、`observed_count` / `unknown_count` / `conflict_count`、`cv_54_verified`、`cube_held_in_gripper`） |
| `semantic_observation: SemanticSceneObservation \| None` | 经过 `EvidenceValidator` 核验后允许交给 Agent 的语义观测；`CV_ONLY` 或被拒绝（如过期旧帧）时为 `None` |
| `raw_semantic_envelope: SemanticObservationEnvelope \| None` | 保留未裁剪前的原始语义信封、请求 ID、延迟、源类型与声明来源用于离线审计 |
| `observation_refs` | 聚合 `observation_id`、`pose_estimate_id`、`frame_id` 等引用列表 |
| `provenance: EvidenceProvenance` | 记录 `geometric_source`, `semantic_source`, `fallback_source`, `is_real_vlm`, `semantic_provided_to_agent`, `vlm_timed_out`, `vlm_error_code` |
| `validity: EvidenceValidity` | 记录 `validation_status`, `is_stale`, `frame_alignment_ok`, `semantic_rejected`, `grasp_precondition_satisfied`, `preserve_verified_cv_fusion` 等状态 |
| `conflicts`, `detected_conflicts` | 确定性规则检出的冲突代码与结构化说明 |

### 支持的非可互换来源类型（`EvidenceSourceType`）
- `DETERMINISTIC_CV`：MuJoCo 实时确定的 RGB-D 几何、D4 与融合状态。
- `REAL_VLM`：经过结构化 VLM Provider 生成的语义输出（`is_real_vlm=True` 仅限真实在线模型客户端；`FakeStructuredModelClient` 明确标定 `is_real_vlm=False`）。
- `INJECTED_SEMANTICS`：Benchmark 对照或消融条件显式注入的受控语义观测。
- `HEURISTIC_VISION`：传统像素/色度启发式检测器（如 `ChromaCubePresenceDetector` / `HeuristicSceneVLM`）。
- `RECORDED_REPLAY`：Layer A Benchmark 录制的真实 MuJoCo 帧包回放几何输入。
- `NONE`：`CV_ONLY` 或未提供语义输入。

**不可强转守卫**：`enforce_non_coerced_semantic_source(...)` 与 `EvidenceValidator.assert_valid_source_transition(...)` 严格禁止将 `HEURISTIC_VISION`（例如 `heuristic_local` / `HeuristicSceneVLM` / `ChromaCubePresenceDetector`）或假客户端统计/升级为 `REAL_VLM`（违规将抛出 `SourceCoercionError` 或标记 `SOURCE_COERCION_FORBIDDEN` 并拒绝语义）。

---

## 3. 确定性 EvidenceValidator 规则矩阵（Cases 1–7）

`EvidenceValidator`（`src/cube_relay/perception/validator.py`）只做来源、时效、一致性与前置条件检查，**绝不决定高层 Skill 顺序，也不引入不透明融合模型**：

| 场景 | 触发条件 | 确定性处置规则 |
| :--- | :--- | :--- |
| **Case 1**：CV 未定位，VLM 称可见 | `not geom.cube_detected and semantic.cube_visible` | 记录 `CASE_1_CV_UNLOCALIZED_VLM_CLAIMS_VISIBLE`；强制 `grasp_precondition_satisfied=False`、`can_use_semantic_for_grasp_pose=False`，禁止合成抓取位置 |
| **Case 2**：CV 已完整验证 54/54，单帧 VLM 称有遮挡/不可见 | `geom.cv_54_verified and (not sem.cube_visible or sem.occluded_regions or sem.information_gaps)` | 记录 `CASE_2_CV_FULL_54_VLM_REPORTS_OCCLUSION`；设置 `preserve_verified_cv_fusion=True`，**严禁清空或降级已验证的 54/54 历史融合状态** |
| **Case 3**：本体状态显示已释放，VLM 称仍在夹持 | `not geom.cube_held_in_gripper and _semantic_claims_held(sem)` | 记录 `CASE_3_PROPRIOCEPTION_RELEASED_VLM_CLAIMS_HELD`；保持 `robot_holding_cube=False`（以机械臂真实本体状态为准，禁止 VLM 覆写） |
| **Case 4**：VLM 称物体可抓取，但 RGB-D 无有效位姿 | `(not geom.pose_valid or not geom.rgbd_valid) and _semantic_claims_graspable(sem)` | 记录 `CASE_4_NO_VALID_RGBD_POSE_VLM_CLAIMS_GRASPABLE`；强制 `allow_grasp_generation=False` 与 `grasp_precondition_satisfied=False`，禁止生成抓取动作 |
| **Case 5**：CV 存在不确定性，VLM 提供合理解释 | `(geom.unknown_count > 0 or geom.conflict_count > 0 or not geom.state_valid) and _semantic_explains_occlusion(sem)` | 设置 `uncertainty_explained_by_semantics=True`，在 `advisory_notes` 添加 `CASE_5_UNCERTAINTY_WITH_OCCLUSION_EXPLANATION`；同时保留 CV 不确定性与 VLM 解释供 Agent 选择补充观察或保守等待 |
| **Case 6**：VLM 结果关联旧帧或超时过期 | `semantic` 的 `observation_id` / `(camera_id, frame_id)` 不匹配当前 Bundle，或 `age_sec > max_semantic_age_sec` | 记录 `CASE_6_STALE_SEMANTIC_FRAME_MISMATCH` / `CASE_6_STALE_SEMANTIC_EXPIRED`；强制 `is_stale=True`、`semantic_rejected=True`、**清除 `semantic_passed_to_agent=None`**，禁止将旧帧冒充当前帧 |
| **Case 7**：VLM Provider 超时或故障 | `vlm_requested and (vlm_timed_out or vlm_error_code or sem is None)` | **独立安全控制与急停不受阻塞 (`safety_controls_unblocked=True`)**；记录 `CASE_7_VLM_PROVIDER_TIMEOUT_OR_ERROR`。仅当 `allow_cv_only_on_vlm_failure=True` 时显式记录 `fallback_source="CV_ONLY_FALLBACK"` 退回 `CV_ONLY`，否则按 fail-closed 标记 `BLOCKED` |

---

## 4. LIVE 主链与遗留模块边界规整

1. **移除 LIVE Skill 内部遗留 Agent 嵌套**：
   - 将原 `embodied/vlm.py` 中的饱和度像素检测剥离为 `ChromaCubePresenceDetector`（明确属性 `source_type="HEURISTIC_VISION"`, `is_real_vlm=False`），`HeuristicSceneVLM` 保留为显式 Legacy 子类。
   - 在 `embodied/failure_aware_v6.py` 抽离低层确定性重试函数 `run_bounded_grasp_retry(...)`（与 `FailureAwareSkillAgent.run` 共用 `_BoundedGraspRetryExecutor` 循环，消除重复）。
   - `SimulationSession._execute_plan_step("place_and_release")`、`MuJoCoEmbodiedBackend.task_regrasp` 与 `SixFaceActiveInspector` 统一改为调用 `run_bounded_grasp_retry(..., presence_detector=ChromaCubePresenceDetector())`，并在 `SkillExecutionState.subroutine_provenance` / `causal_refs` 中记录 `HEURISTIC_VISION` 与 `subroutine_uses_real_vlm=False`。
   - `VLMAgentPlanner`、`SkillBasedGraspAgent`、`FailureAwareSkillAgent`、`OpenAICompatibleSceneVLM`、`GeminiTaskPlanner`、`EmbodiedTaskAgent` 均显式标注 `architecture_role="LEGACY_EXPERIMENT"` 并完整保留向后兼容接口。
2. **UI/API 配置一致性同步**：
   - `SimulationSession.set_planner_mode` 现支持 `model`、`use_vlm_perception` 与 `guide_mode` 参数；`api/main.py` 在收到相应指令字段时透传。
   - 当 `use_vlm_perception=False` (`CV_ONLY`) 时，`_sync_dual_model_agent_state` 明确将 `perception_model_provider=None`、`perception_model_name="DISABLED(CV_ONLY)"`、`perception_connected=False`、`latest_semantic_observation=None`，避免误报感知模型处于激活状态。
3. **全链路因果与追溯关联（Trace Correlation）**：
   - 每次决策生成统一关联 `session_id` / `mission_id` / `decision_id` / `evidence_bundle_id` / `request_id` / `prompt_sha256` / `skill_execution_id` / `observation_id` / `frame_id`。
   - 追溯记录**仅标记 `semantic_provided_to_agent`**（即 Agent Prompt 是否收到了经过 Validation 的 VLM 语义对象），严禁把单一在线轨迹的“语义在场”等价写成“VLM 因果决定了该动作”；真正的因果归因必须依赖 M4-D 的 `VLM_ABSENT` / `VLM_SWAPPED` / `VLM_CONTRADICTORY` / `CV_ONLY vs CV_VLM` 对照实验。
   - `ArtifactExporter` 在会话存在 `evidence_bundles` 时自动写出 `evidence_bundles.jsonl` 并纳入 `manifest.json` SHA-256 校验，兼容全部历史运行目录与快照导出。
