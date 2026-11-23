# CubeRelay M4-E Phase 1：完整代码调用链审计（Baseline Before Consolidation）

> 本审计基于 **M4-E 重构前（M4-A/M4-B/M4-C/M4-D 完成基线）** 的实际本地代码静态调用链与运行时测试引用生成，所有文件、符号与行号均对应 M4-E 修改前的代码状态。文中同时标注将在 M4-E Phase 2–6 实施的最小架构修复。

---

## A. 当前 LIVE 调用图（API / UI → Session → Perception → DecisionPolicy → Skill → Controller）

### 1. 实例生命周期与注入关系

```text
FastAPI (`src/cube_relay/api/main.py`)
 ├── `/api/m3d/*`, `/ws/session` ──▶ `get_m3d_session()` (`SimulationSession`, singleton)
 │     ├── 后端 (`_init_backend_sync()`): `MuJoCoEmbodiedBackend` (`src/cube_relay/embodied/mujoco_v2.py`)
 │     ├── 能力注册表: `SkillRegistry()` (`src/cube_relay/mission/skill_registry.py`)
 │     ├── 决策日志 / 轨迹日志 / 实验记录器:
 │     │     `DecisionEventLog`, `TraceEventLog`, `ExperimentRecorder`
 │     ├── CV 感知栈 (由 backend + session 持有):
 │     │     - `DeterministicCubeLocalizer` / `DeterministicCubePose6DEstimator`
 │     │     - `PerspectiveFaceletMapper` / `SixFacePerception`
 │     │     - `StickerStateFusion`, `solve_canonical_mapping`, `compare_observations`, `verify_post_turn_state`
 │     └── Planner (`self.planner`, 由 `SimulationSession.__init__` / `set_planner_mode` 实例化):
 │           ├── `PlannerMode.DETERMINISTIC_PLANNER` ──▶ `DeterministicMissionPlanner`
 │           └── `PlannerMode.LLM_AGENT` ──▶ `LLMAgentDecisionPolicy`
 │                 └── `DualModelDecisionClient` (`src/cube_relay/mission/dual_model.py`)
 │                       ├── `VLMPerceptionProvider(OpenAICompatibleStructuredClient("PERCEPTION"))`
 │                       └── `AgentPlanningProvider(OpenAICompatibleStructuredClient("AGENT"))`
 ├── `/api/m4d/benchmark/*` ──▶ Offline/Online `BenchmarkRunner` (`src/cube_relay/benchmark/runners.py`)
 └── `/session/*` (早期 V1 回合式 API) ──▶ `TurnCoordinator` (`src/cube_relay/agent/coordinator.py`)
```

### 2. Web Console → API → `SimulationSession` 运行时顺序

1. **前端 UI (`web/console/cuberelay_v4.tsx`)**:
   - 通过 `/api/m3d/command` 发送 `SET_PLANNER_MODE`、`SELECT_MISSION`、`RUN_MISSION`、`STOP_MISSION`、`RESET_SCENE` 等指令。
   - **现状缺陷（见 E-6）**：`web/console/cuberelay_v4.tsx` 发起 `SET_PLANNER_MODE` 时发送 `planner_mode` 与可选 `enable_password` / `model`，后端 `_dispatch_m3d_command` (`src/cube_relay/api/main.py:246-253`) 调用 `session.set_planner_mode(pmode, model=model, context_mode=context_mode)`。
   - 鉴权：当 `pmode == "LLM_AGENT"` 时，`_authorize_real_vlm(cmd)` (`src/cube_relay/api/main.py:248-249`) 校验 `CUBERELAY_VLM_ENABLE_PASSWORD`；只有鉴权通过才允许切换到 `LLM_AGENT`。
2. **Mission 启动与主循环 (`SimulationSession.run_mission` → `_run_mission_sync`, `src/cube_relay/mission/session.py:1090,1528`)**:
   - 初始化 `MissionState` 与 `SkillRegistry`，锁定后端 anti-cheat 标志 (`_lock_backend_anti_cheat`, line 512)。
   - 在 **LLM_AGENT (Mode B)** 下每步循环：
     1. `_snapshot_with_current_camera()` / `_render_live_frames()` 更新多视角画面 (`frame_id`, `overhead_b64`, `wrist_b64` 等) 与 `ObservationReference` (`last_observation_ref`)。
     2. `build_agent_observation(camera_id="overhead")` (`session.py:884`) 构造 `AgentObservation`（结构化非特权状态）。
     3. `self.planner.select_next_action(mission=..., scene_state=..., skill_registry=..., observation=obs, latest_image_data_url=..., round_index=...)` 调用 `DecisionPolicy`。
     4. **双模型路径问题（M4-E 前）**：`LLMAgentDecisionPolicy` 直接继承 `GeminiMissionPlanner` (`mission/planner.py:1164`)，复用 `GeminiMissionPlanner.select_next_action` (`planner.py:734`)：
        - 构造文本 prompt（`_build_prompt`，甚至仍包含 `"based on the live MuJoCo camera image"` 字样）。
        - 调用 `DualModelDecisionClient.generate_decision(prompt, rgb_data_url, include_image=...)`。
        - 返回后在 `GeminiMissionPlanner.select_next_action` 内经过参数校验与 `SkillRegistry.check_preconditions` **Safety Gate**。
     5. `_execute_plan_step(step, input_ref)` (`session.py:2182`) 按 `skill_id` 分发到底层控制器与 CV 模块：
        - `observe_top_view`, `inspect_multiview`, `observe_after_turn`
        - `regrasp_cube`, `reorient_cube`, `place_and_release`
        - `check_physical_capability`, `execute_physical_u_turn`
        - `compute_state_and_solve`, `solve_symbolic_cube`, `verify_solution`
     6. `StateValidator`（魔方规则合法性校验）、`SkillRegistry` 前置条件检查、以及底层关节控制器 + 接触验证 (`bilateral_contact_fraction >= 0.80`) 独立于 VLM 执行物理与逻辑门控。

---

## B. CV 调用图（RGB-D → CV → 结构化状态 → Task Agent / Skill）

```text
MuJoCo RGB-D (`MuJoCoEmbodiedBackend.capture_rgbd` / 多视角抓取)
  ├── 三维定位: `DeterministicCubeLocalizer` (`src/cube_relay/embodied/perception_v2.py`)
  ├── 6D 位姿估计: `DeterministicCubePose6DEstimator` (`perception_v2.py`)
  ├── 贴片几何投影: `PerspectiveFaceletMapper` (`src/cube_relay/embodied/facelet_mapping.py`)
  ├── 多面主感知与 D4 轴分配:
  │     - `SixFacePerception` (`src/cube_relay/embodied/six_face_inspection.py:252`)
  │     - `estimate_orientation_from_centers` (`six_face_inspection.py:89`)
  │     - `solve_d4_assignment` (`six_face_inspection.py:181`)
  │     - `held_visible_faces` / `InformationGainViewPlanner` (`six_face_inspection.py:422,446`)
  ├── 规范 D4 映射与多视角融合 (`StickerStateFusion` / `canonical_facelets.py`):
  │     - `solve_canonical_mapping` (`src/cube_relay/embodied/canonical_facelets.py`)
  │     - 54/54 覆盖统计 (`confirmed_count`, `unknown_count`, `conflict_count`, `missing_faces`)
  └── 状态验证与转后复核:
        - `compare_observations` / `verify_post_turn_state` (`src/cube_relay/embodied/visual_turn_loop.py`)
        - `StateValidator` (`src/cube_relay/cube/validation.py`) & Kociemba / `SolverService` (`src/cube_relay/cube/solver.py`)
              │
              ▼
   `SimulationSession.scene_state` & `build_agent_observation()` → `AgentObservation` (纯结构化非特权数值/布尔/贴片状态)
              │
              ▼
   `LLMAgentDecisionPolicy` / `DeterministicMissionPlanner` / `SkillRegistry.check_preconditions`
```

**审计确认**：
- CV 全部定量计算（定位、6D 位姿、D4 映射、贴片颜色、未知/冲突计数、转后视觉变化验证）完全保持确定性，**没有任何分支把 VLM 输出写回 `pose6d`、`confirmed_facelets` 或覆盖 `StateValidator`**。
- 潜在断点：M4-E 前 `build_agent_observation()` 会新生成一条随机前缀 `obs_id`（而非稳定关联 `last_observation_ref.observation_id` / `pose_estimate_id` / `captured_at_sim_sec`），导致跨事件、Evidence、Skill 执行的细粒度时效检查与因果溯源不够显式。

---

## C. VLM 调用图（两条隔离路径 + 遗留路径）

### 1. M4-B / M4-D 双模型主链（LIVE & Benchmark Group B/C）

```text
Live RGB Frame (`latest_image_data_url` + `AgentObservation` 元数据)
  ├── [当 use_vlm_perception=True 且 image 非空]
  │     ──▶ `VLMPerceptionProvider.perceive(obs, image_data_url)` (`src/cube_relay/mission/dual_model.py:207`)
  │           └── `OpenAICompatibleStructuredClient("PERCEPTION")` (或单测/离线 `FakeStructuredModelClient`)
  │           └── 校验 `parsed.observation_id / frame_id / camera_id` 必须匹配当前观测
  │           └── 输出 `SemanticSceneObservation` (`mission/models.py:73`)
  │                 （只含可见性、语义遮挡猜测、图像质量、信息缺口、观察建议，无 Skill 列表）
  ├── [当 Benchmark Layer A 注入语义 / 对照条件]
  │     ──▶ `DualModelDecisionClient.injected_semantics`（受控合成注入或真实回放）
  └── [当 use_vlm_perception=False (`CV_ONLY`)]
        ──▶ 不调用 `VLMPerceptionProvider`，`semantics = None`
              │
              ▼ (M4-E 前直接传递 `semantics`，缺乏统一 Evidence Bundle 与确定性 Validator)
        `AgentPlanningProvider.decide(base_prompt, semantics, evidence_observation_id=...)` (`dual_model.py:242`)
              └── `OpenAICompatibleStructuredClient("AGENT")` (**`image_data_url=None`：纯文本+结构化语义，不接收像素**)
              └── 输出 `AgentActionDecision` (经 `DualModelDecisionClient.generate_decision` 转为 `VLMCallResult`)
              └── 经 `SkillRegistry` Safety Gate 校验后输出 `SelectedAction`
```

### 2. M4-A 单模型研究基线（严格隔离）

```text
Live RGB Frame + `AgentObservation` 文本上下文
  ──▶ `GeminiMissionPlanner.select_next_action(...)` (`src/cube_relay/mission/planner.py:329,734`)
        └── `_EnvLoadedGeminiClient` / `FakeGeminiVLMClient` (`src/cube_relay/mission/vlm_client.py:81,233`)
        └── 单模型直接看图 (`image_data_url`) 并直接选择 Skill + Parameters
        └── 输出 `VLMCallResult` ──▶ 同一套 `SkillRegistry` Safety Gate ──▶ `SelectedAction`
```

**审计确认**：
- `BenchmarkRunner` (`src/cube_relay/benchmark/runners.py:305-330,658`) 与 `scripts/run_m4a_experiments.py` 使用 `GeminiMissionPlanner` 作为单模型基线；`SimulationSession.set_planner_mode` 目前已不会实例化 `GeminiMissionPlanner`（它只实例化 `LLMAgentDecisionPolicy`），但因为 `LLMAgentDecisionPolicy` 在继承树上仍是 `GeminiMissionPlanner` 的子类，导致类职责、prompt 文本和 `VLM_ABSENT`/`no_image` 边界出现耦合（见 E-2 与 E-6）。

### 3. v5 / v6 / v7 遗留感知 / 规划路径

- `SceneVLM` / `HeuristicSceneVLM` / `OpenAICompatibleSceneVLM` (`src/cube_relay/embodied/vlm.py:20-83`)：返回旧版 `SceneSemantics`（表上阈值色度检测 `chroma > 70` 或单提示词 VLM）。
- `SkillRuntime(..., scene_vlm)` + `VLMAgentPlanner` + `SkillBasedGraspAgent` (`src/cube_relay/embodied/skill_agent.py:156,636,668`)：v5 抓取智能体。
- `FailureAwareSkillAgent` + `OpenAICompatibleFailureAwareVLM` + `RealVLMFailureAwarePlanner` (`src/cube_relay/embodied/failure_aware_v6.py:350,474,543`)：v6 失败恢复抓取实验智能体；其 `HeuristicSceneVLM + FailureAwareRulePlanner` 组合被 **LIVE 主链直接以内嵌子代理方式调用**（见 E-3）。
- `GeminiTaskPlanner` + `EmbodiedTaskAgent` (`src/cube_relay/embodied/task_agent_v7.py:117,222`)：v7 独立任务规划实验。

---

## D. 遗留模块依赖分类表

| 模块 / 类 | 所在文件 | 分类 | 实际调用方 / 运行时证据 | M4-E 处置 |
| :--- | :--- | :--- | :--- | :--- |
| `SimulationSession`, `SkillRegistry`, `DecisionEventLog`, `TraceEventLog` | `src/cube_relay/mission/session.py`, `skill_registry.py`, `events.py`, `models.py` | `ACTIVE_MAINLINE` | `api/main.py` (`get_m3d_session`), `benchmark/runners.py`, Web LIVE 控制台 | 规范化 Evidence Bundle、Validator、Trace 关联与配置同步 |
| `VLMPerceptionProvider`, `AgentPlanningProvider`, `DualModelDecisionClient`, `LLMAgentDecisionPolicy`, `DeterministicMissionPlanner` | `src/cube_relay/mission/dual_model.py`, `planner.py` | `ACTIVE_MAINLINE` | `SimulationSession.set_planner_mode(LLM_AGENT)`, `BenchmarkRunner` Group B/C (`tests/test_m4b_dual_model.py`, `test_m4d_benchmark.py`) | 将 `LLMAgentDecisionPolicy` 从 `GeminiMissionPlanner` 继承链解耦，接入 `PerceptionEvidenceBundle` + `EvidenceValidator` |
| `DeterministicCubeLocalizer`, `DeterministicCubePose6DEstimator`, `PerspectiveFaceletMapper`, `SixFacePerception`, `StickerStateFusion`, `solve_canonical_mapping`, `compare_observations`, `verify_post_turn_state`, `MuJoCoEmbodiedBackend`, `MuJoCoTurnExecutor`, `TimedFrames` / `resample_indices` | `src/cube_relay/embodied/perception_v2.py`, `facelet_mapping.py`, `six_face_inspection.py`, `canonical_facelets.py`, `visual_turn_loop.py`, `mujoco_v2.py`, `mujoco_executor.py`, `replay_timing.py` | `ACTIVE_LOW_LEVEL_DEPENDENCY` | `SimulationSession` 执行观察/融合/定位/转后复核/MuJoCo 仿真动作（`test_m3d_orchestration.py`, `test_six_face_inspection.py`, `test_visual_turn_loop.py`） | **遵循 P1 保持定量 CV 算法不变**；将 `mujoco_v2.py:2300` 等内嵌 `FailureAwareSkillAgent` 替换为低层重试 helper |
| `GeminiMissionPlanner`, `_EnvLoadedGeminiClient`, `FakeGeminiVLMClient` | `src/cube_relay/mission/planner.py`, `vlm_client.py` | `BENCHMARK_BASELINE` | `BenchmarkRunner` Group E (`PlannerGroup.SINGLE_MODEL_BASELINE`), `scripts/run_m4a_experiments.py`, `tests/test_m4a_vlm_loop.py`, `tests/test_m4d_benchmark.py` | 保持严格隔离；通过公共 `_SafetyGatedPolicyBase` 与双模型平级共存 |
| `TurnCoordinator` (`agent/coordinator.py`) | `src/cube_relay/agent/coordinator.py`, `api/main.py:44,78,115` | `BENCHMARK_BASELINE` / 早期 V1 会合点 | `/session/*` 早期回合式 API、`scripts/demo_90s.py`, `experiments/collaboration_audit.py`, `experiments/inverse_diagnostics.py`, `tests/test_coordinator.py` | 保留兼容，明确标示仅服务于早期 turn-coordination API/实验，不参与 M4 LIVE mission |
| `HeuristicSceneVLM` (`embodied/vlm.py:24`) | `src/cube_relay/embodied/vlm.py` | 此前混用于 `ACTIVE_LOW_LEVEL_DEPENDENCY` 与 `LEGACY_EXPERIMENT` | 在 LIVE `session.py:2338`、`mujoco_v2.py:2301`、`active_inspection_v7.py:280`、`six_face_inspection.py:630,712` 与 M4-C/legacy 测试中被实例化 | 实际只是 `chroma > 70` 启发式像素阈值检测器！抽离为 `ChromaCubePresenceDetector`（明确 `HEURISTIC_VISION`, `is_real_vlm=False`），`HeuristicSceneVLM` 保留为显式 Legacy 子类/别名 |
| `FailureAwareSkillAgent` & `FailureAwareRulePlanner` (`embodied/failure_aware_v6.py`) | `src/cube_relay/embodied/failure_aware_v6.py` | 此前同时充当 `ACTIVE_LOW_LEVEL_DEPENDENCY`（抓取重试执行器）与 `LEGACY_EXPERIMENT` | 被 LIVE `session.py:2337`、`mujoco_v2.py:2300`、`active_inspection_v7.py:279`、`six_face_inspection.py:629,711` 及 v6 实验调用 | 抽出无 Agent 命名的确定性低层 `run_bounded_grasp_retry(...)` 供 LIVE 主链与底层后端调用；`FailureAwareSkillAgent` 标注 `LEGACY_EXPERIMENT_V6` 并保留兼容（注意 `active_inspection_v7` 单测 monkeypatch 点需保留或单独兼容） |
| `SceneVLM` (`vlm.py:20`), `OpenAICompatibleSceneVLM` (`vlm.py:40`), `OpenAICompatibleFailureAwareVLM`, `RealVLMFailureAwarePlanner`, `FixedBudgetPlanner` (`failure_aware_v6.py`) | `src/cube_relay/embodied/vlm.py`, `failure_aware_v6.py` | `LEGACY_EXPERIMENT` | `scripts/embodied_v2_demo.py`, `scripts/evaluate_failure_aware_v6.py`, `tests/test_failure_aware_v6.py` | **不被 LIVE 主链调用**；补充清晰 Legacy 文档字符串与 provenance 元数据，保留向后兼容与单测运行 |
| `VLMAgentPlanner`, `ConstrainedHeuristicVLMProvider`, `SkillBasedGraspAgent`, `SkillRuntime` (`embodied/skill_agent.py`) | `src/cube_relay/embodied/skill_agent.py` | `LEGACY_EXPERIMENT` (v5) | `scripts/evaluate_skill_agent.py`, `scripts/skill_agent_demo.py`, `tests/test_skill_agent.py`, `tests/test_m4c_causal_audit.py`（anti-cheat 审计） | **不被 LIVE 主链调用**；保留以支持 M4-C causal audit 与 v5 单测，补充 Legacy 标记 |
| `GeminiTaskPlanner`, `EmbodiedTaskAgent`, `RuleTaskPlanner`, `FixedTaskPlanner` (`embodied/task_agent_v7.py`) | `src/cube_relay/embodied/task_agent_v7.py` | `LEGACY_EXPERIMENT` (v7) | `scripts/evaluate_task_agent_v7.py`, `scripts/task_agent_v7_demo.py`, `tests/test_task_agent_v7.py`, `tests/test_six_face_inspection.py` | **不被 LIVE 主链调用**；保留以支持 v7 单测（含 `urllib.request.urlopen` monkeypatch），补充 Legacy 标记 |
| `EmbodiedV2Controller`, `ContinuousActiveInspector`, `SixFaceActiveInspector` | `v2_controller.py`, `active_inspection_v7.py`, `six_face_inspection.py` | `LEGACY_EXPERIMENT` / `BENCHMARK_BASELINE`（历史 v2/v7 消融控制器） | `scripts/evaluate_embodied_v2.py`, `evaluate_active_inspection_v7.py`, `tests/test_embodied_v2.py`, `tests/test_active_inspection_v7.py` | 仅在旧评估脚本与单测使用，`SimulationSession` 不再委托给它们（仅共用底层 CV 类）；保留并在 `active_inspection_v7` 的 `HeuristicSceneVLM` fallback 上清楚标记来源 |
| `OpenCVVisibleFaceScanner` | `src/cube_relay/adapters/camera_optional.py` | `UNUSED` (可选早期适配器) | 无 `src/` / `scripts/` / `tests/` 运行时调用（仅文档提及） | 保持原状（低风险可选模块，不纳入 LIVE 主链） |
| `DeterministicTurnExecutor` / `FailureInjectingExecutor` | `src/cube_relay/embodied/execution.py` | `BENCHMARK_BASELINE`（物理执行契约/测试替身） | `Agent` / `visual_turn_loop` / `mujoco_executor` 的 `ActionRequest`、`ActionFeedback`、`TurnExecutor` 数据契约 | 保留，仅数据契约被 `ACTIVE_LOW_LEVEL_DEPENDENCY` 使用 |

---

## E. 隐式决策入口与一致性检查清单

逐项核对 M4-E Phase 1 E 节要求的 6 个风险点，审计结论如下：

| 检查项 | 审计结果 | 代码位置与证据 | 规划的 M4-E 最小修复 |
| :--- | :--- | :--- | :--- |
| **E-1: VLM 直接选择 Skill?** | **主链未发现，但测试边界不明确** | `VLMPerceptionProvider.perceive` 仅输出 `SemanticSceneObservation`，不传 Skill 列表；但 M4-A 基线 `GeminiMissionPlanner` 直接选 Skill，且 `LLMAgentDecisionPolicy` 继承了它 | 将 `LLMAgentDecisionPolicy` 从 `GeminiMissionPlanner` 继承树解耦，仅共享 `_SafetyGatedPolicyBase` |
| **E-2: 多个 Planner 同时控制一个 Mission?** | **存在架构混淆风险（继承耦合同族）** | `SimulationSession` 每个 Mission 持有一个 `self.planner`，但 `LLMAgentDecisionPolicy(GeminiMissionPlanner)` (`planner.py:1164`) 与 `GeminiMissionPlanner` 共享 `_build_prompt()` 文本与像素缺失校验逻辑，导致 `CV_ONLY` 或 counterfactual 无图调用时被父类 `CAMERA_FRAME_MISSING` 拦截 (`planner.py:782-800`)，且 Model B prompt 中仍含 `"based on the live MuJoCo camera image"` (`planner.py:603`) | 解耦继承层次，为双模型使用明确的无像素语义 Prompt，并由 `DualModelDecisionClient` 显式管理 VLM 开关与 `EvidenceValidator` |
| **E-3: Skill 内部再次调用任务级 Agent?** | **确认存在（实锤缺陷）** | 1) LIVE `SimulationSession._execute_plan_step("place_and_release")` (`session.py:2337-2339`) 调用 `FailureAwareSkillAgent(b, HeuristicSceneVLM(), FailureAwareRulePlanner()).run(self.seed, 15, reset_scene=False)`；<br>2) `MuJoCoEmbodiedBackend.task_regrasp` (`mujoco_v2.py:2300-2302`) 同样内部实例化 `FailureAwareSkillAgent(..., HeuristicSceneVLM(), ...)`；<br>3) `ContinuousActiveInspector.run` (`active_inspection_v7.py:279-281`) 与 `SixFaceActiveInspector` (`six_face_inspection.py:629,711`) 同样直接嵌套该类。虽然 `HeuristicSceneVLM` 只是色度阈值检测、`FailureAwareRulePlanner` 只是确定性抓取重试逻辑，但类名与 `Agent` 抽象掩盖了其真实性质，造成“Skill 内嵌套另一个 Agent 和 VLM”的严重架构污染 | 在 `failure_aware_v6.py` 抽离纯粹的确定性低层物理重试函数 `run_bounded_grasp_retry(...)` + `vlm.py` 抽出 `ChromaCubePresenceDetector`（明确标记 `HEURISTIC_VISION`, `uses_real_vlm=False`），`session.py` 与 `mujoco_v2.py` 改为调用该确定性低层 helper，并在 `ExecutionState`/日志显式记录子程序来源 `HEURISTIC_VISION`；`FailureAwareSkillAgent` 保留为显式 `LEGACY_EXPERIMENT_V6` 供历史脚本与单测兼容 |
| **E-4: 历史 Provider 覆盖主链感知结果?** | **未覆写 54/54 状态，但无来源隔离与反冒充检查** | `HeuristicSceneVLM` 仅在抓取/放回子程序内部检查 `table_presence`，不写入 `StickerStateFusion`；但缺乏统一 Evidence 协议与来源校验，外部测试或误配置仍可能把启发式或注入对象混作真实 VLM | 新增 `EvidenceSourceType` 枚举与 `EvidenceValidator` 强制来源不可随意转换（禁止 `HEURISTIC_VISION` 标记为 `REAL_VLM`），并保护已融合 CV 54/54 与机械臂本体状态不被单帧 VLM 推翻 |
| **E-5: 默认回退策略隐式改变决策来源?** | **确认存在细节缺陷** | 1) 当 `LLMAgentDecisionPolicy(..., context_mode="no_image")` 被调用时，`DualModelDecisionClient.generate_decision(..., include_image=False)` (`dual_model.py:324`) 传 `rgb_data_url=None` 却依然调用 `VLMPerceptionProvider.perceive(obs, None)`；<br>2) `VLMPerceptionProvider` 返回 `None`（超时/解析错）时，仅记为决策级失败或走 `allow_deterministic_fallback`，缺乏专门的 VLM 超时/降级到 `CV_ONLY` 的显式受控开关和证据流标记；<br>3) 单 frame 过期的 VLM 语义没有单独记录为 `stale` | 新增受控字段 `allow_cv_only_on_vlm_failure: bool = False`，确保明确允许降级或关闭 VLM 时显式记录 `fallback_used` 与 `perception_provenance`（例如 `NONE` / `CV_ONLY_FALLBACK`），不允许隐式伪装 |
| **E-6: UI / API 配置与实际运行 Provider 不一致?** | **确认存在不一致** | 1) `api/main.py:246-253` 向 `session.set_planner_mode(pmode, model=model, context_mode=context_mode)` 传入 `model`，但 `SimulationSession.set_planner_mode` (`session.py:843-882`) 完全忽略了 `model` 参数，也未暴露显式 `use_vlm_perception` 与 `guide_mode` 开关；<br>2) `_sync_dual_model_agent_state` (`session.py:828-841`) 在 `use_vlm_perception=False` (`CV_ONLY`) 时仍填报 `perception_model_name`；前端可能误以为感知模型正在参与决策 | `set_planner_mode` 显式支持 `use_vlm_perception`、`guide_mode`（缺省兼容既有 3 参签名）并把有效参数同步到 `agent_state`；当 `use_vlm_perception=False` 时，`agent_state` 明确标示 VLM 已禁用而非展示活跃感知模型 |

---

*Audit completed before M4-E code modifications; Phases 2–6 apply these minimal targeted fixes without altering CV geometry, safety gates, physical thresholds, or benchmark oracles.*
