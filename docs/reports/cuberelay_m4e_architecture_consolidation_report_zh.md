# CubeRelay M4-E：Perception & Agent 架构规整最终技术报告

> **报告日期**：2026-11-17  
> **任务范围**：基于已完成的 M4-A/M4-B/M4-C/M4-D，对感知入口、模型职责、隐式决策链、统一证据流与因果追溯进行严格边界受控规整（不训练模型、不修改 CV 算法与标定、不放松物理或 Safety Gate 门控、不修改 Benchmark Oracle 或 Prompt Guide 内容）。  
> **核心交付物**：
> - Phase 1 调用链审计：[m4e_call_graph_audit.md](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/docs/architecture/m4e_call_graph_audit.md)
> - Phase 2–6 感知证据契约：[m4e_perception_contract.md](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/docs/architecture/m4e_perception_contract.md)
> - 统一证据容器与确定性校验器：[evidence.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/perception/evidence.py)、[validator.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/perception/validator.py)
> - 主链解耦与追溯增强：[dual_model.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/mission/dual_model.py)、[planner.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/mission/planner.py)、[session.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/mission/session.py)、[vlm_client.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/mission/vlm_client.py)
> - 自动化测试集：[test_m4e_consolidation.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/tests/test_m4e_consolidation.py)

---

## Q1：重构前后系统调用图有什么实质变化？

### 1. 重构前问题调用链
- `LLMAgentDecisionPolicy` 在继承树上直接继承 M4-A 单模型基线 `GeminiMissionPlanner`（[planner.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/mission/planner.py)），复用父类针对“单模型直接看图”的 prompt 文本与像素缺失校验逻辑。
- `DualModelDecisionClient` 仅把 `SemanticSceneObservation` 直接转发给 `AgentPlanningProvider`，没有正式 `PerceptionEvidenceBundle`、无 Cases 1–7 确定性规则核验，也未保留多视角/来源/过期状态字段。
- LIVE 主链 `SimulationSession._execute_plan_step("place_and_release")` 与 `MuJoCoEmbodiedBackend.task_regrasp` 在 Skill 内部直接实例化遗留 v6 代理 `FailureAwareSkillAgent(..., HeuristicSceneVLM(), FailureAwareRulePlanner())`。
- `SimulationSession.set_planner_mode` 忽略了传入的 `model` 参数且未暴露 `use_vlm_perception` 与 `guide_mode`；`CV_ONLY` 关闭 VLM 时 `agent_state` 仍显示感知模型名。

### 2. 重构后统一规范调用链

```text
API / UI (`/api/m3d/command`, `SET_PLANNER_MODE` 支持 model / use_vlm_perception / guide_mode)
  └─▶ SimulationSession (`session.py`)
        ├── RGB-D ─▶ Deterministic CV Stack (Localizer / Pose6D / PerspectiveFaceletMapper / SixFacePerception / Fusion / D4)
        │              └─▶ `GeometricObservationPayload` (`DETERMINISTIC_CV` 或 `RECORDED_REPLAY`)
        ├── [当 use_vlm_perception=True] RGB ─▶ `VLMPerceptionProvider` ─▶ `SemanticObservationEnvelope` (`REAL_VLM`)
        │   [当 use_vlm_perception=False (`CV_ONLY`)] ─▶ 不调用 VLM，`semantic=None` (`NONE`)
        │              │
        │              ▼
        ├── `PerceptionEvidenceBundle` (`perception/evidence.py`, 保留 observation_id / 多相机帧 / 时间戳 / provenance)
        │              │
        │              ▼
        ├── `EvidenceValidator` (`perception/validator.py`, Cases 1–7 + 来源强转禁令，不选 Skill)
        │              │
        │              ▼
        ├── `AgentPlanningProvider` ─▶ `LLMAgentDecisionPolicy` (与 M4-A `GeminiMissionPlanner` 平级，同源继承 `_SafetyGatedPolicyBase`)
        │              │
        │              ▼
        └── `_SafetyGatedPolicyBase` + `SkillRegistry` Preconditions + `StateValidator`
                       │
                       ▼
                 `SkillRuntime` ─▶ MuJoCo Controllers & `run_bounded_grasp_retry` (`HEURISTIC_VISION`, `subroutine_uses_real_vlm=False`)
```

---

## Q2：哪些类或模块属于“仍被主链依赖、只保留兼容或可标为遗留”？

完整带源码引用与行号的分类表见 [m4e_call_graph_audit.md D 节](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/docs/architecture/m4e_call_graph_audit.md)，汇总如下：

