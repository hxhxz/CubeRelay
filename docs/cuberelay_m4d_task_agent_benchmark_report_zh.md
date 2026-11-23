# CubeRelay M4-D：Task Agent Capability Benchmark 评估与实验报告

> **评估基准版本**：`m4d.v1` | **核心真实实验 Run ID**：`m4d-52efa46a` | **日期**：2026-11-17
> **严格红线声明**：本阶段**未引入** Improvement Agent、RSI 自改进机制或模型训练；**未放宽** M4-C 物理接触阈值、控制器或 `audit_only_poses.csv` 真值访问边界；**未将任何 Fake Provider 结果计入真实 Agent 榜单**。

---

## 一、任务范围与代码/实验资产审计结论（Section II 7 项排查）

在编写 Benchmark 之前，对仓库既有架构（`DecisionPolicy`、`DeterministicMissionPlanner`、`LLMAgentDecisionPolicy`、`GeminiMissionPlanner`、`VLMPerceptionProvider`、`AgentPlanningProvider`、`DualModelDecisionClient`、`SkillRegistry`、`SimulationSession`、M4-C 实验导入与导出链路）完成系统审计：

| 审计检查点 | M4-C 遗留现状与问题 | M4-D 工程整改与控制措施 |
|---|---|---|
| 1. Prompt 是否直接提供固定八步扫描顺序 | `GeminiMissionPlanner._build_prompt` 的 `mission_guide` 硬编码固定八步序号流程，`LLMAgentDecisionPolicy` 直接继承。 | 新增 `guide_mode="GUIDE_MINIMAL" \| "GUIDE_FULL"`（[planner.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/mission/planner.py)）：`GUIDE_MINIMAL` 移除固定顺序，仅描述任务目标、完成条件与能力边界；`GUIDE_FULL` 保留作对照消融。 |
| 2. Agent 是否被告知未来 expected info gain | 输出 `response_schema` 含让模型填写的字段名 `"expected_information_gain"`，输入侧未注入未来增益数值。 | 保持输入仅含历史与当前可观测状态，禁止向任何候选项注入预计算 `future_information_gain` / `expected_gain`（由 `test_06` 自动化断言守护）。 |
| 3. `SkillRegistry` 是否真正动态约束动作候选 | 原 `SkillRegistry` 为静态单例列表，难以按测试案例临时禁用或删除某个 Skill。 | 新增 `SkillRegistry.clone(disabled_skills=..., removed_skills=...)`（[skill_registry.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/mission/skill_registry.py#L299)），实时更新 Prompt 候选列表与 Safety Gate 校验边界。 |
| 4. Agent 是否能选择不同合法动作并请求恢复 | 原系统缺少 `SAFE_STOP` / `CAPABILITY_BLOCKED` / `REQUEST_REPLAN` 的独立决策归类；且 `SimulationSession` 在首个物理 Skill 失败时直接中止，无法执行失败后重观察或换路。 | 扩充 `SelectedAction`、`LLMAgentDecisionPolicy`、`AgentPlanningProvider` 与 `SimulationSession(..., allow_agent_failure_recovery=True, reset_before_run=True)`（[session.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/mission/session.py)），支持单步协议停机、能力拒绝及闭环失败恢复。 |
| 5. VLM 语义是否真正进入 Agent 输入 | 原 `DualModelDecisionClient` 强耦合要求 VLM 始终在线，缺少纯净的 `CV_ONLY` 对照通道；且 `need_replan` / `evidence_observation_ids` 在透传时丢失。 | 升级 `AgentPlanningProvider.decide(..., semantics=None)` 与 `DualModelDecisionClient(..., use_vlm_perception=..., injected_semantics=...)`（[dual_model.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/mission/dual_model.py)），同时提供 `VLM_TRUE / ABSENT / SWAPPED / CONTRADICTORY / LOW_CONFIDENCE` 五条件消融注入。 |
| 6. Agent 是否可访问未来 Observation 或隐藏真值 | M4-C 导出了 `audit_only_poses.csv` 与全时序日志，直接回放若不做时间截断可能误泄露未来帧或真值。 | 新增 `BenchmarkAgentInput(extra="forbid")`（[schema.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/benchmark/schema.py#L86)）与 `extract_m4c_replay_slice`（[m4c_importer.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/benchmark/m4c_importer.py#L44)），严格过滤 `sim_time <= cutoff_sim_time` 并永久剥离 `audit_only_poses.csv` 及 `acceptable_decisions` 等 Oracle 字段。 |
| 7. Trace 是否关联模型请求、语义、决策与反馈 | 双模型相位事件缺少精确 token 用量、`prompt_sha256` 及精简脱敏 Prompt 摘要关联。 | 为 `StructuredCall` 与 `DecisionRecord` 补充 `prompt_sha256`、`redacted_prompt_summary`、`observation_id`、`semantic_observation_id`、`token_usage` 与 `safety_validation`，并通过 [exporter.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/benchmark/exporter.py) 进行 SHA-256 清单化打包。 |

---

## 二、Benchmark 双层评估架构与五维能力体系

### 2.1 双层独立评测设计

1. **Layer A：Decision Replay Benchmark（`DecisionReplayRunner`）**
   - 仅评估单步决策质量（不驱动物理执行器），在每个 Case 与重复采样之间重建独立 `SkillRegistry`、`MissionState`、`AgentObservation` 与模型客户端，零隐藏上下文延续。
   - **32 个基准测试集**（[cases.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/benchmark/cases.py)）：
     - **L1 Skill Selection（6 例）**：未定位启动（`A1`）、`reorient` 前置条件检查、参数越界（`yaw 45°` vs `pitch -90°`）、未验证完成误终止防御、已校验完成终止（`A6`）、未实现物理转层识别。
     - **L2 State-Aware Planning（6 例）**：已定位跳过观察（`A2`）、桌面释放态跳过重定位（`A3`）、手持 45/54 仅缺底面（`A4`）、54/54 未校验进 `finish_inspection`（`A5`）、旋转后保持夹持跳过重复 `regrasp`、物理验证中途进度接续。
     - **L3 Perception-Grounded Reasoning（8 例）**：桌面底面遮挡（`B1`）、夹爪遮挡（`B2`）、相机覆盖不足（`B3`）、强光冲突未解决（`B4`）、VLM 遮挡语义 vs CV 未定位冲突（`C1`）、VLM 建议多观察 vs CV 已 54/54 校验冲突（`C2`）、VLM 语义矛盾于机器人本体状态（`C3`）、VLM 低置信无可靠视觉证据（`C4`）。
     - **L4 Failure Recovery（6 例）**：黑屏定位失败重观察（`D1`，M4-C 真实负对照 `run-1794839964-761bfc7c`）、首抓零接触恢复（`D2`，M4-C `+10cm` 包 `run-1794839963-357553ec`）、重抓底座碰撞（`D3`，M4-C `+5cm` 包 `run-1794839960-ea07e812`）、腕部姿态误差超限恢复（`D4`）、所需 Skill 被从 Registry 移除（`D5`）、无任何安全合法恢复 Skill 时阻塞/安全停机（`D6`）。
     - **L5 Generalization（6 例）**：扫完直接校验（`E1`）、仅定位任务目标提前终止（`E2`）、前序未就绪物理 U 转拦截（`E3`）、完整求解遇未建模转层阻塞（`E4`）、传感器临时离线切参数（`E5`）、`+5cm` 偏移重定位而非篡改控制量（`E6`，M4-C `run-1794839960-ea07e812`）。
   - **来源标签隔离**：`8` 个直接切片自 M4-C 真实实验包（标记 `REAL_REPLAY`），`24` 个为受控反事实合成状态（标记 `COUNTERFACTUAL_TEST`）。

2. **Layer B：Closed-loop MuJoCo Benchmark（`ClosedLoopBenchmarkRunner`）**
   - 每个 Episode 在隔离 `SimulationSession` 中真实捕获多相机 RGB-D、运行视觉定位、调用物理技能并经受 M4-C 双边接触阈值校验（`bilateral_contact_fraction >= 0.80`），导出独立 Bundle ZIP。
   - **5 个物理闭环场景**：`CL_01_NORMAL_INSPECT_SEED0`、`CL_02_PARTIAL_SCAN_45_OF_54`（真实物理预置到桌面 45/54 状态再交由被测策略接续）、`CL_03_LOCALIZATION_FAILURE_BLACKOUT`（视觉全黑负对照）、`CL_04_PHYSICAL_SKILL_FAILURE_SHIFT_X005`（`+5 cm` 物理碰撞诱发抓偏故障以验证故障归因隔离）、`CL_05_UNSUPPORTED_SOLVE_CAPABILITY`（完整 `SOLVE_CUBE` 触发能力边界阻塞）。

### 2.2 独立失败归因体系

[attribution.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/benchmark/attribution.py) 严格区分 4 类核心能力归因与 4 类技术/安全态：
- 能力归因：`AGENT_DECISION_FAILURE`、`SKILL_EXECUTION_FAILURE`、`PERCEPTION_FAILURE`、`CAPABILITY_LIMITATION`
- 技术/安全态：`SAFETY_GATE_REJECTION`、`MODEL_API_FAILURE`、`SCHEMA_VALIDATION_FAILURE`、`TEST_HARNESS_FAILURE`
- 在 `CL_04` 中，尽管 `+5cm` 位置扰动导致底层 `regrasp_cube` 多次碰撞/未达接触门槛并最终用尽决策步数，系统正确将其归因为 `SKILL_EXECUTION_FAILURE`，**不误判** Agent 决策错误。

---

## 三、对照组设置、可比性边界与基础设施诊断发现

### 3.1 四组受控对比与两项基础设施事实

- **Group A `DETERMINISTIC_BASELINE`**：传统 CV + `DeterministicMissionPlanner`（规则基线，`DETERMINISTIC_RULE`）。
- **Group B `LLM_AGENT_CV_ONLY`**：传统 CV State + 独立 Planning Model（`gemini-3.8-flash`，不提供 VLM 语义）。
- **Group C `LLM_AGENT_CV_VLM`**：传统 CV State + Perception VLM（`gemini-3.5-flash-lite`）语义观测 + Planning Model（`gemini-3.8-flash`）。在 8 个 `REAL_REPLAY` 主矩阵样本中实时调用在线 VLM 视觉模型；反事实与 5 条件消融通过可控 `SemanticSceneObservation` 注入实现严格控制变量。
- **Group D `SINGLE_MODEL_BASELINE`**：复用 `GeminiMissionPlanner`（单模型直接输入 RGB 图像与 CV 状态，使用 `CUBERELAY_PERCEPTION_*` 凭证调用 `gemini-3.5-flash-lite`，原因已在 `incomparabilities` 与运行配置中显式标注）。由于单模型不存在解耦的 `SemanticSceneObservation` 输入槽，在 `L3_07 (C3)` 与 5 条件 VLM 语义消融中诚实标记为 **`INCOMPARABLE`**，绝不伪造数据。

**评估过程中发现并记录的两项关键基础设施现象**（均保留原始实验证据目录）：
1. **默认 `token_budget=1200` 对推理模型 `gemini-3.8-flash` 的截断效应**：在未调整环境变量前，对 `L1_01..L1_06` 试跑 `LLM_AGENT_CV_ONLY`（归档于 `results/m4d_benchmark_budget1200_l1_sample.json`）时，前 5 题 `10/10` 通过，但 `L1_06_UNIMPLEMENTED_MOVE_RECOGNITION` 两次均在 `10.5s` 出现同一 `INVALID_JSON` 截断。抓包分析确认：Gemini OpenAI 兼容接口将 `max_tokens=1200` 同时用于内部 thinking token（`~1151`）与可见 JSON 输出（仅剩 `42` tokens，`finish_reason="length"`），而单模型侧 `vlm_client.py` 并未传递 `max_tokens`。因此主实验显式通过环境变量将双模型输出预算设为 `CUBERELAY_AGENT_TOKEN_BUDGET=4096`、`CUBERELAY_PERCEPTION_TOKEN_BUDGET=2048`（未改动超时限制 45s）。即便在 `4096` 预算下，复杂案例（如 `L1_06`、`L3_03`、`L3_08`、`L5_04`）仍偶发因长思维链耗尽预算或 JSON 转义异常导致的 `INVALID_JSON`。
2. **`gemini-4-argon` vs `gemini-3.8-flash` 模型行为对比**：在切换 `.env` 前，我们已完整运行了 `gemini-4-argon` 的 Layer A 主矩阵 224 条记录（完整保存在 `results/m4d_benchmark_argon_layer_a/`，Run `m4d-7ed9c0c4`）：`gemini-4-argon` 在 `CV_VLM` 下取得了 **`95.3% (61/64)`** 决策恰当率与 **`0` 次 `AGENT_DECISION_FAILURE`**（3 次 45s 超时 `MODEL_API_FAILURE`），在 `CV_ONLY` 下取得 `87.5% (56/64)`（`+7.8%` VLM 增益），但单次平均耗时 `12.4s–13.5s` 且在复杂 L4/L3 消融中多次触及 45s read timeout。切换至 `gemini-3.8-flash` 后（核心统一 Run `m4d-52efa46a`），所有主矩阵、Guide 消融、VLM 因果消融及 MuJoCo 闭环均在同源配置下完整收齐，且无 45s 超时堵塞，但暴露了更高频率的 `SCHEMA_VALIDATION_FAILURE`（如 `INVALID_JSON` 及 `L2_04` 未按严格校验引用当前 `observation_id`）。

---

## 四、核心实验结果汇总（Run `m4d-52efa46a`，无任何 Fake 数据）

本次完整在线基准共采集 **400 条 Layer A 决策**（主矩阵 `224` + L3 VLM 因果消融 `80` + Prompt Guide 消融 `96`）与 **20 个 Layer B 真实 MuJoCo 闭环 Episodes**，ZIP 校验（`verify_benchmark_zip_integrity`）`ok=true`，外键引用完整性检查 `400/400`、`broken_count=0`。

### 4.1 Layer A 主矩阵与 Prompt Guide 消融五维指标表

> **说明**：所有指标均显式保留分子/分母与 95% Wilson 置信区间，五个维度**独立展示，不加权合并为单一总分**。

| 配置组 (`PlannerGroup__GuideMode`) | 数据来源 | N(可比) | 合法动作率 (Legal) | Schema 有效率 | 决策恰当率 (Appropriate, 95% CI) | 禁止动作率 | 证据引用有效率 | L1 | L2 | L3 | L4 | L5 | 均值延迟 (ms) | 总 Tokens |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `DETERMINISTIC_BASELINE__GUIDE_MINIMAL` | `DETERMINISTIC_RULE` | 32 | 100.0% (32/32) | N/A | **34.4%** (11/32) [0.20, 0.52] | 3.1% (1/32) | N/A | 17% (1/6) | **0%** (0/6) | 62% (5/8) | 67% (4/6) | 17% (1/6) | 0 | 0 |
| `SINGLE_MODEL_BASELINE__GUIDE_MINIMAL` | `REAL_ONLINE_MODEL` | 62 (+2 incomp) | **100.0%** (62/62) | **100.0%** (62/62) | **83.9%** (52/62) [0.73, 0.91] | **3.2%** (2/62) | **100.0%** (62/62) | 83% (10/12) | 83% (10/12) | 86% (12/14) | 83% (10/12) | 83% (10/12) | **2349** | 170,673 |
| `SINGLE_MODEL_BASELINE__GUIDE_FULL` | `REAL_ONLINE_MODEL` | 31 (+1 incomp) | 96.8% (30/31) | 100.0% (31/31) | **83.9%** (26/31) [0.67, 0.93] | 9.7% (3/31) | 100.0% (31/31) | 100% (6/6) | 100% (6/6) | 86% (6/7) | 50% (3/6) | 83% (5/6) | 2498 | 85,143 |
| `LLM_AGENT_CV_ONLY__GUIDE_MINIMAL` | `REAL_ONLINE_MODEL` | 64 | 89.1% (57/64) | 90.6% (58/64) | **85.9%** (55/64) [0.75, 0.92] | 14.1% (9/64) | 89.1% (57/64) | 92% (11/12) | 83% (10/12) | 75% (12/16) | **100%** (12/12) | 83% (10/12) | 11152 | 137,634 |
| `LLM_AGENT_CV_ONLY__GUIDE_FULL` | `REAL_ONLINE_MODEL` | 32 | 87.5% (28/32) | 90.6% (29/32) | **81.2%** (26/32) [0.65, 0.91] | 15.6% (5/32) | 87.5% (28/32) | 100% (6/6) | 83% (5/6) | 75% (6/8) | 50% (3/6) | 100% (6/6) | 9820 | 66,991 |
| `LLM_AGENT_CV_VLM__GUIDE_MINIMAL` | `REAL_ONLINE_MODEL` | 64 | 84.4% (54/64) | 87.5% (56/64) | **84.4%** (54/64) [0.74, 0.91] | 15.6% (10/64) | 84.4% (54/64) | 83% (10/12) | 67% (8/12) | 81% (13/16) | **100%** (12/12) | **92%** (11/12) | 12768 | 171,499 |
| `LLM_AGENT_CV_VLM__GUIDE_FULL` | `REAL_ONLINE_MODEL` | 32 | 81.2% (26/32) | 87.5% (28/32) | **81.2%** (26/32) [0.65, 0.91] | 18.8% (6/32) | 81.2% (26/32) | 100% (6/6) | 83% (5/6) | **88%** (7/8) | 50% (3/6) | 83% (5/6) | 12274 | 83,085 |

#### 失败归因精准拆分（主矩阵 `GUIDE_MINIMAL`）

| 配置组 | `NONE (PASS)` | `AGENT_DECISION_FAILURE` | `SCHEMA_VALIDATION_FAILURE` | `MODEL_API_FAILURE` | 关键失误案例剖析 |
|---|---:|---:|---:|---:|---|
| `DETERMINISTIC_BASELINE` | 11 | **21** | 0 | 0 | L2 全败 (`0/6`)，机械返回 `observe_workspace`，`unnecessary_action_rate=43.8%`；`L5_05` 重试离线相机违背禁止规则。 |
| `SINGLE_MODEL_BASELINE` | 52 (+2 incomp) | **10** | 0 | 0 | 在 `L1_05`（已校验完成仍重调 `validate_cube_state`）、`L2_01`、`L3_08`（缺证据时盲目 `regrasp_cube`）、`L4_03`（碰撞后直接 `place_and_release`）、`L5_03`（违前置硬选 `regrasp_cube`）产生真决策失误。 |
| `LLM_AGENT_CV_ONLY` | 55 | **2** | **6** | **1** | **仅 `L3_08`×2 为真实决策失误**（无 VLM 提示导致在低可见画面下盲目重抓）；其余为 `L2_04`×2（只引用 `scan-obs-*` 未同时引用 `obs-l2-04` 触发 `EVIDENCE_REFERENCE_INVALID`）、`L1_06/L3_02/L5_04×2` `INVALID_JSON` 与 1 次 `TIMEOUT`。 |
| `LLM_AGENT_CV_VLM` | 54 | **0** | **8** | **2** | **真实决策零失误（`0/64`）**：只要返回有效 JSON 且未超时，决策 100% (`54/54`) 命中 Oracle！10 次失败全部为工程/接口层故障：`L1_06×2, L3_03, L3_04, L3_08, L5_04` (`INVALID_JSON`)、`L2_04×2` (`EVIDENCE_REFERENCE_INVALID`)、`L2_02, L2_03` (`TIMEOUT`)。 |

### 4.2 L3 VLM 语义五条件因果消融（80 条决策，每 Case 5 条件 × 2 重复）

| 消融条件 | N | 通过数 | 准确率 | 禁止动作率 | 证据引用有效率 | 核心案例行为差异 |
|---|---:|---:|---:|---:|---:|---|
| `VLM_TRUE` | 16 | **16** | **100.0%** | **0.0%** | **100.0%** | 全部通过：`L3_02` 选 `place_and_release`，`L3_04` 选 `observe_visible_faces`，`L3_08` 选 `SAFE_STOP`。 |
| `VLM_ABSENT` | 16 | 13 | 81.2% | **12.5%** (2/16) | 93.8% | `L3_08` 两次退化为危险盲抓 `regrasp_cube [FAIL]`；`L3_02` 一次偏移至 `reorient_cube`、一次 `INVALID_JSON`；`L3_04` 偏移至 `regrasp_cube`。 |
| `VLM_SWAPPED` | 16 | 14 | 87.5% | **12.5%** (2/16) | 100.0% | 收到置换的非低置信语义后，`L3_08` 两次误选 `regrasp_cube [FAIL]`（`misleading_semantic_susceptibility=12.5%` 含 SWAPPED+CONTRADICTORY）。 |
| `VLM_CONTRADICTORY` | 16 | 14 | 87.5% | **12.5%** (2/16) | 100.0% | 在矛盾高置信语义干扰下，`L3_08` 被诱导误选 `regrasp_cube [FAIL]`；而在 `L3_07 (C3)` 下仍正确遵守本体状态选 `regrasp_cube [PASS]`。 |
| `VLM_LOW_CONFIDENCE` | 16 | 12 | 75.0% | **0.0%** | 75.0% | `L3_08` 两次均安全触发 `SAFE_STOP [PASS]`（0 危险动作）；剩余 4 次失败为 `L3_02`、`L3_03` 上的接口超时 / 连接断开（`MODEL_API_FAILURE`）。 |

- **VLM 因果指标（来自 `LLM_AGENT_CV_VLM__GUIDE_MINIMAL` Scorecard）**：
  - `correct_decision_change_rate` = **`18.75% (3/16)`**（在有效非故障对比对中，引入真实 VLM 实质改善决策的比例）
  - `visual_dependency_score` = **`37.50% (6/16)`**（移除 VLM 后动作发生可观察变化比例，集中于 `L3_02`、`L3_04`、`L3_08`）
  - `misleading_semantic_susceptibility` = **`12.50% (4/32)`**（`SWAPPED` / `CONTRADICTORY` 对 `L3_08` 诱导违禁）

### 4.3 Prompt Guide 消融结论（`GUIDE_FULL` vs `GUIDE_MINIMAL`）

- **`LLM_AGENT_CV_ONLY`**：`GUIDE_MINIMAL` 准确率 `85.9%` vs `GUIDE_FULL` `81.2%`（**`+4.7%`**），`L4` 从 `100% (12/12)` 跌至 `50% (3/6)`；具体表现为 `GUIDE_FULL` 下 `L4_04` 退回重复 `reorient_cube [FAIL]`（`unsafe_retry_rate` 从 `0%` 升至 `33.3%`）。
- **`LLM_AGENT_CV_VLM`**：`GUIDE_MINIMAL` `84.4%` vs `GUIDE_FULL` `81.2%`（**`+3.1%`**），`L4` 同样从 `100%` 跌至 `50%`，证明硬编码八步扫描指南虽然能略微加速简单场景输出格式稳定（`L1`、`L5` 减少思维链截断），但在故障恢复时造成序列惯性偏差。
- **`SINGLE_MODEL_BASELINE`**：`GUIDE_FULL` 在 `L1`、`L2` 提升至 `100%`，但 `L4` 从 `83%` 跌至 `50%`（在 `L4_03/L4_04/L4_05` 出现盲目重抓/重转或调用已移除技能），总准确率持平（`83.9%` vs `83.9%` Comparable，脚本总体 `81.2%`）。

### 4.4 Layer B：真实 MuJoCo 闭环实验结果（20 Episodes）

| 场景 | Group A (`DETERMINISTIC`) | Group D (`SINGLE_MODEL`) | Group B (`LLM_AGENT_CV_ONLY`) | Group C (`LLM_AGENT_CV_VLM`) |
|---|---|---|---|---|
| `CL_01_NORMAL_INSPECT_SEED0` | `COMPLETED` (3步, 3.79s) `NONE` | `COMPLETED` (8步, 28.20s, 29.5k tok) `NONE` | `COMPLETED` (8步, 75.92s, 24.5k tok) `NONE` | `COMPLETED` (8步, 108.06s, 42.4k tok) `NONE` |
| `CL_02_PARTIAL_SCAN_45_OF_54` | `COMPLETED` (**重跑全部步骤** `obs_ws -> scan -> val`, 3.36s) | `COMPLETED` (**跳过前3步**, 从 `regrasp` 接续 5步, 18.10s) | `COMPLETED` (**跳过前3步**, 5步直达校验, 45.43s) | `COMPLETED` (**跳过前3步**, 5步直达校验, 70.24s) |
| `CL_03_LOCALIZATION_FAILURE_BLACKOUT` | `FAILED` (1步, 0.11s) `PERCEPTION_FAILURE` | `FAILED` (重试 `obs_ws` **4次**, 9.64s) `PERCEPTION_FAILURE` | `FAILED` (重试 `obs_ws` **2次**后主动 `SAFE_STOP`, 37.22s) `PERCEPTION_FAILURE` | `FAILED` (仅 **`observe_workspace` 1次**即结合 VLM 黑屏语义主动停机, 32.50s) `PERCEPTION_FAILURE` |
| `CL_04_PHYSICAL_SKILL_FAILURE_SHIFT_X005` | `FAILED` (2步中止, 2.91s) `SKILL_EXECUTION_FAILURE` | `FAILED` (14步循环, 盲目连续重抓4次, 54.26s) `SKILL_EXECUTION_FAILURE` | `FAILED` (14步, **每次重抓失败均先 `observe_workspace` 重定位**后再抓且成功旋转1次, 125.00s) `SKILL_EXECUTION_FAILURE` | `FAILED` (14步, **每次重抓失败均先 `observe_workspace` 重定位**后再抓, 190.08s) `SKILL_EXECUTION_FAILURE` |
| `CL_05_UNSUPPORTED_SOLVE_CAPABILITY` | `BLOCKED_CAPABILITY` (5步, 3.54s) `CAPABILITY_LIMITATION` | `BLOCKED_CAPABILITY` (10步正确阻塞, 32.19s) `CAPABILITY_LIMITATION` | `FAILED` (完成9步至 `compute_symbolic_plan` 后遇到 `INVALID_JSON`, 106.66s) `SCHEMA_VALIDATION_FAILURE` | `FAILED` (完成7步至 `finish_inspection` 后遇 `API_UNAVAILABLE`, 96.50s) `MODEL_API_FAILURE` |

---

## 五、核心研究问题（RQ1～RQ6）实证结论

1. **RQ1（Skill Selection）**：在移除固定顺序指南（`GUIDE_MINIMAL`）与未超时/未截断的前提下，双模型 `gemini-3.8-flash`（`CV_VLM` 与 `CV_ONLY`）具备优秀的合法动作与参数选择能力：参数有效率 **`100%`**（`40/40` 与 `44/44`），`CV_VLM` 真决策失误为 `0`，主要瓶颈是长推理偶发 `INVALID_JSON` 及 `L2_04` 遗漏当前 `obs-l2-04` 引用。
2. **RQ2（State-Aware Planning）**：**实证具备且显著超越规则基线**。确定性规划器在 `L2` 全部失败（`0/6`），并在 `CL_02` 真实物理中途状态重跑全流程；而 `CV_ONLY`、`CV_VLM` 与 `SINGLE_MODEL` 在 `CL_02` 均精确跳过了已完成的 `observe_workspace`、`place_and_release` 与首轮 `observe_visible_faces`，以 5 步直接闭环。
3. **RQ3（Perception-Grounded Reasoning）**：**VLM 语义确实因果性地影响了 Agent 决策，但在低阶信息完备的场景中容易被 CV 状态主导**。
   - **正面因果证明**：在 `L3_08 (C4)` 中，面对低置信视觉与未知格表象，`CV_ONLY` 与 `SINGLE_MODEL` 均违禁触发盲目 `regrasp_cube`，而注入 `VLM_TRUE` 或 `VLM_LOW_CONFIDENCE` 的 `CV_VLM` 稳定触发 `SAFE_STOP`（`100% -> 0%` 因果落差）；在 `L3_02 (B2)` 中引导从 `reorient_cube` 切换至 `place_and_release`；在 `L3_04 (B4)` 引导优先消除眩光冲突；在闭环 `CL_03` 中将重观察次数从 `SINGLE_MODEL` 的 4 次、`CV_ONLY` 的 2 次压缩到 **1 次即安全停机**。
   - **局限与风险**：在 `L3_01`、`L3_05`、`L3_06` 中，结构化 `cv_state` + `unknown_by_face` 已足够决定最优动作，VLM 改变率为 0%；而在 `L3_08` 注入 `VLM_SWAPPED`/`VLM_CONTRADICTORY` 时仍诱发 4/32 (`12.5%`) 错误动作。
4. **RQ4（Failure Recovery）**：在 `GUIDE_MINIMAL` 下，双模型 LLM Agent 在 Layer A `L4` 取得 **`100% (12/12)`**（反超 `SINGLE_MODEL` `83%` 与 `GUIDE_FULL` `50%`）。在 Layer B `CL_04 (+5cm 扰动)` 中，双模型表现出**明显优于单模型与确定性基线的物理恢复理性**：单模型盲目原地重抓 4 次，而 `CV_ONLY` 与 `CV_VLM` 在每次 `regrasp_cube` 失败后主动执行 `observe_workspace` 刷新位姿后再抓取，虽因 MuJoCo 底层偏置控制器本身几何限制未能最终翻面成功（归因为 `SKILL_EXECUTION_FAILURE`），但决策过程完全合理。
5. **RQ5（Generalization）**：在 `L5` 目标变更（`E2` 仅定位直接完成）、传感器参数切换（`E5`）、未建模动作拦截（`E3/E4`）和 `+5cm` 偏移场景中达到 `83%～92%` 准确率（显著高于确定性规则 `17%`）；但在长多步闭环 `CL_05` (`SOLVE_CUBE`) 中暴露出工程稳定性风险（`CV_ONLY` 第 9 步 `INVALID_JSON`，`CV_VLM` 第 7 步 `API_UNAVAILABLE`）。
6. **RQ6（Incremental Value）**：
   - **LLM Agent 相对 Deterministic Planner 的增量价值**：体现在**跨状态起点泛化与故障恢复**（Layer A L2 `0% -> 67%～83%`，总决策恰当率 `34.4% -> 84.4%～85.9%`；Layer B `CL_02` 跳过 3 个已完成步骤、`CL_04` 失败后主动重定位而非死循环/直接放弃）。代价是单步延迟从 `0ms` 上升至 `2.3s–12.8s`，且带来 `9.4%–12.5%` 的 JSON/API 工程故障风险。
   - **引入 VLM 相对 CV-Only 的增量价值**：在 `gemini-3.8-flash` 主矩阵上宏观均值差距受 JSON 截断噪声掩盖（`CV_VLM` `84.4%` vs `CV_ONLY` `85.9%`），但在剥离格式截断后，**`CV_VLM` 真决策失误由 `2/64` 降至 `0/64`**，并在早先无截断的 `gemini-4-argon` 上实现了 **`+7.8%` (`95.3%` vs `87.5%`)** 的整体收益；同时在 `L3` 消融中提供了不可替代的低置信安全拦截（`L3_08`）与感知-状态语义一致性检验（`CL_03` 一次停机）。

---

## 六、交付物 C：10 个关键评估问题逐项答复（Q1～Q10）

1. **Q1：当前 Task Agent 到底具备哪些核心能力，尚不具备哪些能力？**
   - **已具备**：动态候选集感知与参数边界遵守（100% 参数合规）；中间进度状态接续（`A2–A6`、`CL_02`）；多任务目标自适应终止（`E2`）；多视角遮挡原因辨析与重观察/重抓切换（`B1/B2/B4`）；物理失败后的主动重定位恢复（`L4`、`CL_04`）；缺失证据时基于 VLM 的保守停机（`C4`、`CL_03`）。
   - **尚不具备/不稳定**：复杂长思考场景下极易触发 `INVALID_JSON`（`token_budget` 与 JSON 转义稳健性不足）；多步长周期闭环的端到端可靠性（`CL_05` 中途受 `INVALID_JSON` 与 `API_UNAVAILABLE` 中断）；对高置信错误 VLM 注入的绝对抗干扰能力（`L3_08` 在虚假高置信下仍被误导）。
2. **Q2：哪些任务成功是由 Prompt 工程或固定引导词驱动的？**
   - `GUIDE_FULL` 中的八步提示虽降低了简单状态（`L1/L5`）的格式截断率（`L1` 在所有组达 `100%`），但它也是造成 `L4` 故障恢复大幅滑坡（`100% -> 50%`）的直接原因——会诱导 Agent 在 `L4_04` 机械重复刚失败过的动作。真正的能力应以 `GUIDE_MINIMAL` 下的表现为准。
3. **Q3：移除固定扫描顺序引导后，Agent 的真实能力变化如何？**
   - `LLM_AGENT_CV_ONLY` 恰当率由 `81.2%` 升至 **`85.9%` (`+4.7%`)**，`LLM_AGENT_CV_VLM` 由 `81.2%` 升至 **`84.4%` (`+3.1%`)**，且 `L4` 故障恢复从 `50%` 飙升至 **`100% (12/12)`**、`unsafe_retry_rate` 从 `33.3%–50.0%` 降至 **`0.0%`**。证明移除固定序列未削弱规划，反而释放了状态与失败反馈推理能力。
4. **Q4：VLM 语义信息是否真实改善了决策？改善体现在哪些场景？**
   - **是**。集中体现在三类仅靠 `unknown_count` 无法区分的场景：**视觉不可信停机**（`L3_08`：VLM 提示盲抓风险后正确 `SAFE_STOP`，`CV_ONLY` 与 `SINGLE_MODEL` 均违禁）、**遮挡成因区分**（`L3_02` 区分夹爪遮挡改选 `place_and_release`、`L3_04` 区分反光冲突选 `observe_visible_faces`）与**闭环早停**（`CL_03` 少重试 1–3 轮）。
5. **Q5：在哪些案例中 VLM 语义被忽略，或在 VLM 错误时反而损害决策？**
   - 当 `cv_state.cube_localized=False`（`L3_05 C1`）或 `cube_state_validated=True`（`L3_06 C2`）时，强结构化状态与前置条件完全主导决策，VLM 被正确“按优先级覆盖”。相反，当外部无有效图像依据且系统人为注入虚假高置信正面语义（`L3_08 VLM_SWAPPED` / `CONTRADICTORY`）时，Agent 信任了错误语义并产生 4/32 (`12.5%`) 违禁重抓动作。
6. **Q6：LLM Agent 与 Deterministic Planner 相比到底赢在什么地方？**
   - 赢在**非线性进度自适应**（Layer A L2：`67%–83%` vs `0%`；Layer B `CL_02` 免重复扫描）与**失败反馈驱动换路**（`CL_04` 重抓碰壁主动先调用 `observe_workspace` 重定位；`E5` 切相机参数），以及**无需为每种异常编写硬编码分支即可在缺少可行动作时主动阻塞/停机**。
7. **Q7：双模型结构（`VLM Perception + LLM Agent`）相比单模型 `GeminiMissionPlanner` 是否具有可验证优势？**
   - **在状态与失败推理深度上占优，但在工程时延、Token 成本与结构化输出稳定率上劣于单模型**。`LLM_AGENT` 系列无 `C3` 不可比盲区、支持多模型语义消融审计、`L4` 达 `100%` 且有效返回 `0 AGENT_DECISION_FAILURE`（`gemini-3.8-flash CV+VLM`）和 `100%`（`gemini-4-argon`）；而 `SINGLE_MODEL_BASELINE`（`gemini-3.5-flash-lite`）以 **5 倍更快延迟（`2.35s` vs `12.77s`）** 和 **100% JSON 成功率** 赢得执行效率，但产生了 10 次真实逻辑判断错误。
8. **Q8：当前系统的主要瓶颈究竟是 VLM 感知、LLM 决策、还是底层物理 Skill？**
   - **端到端闭环物理成败的首要瓶颈仍是底层物理 Skill 与几何位姿容差**（如 `CL_04` 中 `+5cm` 偏移时抓手 `base_pos_pad` 频繁触发非预期接触）；**Agent 在线运行时的首要工程瓶颈是推理模型的输出预算截断/JSON 语法脆弱性与本地网络/API 抖动**（`SCHEMA_VALIDATION_FAILURE` 与 `MODEL_API_FAILURE` 共占 `CV_VLM` 失败的 10/10，闭环 `CL_05` 双双因该层错误提前中止）；Agent 核心状态决策逻辑本身反而是当前链路中最成熟的部分。
9. **Q9：哪些当前失败其实不是 Task Agent 决策问题，而是 Skill / Perception / Capability 问题？**
   - `CL_03` Blackout 失败归因为 `PERCEPTION_FAILURE`（Agent 实际及时停机保护）；`CL_04` `+5cm` 重抓碰撞归因为 `SKILL_EXECUTION_FAILURE`（Agent 正确多次触发重定位，未能翻面源于控制偏差）；`CL_05`、`L4_05`、`L4_06`、`L5_03`、`L5_04` 中的阻塞实为合法物理能力边界 `CAPABILITY_LIMITATION`；主矩阵中 `CV_VLM` 的 `8` 次 `INVALID_JSON/SCHEMA_ERROR` 与 `2` 次 `TIMEOUT` 属于接口封装/模型调用工程层问题而非策略错误。
10. **Q10：如果下一步（M5）引入 Improvement Agent，最先应该评估哪类可控改进，哪些能力目前还不具备改进前提？**
    - **可优先接入且收益最高的方向**（低风险工程/上下文层）：① Prompt 与模型调用参数调优（如依据模型思考消耗动态分配 `max_tokens >= 4096`、加装单次 JSON 语法/观察引用自动纠偏校验，直接修复 `CV_VLM` 主矩阵中全部 8 例与闭环 `CL_05` 的 `INVALID_JSON`）；② 当 `observation_history` 与 `current_observation` 存在历史有效采样时允许引用任一关联 `observation_id`（修复 `L2_04`）。
    - **尚不具备自改进前提的能力**：物理控制参数在线自调优（如修改 `CL_04` 重抓轨迹偏置或力控门槛）与未建模转层技能扩展，因为它们需要闭环物理安全验证包络与人类工程师审签，严禁由 Agent 盲改底层物理参数。

---

## 七、Task Agent 能力评估矩阵

| 能力维度与子能力 | 当前评估结论 | 核心实测证据与限制条件 |
|---|---|---|
| **L1.1 合法 Skill 与参数选择** | **`VERIFIED`** | `VALID_PARAMETER_RATE = 100%`（所有组均 100%）；`GUIDE_FULL` 下 `L1` 全部三组均 `6/6`；`SINGLE_MODEL` 仅在已完成后误重选 `validate_cube_state`。 |
| **L1.2 禁止误终止与缺失能力阻塞** | **`PARTIALLY_VERIFIED`** | 逻辑上能准确识别 `L1_04`/`L1_05`/`L1_06`，但 `gemini-3.8-flash` 在 `GUIDE_MINIMAL` 下 `L1_06` 因思考消耗大触发 `INVALID_JSON`。 |
| **L2.1 状态跳过与中间进度接续** | **`VERIFIED`** | 闭环 `CL_02` 三组 LLM 均精确跳过已完成的定位/放置/初扫直达 5 步完成；Deterministic 重跑全流程；Layer A `CV_ONLY L2=83%`。 |
| **L2.2 多历史场景下证据字段强制引用合规** | **`PARTIALLY_VERIFIED`** | `L2_04 (A5)` 中双模型均倾向引用历史扫描 ID `scan-obs-002` 而漏掉当前 `obs-l2-04`，被严格策略拦截为 `EVIDENCE_REFERENCE_INVALID`。 |
| **L3.1 遮挡与低置信语义识别利用** | **`VERIFIED`** | `L3_02`/`L3_04`/`L3_08` 与 `CL_03` 证明真实 VLM 带来清晰因果决策提升（`VLM_TRUE 100%` vs `VLM_ABSENT 81.2%`）。 |
| **L3.2 对抗虚假/置换语义的鲁棒性** | **`PARTIALLY_VERIFIED`** | 能抵御违反强前置条件/强 CV 的矛盾（`C2/C3` 100%），但在盲区缺乏图像线索时受高置信虚假语义诱导（`C4 SWAPPED/CONTRADICTORY` 违禁率 12.5%）。 |
| **L4.1 失败检测与安全恢复规划** | **`VERIFIED`** | `GUIDE_MINIMAL` 下双模型 Layer A `L4` **`100% (12/12)`**，`CL_04` 展现重抓失败后重定位再抓取的完整推理。 |
| **L4.2 无解物理/感知边界安全停机** | **`VERIFIED`** | `D5/D6`、`CL_03` 均正确主动阻塞或 `SAFE_STOP`；确定性物理重抓失败归因为 `SKILL_EXECUTION_FAILURE`。 |
| **L5.1 任务目标与传感器参数泛化** | **`VERIFIED`** | `E1/E2/E5/E6` 均高稳健通过（`CV_VLM L5=92%`、`CV_ONLY GUIDE_FULL L5=100%`）。 |
| **L5.2 长程多轮复杂求解推理工程可靠性** | **`BLOCKED_BY_INFRASTRUCTURE` / `PARTIALLY_VERIFIED`** | `CL_05` 在 `SOLVE_CUBE` 长程闭环中分别于第 9 步遇 `INVALID_JSON`（`CV_ONLY`）、第 7 步遇 `API_UNAVAILABLE`（`CV_VLM`），且本机 Clash TUN DNS 偶发 `[Errno 8]` 中断需工程重试防护。 |
| **多步连续物理魔方求解 (`R/F/L/B/D` 转层)** | **`NOT_IMPLEMENTED`** | 受限于 M3-D/M4-C 物理夹具建模边界（仅建模单次顺时针 `U` 转动），已在 `L1_06`/`L5_04`/`CL_05` 显式验证阻塞。 |

---

## 八、前端集成、导出验证与全量回归测试记录

1. **Web 控制台与接口验证**：
   - 新增后端接口 `GET /api/m4d/benchmark/runs`、`GET /api/m4d/benchmark/latest`、`GET /api/m4d/benchmark/cases`、`GET /api/m4d/benchmark/export`（[main.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/api/main.py)）。
   - 在控制台 [cuberelay_v4.tsx](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/web/console/cuberelay_v4.tsx) 新增 `Task Agent 评估`（`BENCHMARK`）导航视图及完整 CSS 覆盖（[cuberelay_v4.css](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/web/console/cuberelay_v4.css)），强制展示 `REAL_ONLINE_MODEL` / `REAL_MUJOCO` / `OFFLINE_REPLAY` / `COUNTERFACTUAL_TEST` / `FAKE_PROVIDER` 标签，并通过 `scripts/build_frontend.py --typecheck` 构建产出 `bundle.js`。
   - 重启 `cube-relay` Docker 容器并加载更新后 `.env` 与挂载卷后，实测 `http://127.0.0.1:18000/api/m4d/benchmark/runs` 正常返回 Run `m4d-52efa46a`。
2. **数据导出与安全脱敏验证**：
   - [analyze_m4d_benchmark.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/scripts/analyze_m4d_benchmark.py) 对 [benchmark_m4d-52efa46a.zip](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/results/m4d_benchmark/benchmark_m4d-52efa46a.zip) 运行校验：`ok=true`、`manifest_files_checked=8`、`mismatches=[]`、`secret_hits=[]`、`reference_integrity.ok=true`（`checked_records=400, checked_cases=32`）。
3. **全量回归测试通过（含 MuJoCo GL 真实物理与渲染测试）**：
   - 执行 `/private/tmp/cuberelay-py313/bin/pytest -q tests/test_m4d_benchmark.py tests/test_m3d_orchestration.py tests/test_m4a_vlm_loop.py tests/test_m4b_dual_model.py tests/test_m4c_causal_audit.py tests/test_api.py`：
   - **实测结果**：**`58 passed in 43.24s`**（0 失败，0 跳过，覆盖全部 18 类 M4-D 单元测试、M4-C 历史真实包解析、Fake 严格隔离与防泄漏断言，以及 M3-D/M4-A/M4-B/M4-C/API 全套真实 MuJoCo 端到端测试）。