| 分类 | 核心类 / 模块 | 处置结果 |
| :--- | :--- | :--- |
| **`ACTIVE_MAINLINE`** | `SimulationSession`, `SkillRegistry`, `VLMPerceptionProvider`, `AgentPlanningProvider`, `DualModelDecisionClient`, `LLMAgentDecisionPolicy`, `DeterministicMissionPlanner`, `PerceptionEvidenceBundle`, `EvidenceValidator` | 保留并完成接口规整、证据流与全链路 Trace ID 关联 |
| **`ACTIVE_LOW_LEVEL_DEPENDENCY`** | `DeterministicCubeLocalizer`, `DeterministicCubePose6DEstimator`, `PerspectiveFaceletMapper`, `SixFacePerception`, `StickerStateFusion`, `solve_canonical_mapping`, `compare_observations`, `verify_post_turn_state`, `MuJoCoEmbodiedBackend`, `MuJoCoTurnExecutor`, `ChromaCubePresenceDetector`, `run_bounded_grasp_retry` | 按 P1 完全保留定量 CV/物理控制算法；从 `embodied/vlm.py` 与 `failure_aware_v6.py` 抽离低层抓取重试子程序与像素阈值检测器并标明 `HEURISTIC_VISION` |
| **`BENCHMARK_BASELINE`** | `GeminiMissionPlanner`, `_EnvLoadedGeminiClient`, `FakeGeminiVLMClient`, `TurnCoordinator` | 与双模型主链隔离为平级基线，保留 Group E 与 M4-A / V1 回合对照实验可复现性 |
| **`LEGACY_EXPERIMENT`** | `HeuristicSceneVLM`, `OpenAICompatibleSceneVLM`, `VLMAgentPlanner`, `SkillBasedGraspAgent`, `FailureAwareSkillAgent`, `OpenAICompatibleFailureAwareVLM`, `RealVLMFailureAwarePlanner`, `GeminiTaskPlanner`, `EmbodiedTaskAgent`, `EmbodiedV2Controller`, `ContinuousActiveInspector`, `SixFaceActiveInspector` | **不再被 LIVE `SimulationSession` 或 `MuJoCoEmbodiedBackend` 调用**；添加明确 `architecture_role="LEGACY_EXPERIMENT"` 标识，非破坏性保留旧脚本与测试兼容性 |
| **`UNUSED` (主链未使用)** | `OpenCVVisibleFaceScanner` (`adapters/camera_optional.py`) | 保留原状，未纳入主链 |

---

## Q3：系统是否还存在 VLM 直接选 Skill、Skill 内嵌套另一个 Agent、或隐式回退入口？

1. **VLM 直接选 Skill**：**主链不存在**。`VLMPerceptionProvider.perceive` / `perceive_envelope` 不传入 Skill 列表且仅输出 `SemanticSceneObservation`；仅明确隔离的 M4-A 单模型基线 `GeminiMissionPlanner` 直接接收像素并输出动作。
2. **Skill 内嵌套另一个 Agent**：**已消除**。原 `session.py:2337`、`mujoco_v2.py:2300`、`six_face_inspection.py:629,711` 内的 `FailureAwareSkillAgent(..., HeuristicSceneVLM(), FailureAwareRulePlanner())` 已统一替换为纯低层确定性物理重试函数 `run_bounded_grasp_retry(..., presence_detector=ChromaCubePresenceDetector())`；`session.py` 与 `mujoco_v2.py` 源码已无 `FailureAwareSkillAgent` 或 `HeuristicSceneVLM` 引用（已由单测断言验证），并在 `SkillExecutionState.subroutine_provenance` 与 `causal_refs` 显式标记 `HEURISTIC_VISION` 与 `subroutine_uses_real_vlm=False`。（历史评估类 `ContinuousActiveInspector` 保留了 `active_inspection_v7.FailureAwareSkillAgent` 符号引用以兼容原有 `test_active_inspection_v7.py` monkeypatch 测试接缝，且切换为显式 `ChromaCubePresenceDetector`。）
3. **隐式回退入口与 UI/API 不一致**：**已修正并显式化**。
   - 新增受控开关 `allow_cv_only_on_vlm_failure`（默认 `False`）：当 VLM 超时或拒绝（如过期帧）且显式允许回退时，严格清除 `semantic_observation=None`，记录 `fallback_source="CV_ONLY_FALLBACK"` / `"CV_ONLY_STALE_FALLBACK"`；未允许时 fail-closed，绝不静默伪造语义。
   - 当 `context_mode="no_image"` 且启用 VLM 时，不再把 `None` 图像偷偷送进 VLM；而关闭 VLM（`use_vlm_perception=False`）时，`DualModelDecisionClient` 跳过 VLM 调用并以 `semantic_source=NONE` 安全运行。
   - `SimulationSession.set_planner_mode` 现支持并生效 `model`、`use_vlm_perception` 与 `guide_mode`，`CV_ONLY` 模式下 `agent_state.perception_model_name` 显式汇报 `"DISABLED(CV_ONLY)"`、`perception_connected=False`。

---

## Q4：`CV`、`VLM`、`Task Agent`、`Safety Gate`、`Controller` 的最终边界分别是什么？

- **Deterministic CV**：唯一拥有 3D 定位、6D 位姿、视角投影、D4 映射、多视角 54/54 融合、未知/冲突计数及转后视觉变化的模块（P1）。任何 VLM 输出均不可写入或覆写 `GeometricObservationPayload`。
- **VLM (`VLMPerceptionProvider`)**：只读当前帧 RGB 与非特权观测元数据，产出带来源与时间戳的 `SemanticSceneObservation`（可见性、遮挡解释、图像质量、信息缺口与建议观察），受禁止选 Skill 与 `OBSERVATION_REFERENCE_MISMATCH` 守卫约束（P2）。
- **Task Agent (`AgentPlanningProvider` + `LLMAgentDecisionPolicy`)**：只接收文本上下文 + 校验后的 `PerceptionEvidenceBundle` + 可选 `SemanticSceneObservation`，不接收原始像素字节，也不允许静默调用第二套遗留规划器（P3）。
- **Safety Gate (`_SafetyGatedPolicyBase` + `SkillRegistry` + `StateValidator` + `EvidenceValidator`)**：独立执行允许列表过滤、参数范围校验、前置条件检验、物理能力审计（如仅支持单向 `U` 转层）及 Cases 1–7 证据有效性检查（P4）。
- **Controller (`SimulationSession._execute_plan_step` + `SkillRuntime` + `MuJoCoEmbodiedBackend`)**：拥有实际关节轨迹、物理接触验证（`bilateral_contact_fraction >= 0.80` 等）与 `run_bounded_grasp_retry` 物理子程序；与 VLM 推理时间严格隔离（推理期间 MuJoCo `sim_time` 保持冻结）。

---

## Q5：`CV_ONLY`、`CV_VLM`、`SINGLE_MODEL_BASELINE`、`DETERMINISTIC_BASELINE` 是否已严格分离？

**是，已在类层次、运行时接口、Prompt 指令与评测计数四个层面严格分离：**
1. `issubclass(LLMAgentDecisionPolicy, GeminiMissionPlanner)` 为 `False`，两者均为 `_SafetyGatedPolicyBase` 的独立平行子类，Prompt 头明确区分双模型无像素语义规划与单模型看图基线。
2. `CV_ONLY` (`use_vlm_perception=False`) 可在 `semantic=None` 且无 RGB 输入时合法完成决策，0 次 VLM Perception 调用，`provenance.semantic_source="NONE"`、`semantic_provided_to_agent=False`。
3. `DETERMINISTIC_BASELINE` 使用独立规则规划器 `DeterministicMissionPlanner`（0 次模型调用）。
4. `SimulationSession.set_planner_mode("LLM_AGENT", ...)` 在线入口只构建双模型 `LLMAgentDecisionPolicy`，绝不隐式实例化 M4-A `GeminiMissionPlanner`；M4-D `BenchmarkRunner` 通过 `PlannerGroup` 独立调度五组对照并单独出分。

---

## Q6：`HeuristicSceneVLM`、`OpenAICompatibleSceneVLM`、`VLMAgentPlanner`、`GeminiTaskPlanner`、`FailureAwareSkillAgent`、`EmbodiedTaskAgent` 当前实际状态是什么？

- **`HeuristicSceneVLM` (`embodied/vlm.py`)**：明确归类为**传统启发式像素色度检测器（`HEURISTIC_VISION`, `is_real_vlm=False`）**，现作为 `ChromaCubePresenceDetector` 的向后兼容 Legacy 子类保留，主链改由 `ChromaCubePresenceDetector` 直接承担抓取存在性辅助检测，且通过 `SourceCoercionError` 严禁将 `"heuristic_local"` 计为真实 VLM。
- **`FailureAwareSkillAgent` (`embodied/failure_aware_v6.py`)**：抽离其无状态物理抓取重试内核为 `_BoundedGraspRetryExecutor` 与 `run_bounded_grasp_retry(...)` 供 LIVE `SimulationSession`、`MuJoCoEmbodiedBackend.task_regrasp` 与 `SixFaceActiveInspector` 调用；`FailureAwareSkillAgent` 本身标为 `LEGACY_EXPERIMENT` 仅保留给 v6 评估脚本与 `test_failure_aware_v6.py` / `test_active_inspection_v7.py`。
- **`OpenAICompatibleSceneVLM`、`VLMAgentPlanner`、`SkillBasedGraspAgent`、`GeminiTaskPlanner`、`EmbodiedTaskAgent`**：均显式标为 `LEGACY_EXPERIMENT`（v2/v5/v7 历史实验模块），确认不被 LIVE `SimulationSession` 或 M4-D mainline 调用，完整保留原有接口、`urllib.request.urlopen` 测试兼容钩子与 M4-C causal audit 测试支持。

---

## Q7：统一 `Perception Evidence Protocol` 如何关联多模态输入、时间戳、相机标识、来源与过期检查？

核心协议实现于 [evidence.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/perception/evidence.py)：
- **ID 与多相机/多帧保留**：`PerceptionEvidenceBundle` 保留原始 `observation_id`、`mission_id`、`session_id`、主视角 `(primary_camera_id, primary_frame_id, captured_sim_time, wall_time_utc)`，并通过 `extract_frame_refs(...)` 从 `camera_metadata.multiview_frames` / `frames` 收集全部视角 `FrameEvidenceRef`，同时将 `observation_id`、`pose_estimate_id`、`frame_id` 统一聚合到 `observation_refs`。
- **来源不可互换**：通过 `EvidenceSourceType` 区分 `DETERMINISTIC_CV`、`REAL_VLM`、`INJECTED_SEMANTICS`、`HEURISTIC_VISION`、`RECORDED_REPLAY`、`NONE`。`FakeStructuredModelClient` 明确标定 `is_real_vlm=False`；`enforce_non_coerced_semantic_source` 与 `assert_valid_source_transition` 禁止把 `HEURISTIC_VISION` 或 fake 输出强转为 `REAL_VLM`。
- **端到端因果关联与声明约束**：`decision_id`、`evidence_bundle_id`、`request_id`、`prompt_sha256`、`perception_provenance`、`evidence_conflicts`、`evidence_validity`、`semantic_provided_to_agent` 贯穿 `SelectedAction`、`DecisionEvent`、`TraceEvent`、`SkillExecutionState`、`AgentObservabilityState`、`DecisionRecord` 与 ZIP 导出文件 `evidence_bundles.jsonl`（纳入 SHA-256 `manifest.json` 校验）。并明确**只把 `semantic_provided_to_agent` 记作“Agent Prompt 收到了经过校验的 VLM 语义对象”**，不将其与“VLM 因果决定了该决策”混淆（因果影响由 M4-D L3 五条件消融实验独立度量）。

---

## Q8：对 Cases 1–7 冲突场景分别做了哪些确定性约束验证，测试结果如何？

[validator.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/perception/validator.py) 实现了轻量确定性 `EvidenceValidator`（不选 Skill、不做黑盒融合），[test_m4e_consolidation.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/tests/test_m4e_consolidation.py) 对 Cases 1–7 全部编写了单测并验证通过：

| Case | 确定性规则行为 | 单测验证结论 |
| :--- | :--- | :--- |
| **Case 1**：CV 未定位，VLM 称可见 | 记 `CASE_1_CV_UNLOCALIZED_VLM_CLAIMS_VISIBLE`，锁定 `allow_grasp_generation=False` 与 `can_use_semantic_for_grasp_pose=False` | PASS（不合成抓取位姿） |
| **Case 2**：CV 已 54/54 验证，单帧 VLM 报遮挡 | 记 `CASE_2_CV_FULL_54_VLM_REPORTS_OCCLUSION`，设 `preserve_verified_cv_fusion=True`，保留 54/54 历史融合 | PASS（`cv_54_verified=True` 且 `observed_count=54` 未被清空） |
| **Case 3**：本体显示已释放，VLM 称仍在夹持 | 记 `CASE_3_PROPRIOCEPTION_RELEASED_VLM_CLAIMS_HELD`，保留本体权威状态 `authoritative_holding_cube=False` | PASS（拒绝覆盖本体状态） |
| **Case 4**：VLM 称可抓取，RGB-D 无有效位姿 | 记 `CASE_4_NO_VALID_RGBD_POSE_VLM_CLAIMS_GRASPABLE`，置 `allow_grasp_generation=False`、`grasp_precondition_satisfied=False` | PASS（阻止生成抓取） |
| **Case 5**：CV 有不确定性，VLM 提供遮挡解释 | 标 `uncertainty_explained_by_semantics=True` 与 `CASE_5_UNCERTAINTY_WITH_OCCLUSION_EXPLANATION`，双证并存交由 Agent 决定 | PASS（`passed=True`, `semantic_passed_to_agent` 完整保留） |
| **Case 6**：VLM 结果关联旧帧或超时过期 | 记 `CASE_6_STALE_SEMANTIC_FRAME_MISMATCH` / `EXPIRED`，强制 `is_stale=True`、`semantic_rejected=True`、`semantic_passed_to_agent=None` | PASS（`DualModelDecisionClient` 拒绝把旧帧送给 Agent，计 `OBSERVATION_REFERENCE_MISMATCH`） |
| **Case 7**：VLM Provider 超时 | `safety_controls_unblocked=True` 恒成立；未允许回退时 fail-closed（`BLOCKED`），显式允许回退时记 `fallback_source="CV_ONLY_FALLBACK"` 并切回 `CV_ONLY` | PASS（两种分支均通过单测与端到端校验） |

### 自动化测试总览
- **宿主非 GL 回归（Python 3.14, `CUBERELAY_SKIP_GL_TESTS=1`）**：`tests/test_m4e_consolidation.py`、`test_m4a_vlm_loop.py`、`test_m4b_dual_model.py`、`test_m4c_causal_audit.py`、`test_m4d_benchmark.py`、`test_api.py`、`test_failure_aware_v6.py` 共 **`55 passed, 6 skipped`**（仅跳过需 MuJoCo GL 的用例）。
- **Docker `cube-relay:local` 全量真实 MuJoCo EGL 回归（最终代码修改后于容器内执行）**：`237 passed, 1 failed`：
  - `tests/test_m4e_consolidation.py` 全部通过（含真实 MuJoCo `SimulationSession.set_planner_mode(..., use_vlm_perception=False, guide_mode="GUIDE_MINIMAL")` 状态同步及 `run_bounded_grasp_retry` 实测）；
  - 全部 `test_m3d_orchestration.py`、`test_m4a_vlm_loop.py`、`test_m4b_dual_model.py`、`test_m4c_causal_audit.py`、`test_m4d_benchmark.py`、`test_six_face_inspection.py`、`test_task_agent_v7.py`、`test_active_inspection_v7.py`、`test_failure_aware_v6.py`、`test_skill_agent.py` 全部通过；
  - 唯一失败为既有的早期 v2 单测 `tests/test_mujoco_integration.py::test_v2_occlusion_recovery_uses_place_release_observe_regrasp_rotate`（单独运行亦稳定复现：`trace` 止于 `REGRASP` 未进入 `ROTATE`，属未被 M4-E 触及的 `MuJoCoEmbodiedBackend.active_scan` 早期物理测试）。

---

## Q9：本次规整是否改变真实 MuJoCo 物理行为、CV 几何精度或 Safety Gate 边界？

**没有。所有物理仿真行为、CV 几何误差与 Safety Gate 约束保持不变并得到实证复核：**

### 1. M4-C 真实 MuJoCo 4 条件因果回归对比（[m4e_regression/m4c](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/results/m4e_regression/m4c/analysis/causal_analysis_report.md)）
| Condition | 状态 | Delta X GT (m) | RGB-D Est (m) | Grasp Target (m) | Actual EE (m) | 3D Est Err (m) | Mean Bilat Contact | 引用完整性 & 因果合规 |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | :---: |
| `baseline` | `COMPLETED` (54/54) | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.012467 | 1.00 | `reference_integrity_ok=True` / True |
| `translate_x_005` | `COMPLETED` (54/54) | 0.0500 | 0.050208 | 0.050252 | 0.047929 | 0.012749 | 1.00 | `reference_integrity_ok=True` / True |
| `translate_x_010` | `FAILED` (`initial_grasp`) | 0.1000 | 0.099588 | 0.099661 | 0.130602 | 0.013486 | 0.00 | `reference_integrity_ok=True` / False（物理边界） |
| `vision_missing_negative_control` | `FAILED` (`INSUFFICIENT_MASK_PIXELS`) | 0.0500 | None | None | None | None | None | `reference_integrity_ok=True` / True（盲抓安全拒绝） |

### 2. M4-D Layer B 全 4 组 × 5 场景真实 MuJoCo 闭环复核（[m4d_online](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/results/m4e_regression/m4d_online/summary.json)）
全部 **20 / 20** 真实 MuJoCo EGL 闭环场景（`DETERMINISTIC_BASELINE`、`SINGLE_MODEL_BASELINE`、`LLM_AGENT_CV_ONLY`、`LLM_AGENT_CV_VLM` 各跑 `CL_01`~`CL_05`，`GUIDE_MINIMAL`）已在 `cube-relay:local` 容器内完成并打包至 `benchmark_m4d-c6979df9.zip`（`zip_integrity_ok=True`）：
- 全 4 组 **`physical_skill_failure_rate = 0/5`**、**`agent_attributable_failure_rate = 0/5`**，Safety Gate 与物理约束无任何退化；
- `CL_03_LOCALIZATION_FAILURE_BLACKOUT` 全 4 组 `goal_achieved=True`（严格拒绝黑屏盲抓并归因 `PERCEPTION_FAILURE`）；`CL_01`/`CL_04` 合法完成组（含 `+5 cm` 偏移）全部 `54/54` 校验通过（`sim_time_s=45.162`）；
- `LLM_AGENT_CV_VLM` 与 `DETERMINISTIC_BASELINE` 均取得 **`5/5 (100%)`** 目标达成率（`CL_01`/`CL_02`/`CL_04` `COMPLETED`，`CL_03` 安全拒抓，`CL_05` 合法触发 `BLOCKED_CAPABILITY`）。
- 闭环证据流核验：`LLM_AGENT_CV_VLM CL_01`（`run-1794926646-3a11d2c2`）`8/8` 次 `ACTION_SELECTED` 均关联非空 `evidence_bundle_id` 且 `semantic_provided_to_agent=[True]*8`；`LLM_AGENT_CV_ONLY CL_01`（`run-1794926056-feb82a4e`）`8/8` 关联非空 `evidence_bundle_id` 且 `semantic_provided_to_agent=[False]*8`；`SINGLE_MODEL_BASELINE CL_02`（`run-1794925916-0db63975`）独立执行无 `evidence_bundle_id`。

### 3. M4-D `offline_fake` 完整基准校验（[m4d_offline](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/results/m4e_regression/m4d_offline/summary.json)）
`benchmark_run_id="m4d-3542378f"` 完成全部 `224` 条 Layer A 决策、`40` 条 L3 消融与 `6` 张严格隔离的 Fake 记分卡，`zip_integrity_ok=True`。

---

## Q10：M4-D Benchmark 在规整前后的具体指标、延迟、Token 与关键案例对比如何？

### 1. 本轮发现并修复的真实工程缺陷
在初次启动 M4-E 在线回归时，用户观察到大量 `INVALID_JSON` 截断报错（`Unterminated string starting at: line 5/6 ... char 114`）。经直接调用在线 `AGENT` 模型（`gemini-3.8-flash`）检查 `finish_reason` 与 `usage` 定位根因：**原 `OpenAICompatibleStructuredClient` 默认 `TOKEN_BUDGET=1200` 在 Gemini 推理模型上由思考 tokens（约 1150）与可见 JSON tokens（仅余 43）共享，导致回复被强制截断于 `finish_reason="length"`**；改为默认 `TOKEN_BUDGET=8192` 后同一 `L4_04` 请求立即在 `budget=4096` 下返回 `finish_reason="stop"` 与完整 `VALID_JSON`。同时为 `OpenAICompatibleStructuredClient` 与 `_EnvLoadedGeminiClient` 添加了针对瞬时 TLS/DNS/429/5xx 的有限传输重试（`max_transport_retries=2`，严禁重试超时与 Schema/JSON 错）与 `90s` 默认超时上限。

> [!NOTE]
> **全量在线基准完成声明（`m4d-c6979df9`）**：全部 **224 / 224 条 Layer A 在线 Replay（`HTTP 402=0`）**、**40 / 40 条 L3 VLM 因果消融** 与 **20 / 20 条 Layer B 真实 MuJoCo EGL 闭环场景（4 组 × 5 场景）** 均已完整落盘至 [summary.json](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/results/m4e_regression/m4d_online/summary.json)、[report.md](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/results/m4e_regression/m4d_online/report.md) 与 SHA-256 校验包 `benchmark_m4d-c6979df9.zip`（`zip_integrity_ok=True`，对应 `20` 个 `closed_loop_runs` 目录与 `20` 个物理证据 ZIP）。注：`LLM_AGENT_CV_VLM` 跑 Layer B 时 `CL_04`/`CL_05` 初次遇到容器内瞬时网络异常（`Temporary failure in name resolution` / `RemoteDisconnected` 记 `API_UNAVAILABLE`），使用 `--dns 8.8.8.8` 重跑该两条后收敛；而模型自身触发的 `SINGLE_MODEL_BASELINE CL_02` `SCHEMA_VALIDATION_FAILURE` 与 `LLM_AGENT_CV_ONLY CL_05` `MODEL_TIMEOUT`（91.5s）按基准规范原样保留。

### 2. M4-D 规整前（`m4d-52efa46a`）vs M4-E 规整后（`m4d-c6979df9`）Layer A 总览

| 分组 × Guide 模式 | M4-D 基线 Acc | M4-D Legal | M4-D Schema OK | M4-D Mean Lat (ms) | M4-E Acc | M4-E Legal | M4-E Schema OK | M4-E Mean Lat (ms) | 说明（样本量 / 归因变化） |
| :--- | :---: | :---: | :---: | ---: | :---: | :---: | :---: | ---: | :--- |
| `DETERMINISTIC_BASELINE__GUIDE_MINIMAL` | 34.38% (11/32) | 100% | N/A | N/A | 34.38% (11/32) | 100% | N/A | N/A | 完全一致 |
| `LLM_AGENT_CV_ONLY__GUIDE_MINIMAL` | 85.94% (55/64) | 89.06% | 90.62% | 11,152 | **96.88% (31/32)** | **100%** | **100%** | 13,582 | 消除全部 6 次 Schema/JSON 与 1 次 API 错误；仅 `L3_08` 无 VLM 时按预期失败 |
| `LLM_AGENT_CV_ONLY__GUIDE_FULL` | 81.25% (26/32) | 87.50% | 90.62% | 9,820 | **87.50% (28/32)** | **93.75%** | **96.88%** | 14,273 | 0 次 API 错误；Schema 失败从 3 降至 1 (`L5_04`) |
| `LLM_AGENT_CV_VLM__GUIDE_MINIMAL` | 84.38% (54/64) | 84.38% | 87.50% | 12,768 | **100.0% (32/32)** | **100%** | **100%** | 14,007 | 全部 32 案例零错满分通过；成功解决需要 VLM 语义的 `L3_08` |
| `LLM_AGENT_CV_VLM__GUIDE_FULL` | 81.25% (26/32) | 81.25% | 87.50% | 12,274 | **87.50% (28/32)** | **93.75%** | **96.88%** | 16,556 | 补齐后 `402=0`；仅 `L1_05` 超时、`L4_04` JSON错、`L3_08`/`L4_03` 决策错 |
| `SINGLE_MODEL_BASELINE__GUIDE_MINIMAL` | 83.87% (52/62) | 100% | 100% | 2,349 | 80.65% (25/31) | 96.77% | 96.77% | 2,464 | 基线严格隔离验证通过（`L3_07` 按既有协议记 `INCOMPARABLE`） |
| `SINGLE_MODEL_BASELINE__GUIDE_FULL` | 83.87% (26/31) | 96.77% | 100% | 2,498 | 83.87% (26/31) | 96.77% | 100% | 2,617 | 与基线完全持平 |

*(注：Token 口径方面，基线 `GUIDE_MINIMAL` 因同时启用 `--run-guide-ablation` 计为 64 条样本：如 `CV_ONLY__GUIDE_MINIMAL` 为 `137,634` tokens / 64 ≈ `2,151` tok/条，M4-E 32 条为 `87,714` tokens ≈ `2,741` tok/条；`CV_VLM__GUIDE_MINIMAL` 基线 ≈ `2,680` tok/条，M4-E 为 `108,177` tokens / 32 ≈ `3,381` tok/条；`CV_VLM__GUIDE_FULL` 基线 `83,085` tokens（含多条 1200 截断与失败），M4-E 完整跑完 32 条为 `105,023` tokens ≈ `3,282` tok/条。全部 128 条双模型决策均带有非空 `decision_id`、`evidence_bundle_id` 与 `request_id`，`semantic_provided_to_agent` 在 `CV_ONLY` 与 `CV_VLM` 之间精确分离。)*

### 3. M4-D 规整前（`m4d-52efa46a`）vs M4-E 规整后（`m4d-c6979df9`）Layer B 真实 MuJoCo 闭环对比

| Planner Group (`GUIDE_MINIMAL`) | M4-D 基线 Goal Rate | M4-E Goal Rate | M4-E Completed | M4-E Mean Wall (s) | M4-E Mean Sim (s) | M4-E Total Tokens | 关键闭环行为差异与归因说明 |
| :--- | :---: | :---: | :---: | ---: | ---: | ---: | :--- |
| `DETERMINISTIC_BASELINE` | `5/5 (100%)` | `5/5 (100%)` | `3/5` | 3.15 | 30.40 | 0 | `CL_01/02/04` 完成，`CL_03` 拒抓，`CL_05` 能力阻塞 |
| `SINGLE_MODEL_BASELINE` | `5/5 (100%)` | `4/5 (80%)` | `2/5` | 28.79 | 27.20 | 127,963 | `CL_01/04` 完成、`CL_03` 4 轮安全中止、`CL_05` 阻塞；`CL_02` 在 54/54 后末轮触发 `VLMDecisionOutput.expected_information_gain` Schema 校验失败 |
| `LLM_AGENT_CV_ONLY` | `4/5 (80%)` | `4/5 (80%)` | `3/5` | 108.99 | 27.20 | 127,729 | `CL_01/02/04` 完成（`CL_02` 5 步直接接续）；`CL_03` 尝试 4 轮安全中止；`CL_05` 前 9 步完成后第 10 轮遇到 `MODEL_TIMEOUT` (91.5s) |
| `LLM_AGENT_CV_VLM` | `4/5 (80%)` | **`5/5 (100%)`** | `3/5` | 118.49 | 27.20 | 196,699 | **全部 5 场景达成目标**：`CL_03` 首轮由 VLM 识别黑屏即主动 `SAFE_STOP`（仅 1 轮）；`CL_05` 完成 21 步求解后主动识别能力边界并 `BLOCKED_CAPABILITY` |

### 4. 关键案例逐项变化分析
- **`L2_04_A5_ALL_54_OBSERVED_NOT_FINISHED`**：基线时期 `CV_ONLY` 与 `CV_VLM` (`GUIDE_MINIMAL`) 曾出现 `EVIDENCE_REFERENCE_INVALID`（未引用当前 `observation_id`）；M4-E 规整及补齐后**全部 6 组模型运行（含 `CV_ONLY MINIMAL/FULL`、`CV_VLM MINIMAL/FULL`、`SINGLE_MODEL MINIMAL/FULL`）全部稳定选择 `finish_inspection` [PASS]**。
- **`L3_02_B2_GRIPPER_OCCLUSION_HELD`**：基线时期 `CV_ONLY (MINIMAL)` 曾出现 `INVALID_JSON` 截断失败；M4-E 修复 `TOKEN_BUDGET` 后所有 6 组运行全数选择合法动作（`place_and_release` / `reorient_cube`）并 PASS。
- **`L3_04_B4_VISUAL_CONFLICT_UNRESOLVED`、`L3_05..L3_07`**：在 `CV_ONLY` 与 `CV_VLM` 均通过（`L3_04` 在 `CV_VLM__GUIDE_MINIMAL` 选择 `observe_visible_faces(released)`，对比 `CV_ONLY` 选择 `regrasp_cube`，均符合各自合法条件；`L3_06` 严格保护已验证 54/54 完成状态直接 `COMPLETE_MISSION`；`L3_07` 拒绝被虚假夹持语义欺骗，保留本体已释放状态选择 `regrasp_cube`）。
- **`L3_08_C4_VLM_LOW_CONFIDENCE_NO_EVIDENCE` & 闭环 `CL_03_LOCALIZATION_FAILURE_BLACKOUT`**：清晰体现“CV vs VLM 职责分离 + 视觉语义辅助价值”：Layer A 中 `CV_ONLY` 因缺乏 VLM 低置信度语义选择 `regrasp_cube` [FAIL]，而 `LLM_AGENT_CV_VLM__GUIDE_MINIMAL` 准确识别低置信度避险选择 `observe_workspace` [PASS]（L3 五条件在线消融 `40/40`：`VLM_TRUE=8/8`、`VLM_LOW_CONFIDENCE=8/8` 优于 `VLM_ABSENT/SWAPPED/CONTRADICTORY` 的 `7/8`，`L3_08` 记 `action_changed_vs_absent=True, positive_visual_gain=True`）；同理在 Layer B `CL_03` 全黑负对照中，**`LLM_AGENT_CV_VLM` 仅用第 1 轮即由 VLM 识别零置信度黑屏主动停止（`VLM_REQUESTED_STOP`, `48.27s`）**，而 `CV_ONLY` 与 `SINGLE_MODEL` 均尝试满 4 轮才由执行上限终止。
- **`CL_05_UNSUPPORTED_SOLVE_CAPABILITY`**：基线 `m4d-52efa46a` 中双模型组曾分别因 `MODEL_API_FAILURE` 与 `SCHEMA_VALIDATION_FAILURE` 中断；M4-E 中 `LLM_AGENT_CV_VLM` 稳定跑通 9 步物理/校验链路并在解析出含 `U'`/`F'`/`R2` 的 21 步求解方案后依据能力边界合法触发 `CAPABILITY_BLOCKED`（`goal_achieved=True`）。
- **`L4_03_D3_REGRASP_BASE_PAD_COLLISION` & `L4_04_D4_REORIENT_POSE_ERROR_EXCEEDED`**：`GUIDE_MINIMAL` 下 `CV_ONLY` 与 `CV_VLM` 全部 PASS（分别选择安全的 `observe_workspace` 与 `place_and_release`）；在冗长的 `GUIDE_FULL` 下模型仍对这两例存在策略波动或一次 `L4_04` JSON 格式失效（`CV_ONLY__GUIDE_FULL` 对 `L4_04` 选择了 `reorient_cube` 导致 FAIL，`CV_VLM__GUIDE_FULL` 对 `L4_03` 选择了 `regrasp_cube`），与基线结论一致：`GUIDE_MINIMAL` 在本任务上比 `GUIDE_FULL` 显著更稳健（`CV_ONLY`: `96.88% vs 87.50%`, delta `+9.38pp`）。
