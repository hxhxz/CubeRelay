# CubeRelay M4-B：VLM 感知 × 独立 Agent 规划 × MuJoCo 闭环报告

## 1. M4-A 审计结论

- 已实现并测试：真实 MuJoCo RGB、`AgentObservation`、细粒度安全扫描 Skill、
  SkillRegistry Safety Gate、多轮动作反馈、层级 Trace、Agent/Skill UI。
- 真实在线模型证据：`results/m4a_acceptance/` 中 Seed 0 INSPECT 和视觉消融曾成功；
  VERIFY/SOLVE 的早期运行失败，不能算在线通过。
- 仅 Mock/离线覆盖：超时、非法 JSON、非法动作、调用预算、fallback 以及本次新增的双模型
  物理闭环。
- M4-A 缺口：不存在 `SemanticSceneObservation`，单个 `GeminiMissionPlanner` 调用同时看图
  和选 Skill；没有独立的视觉语义来源、Agent Provider 或双模型事件链。

## 2. M4-B 实现

新增 `src/cube_relay/mission/dual_model.py`：

- `VLMPerceptionProvider`：模型 A，只接收真实 RGB data URL 和帧元数据，输出严格
  `SemanticSceneObservation`；prompt 不含 Skill 列表，不能选择动作。
- `AgentPlanningProvider`：模型 B，不接收图像字节，读取 VLM 语义、CV 状态、Mission、
  历史、Skill、前置条件和物理边界，输出严格 `AgentActionDecision`。
- `DualModelDecisionClient`：按“感知完成后再规划”的顺序串联两个独立调用，检查
  observation/frame/camera 引用和 Agent evidence 引用。
- `LLMAgentDecisionPolicy`：实现既有 DecisionPolicy，复用 M4-A 已测试的动作映射、
  参数校验、前置条件和能力阻塞，不直接访问 MjData。

两个模型分别配置 endpoint、provider、model、temperature、timeout、token budget、key；
允许同一供应商，但调用链、Schema、prompt 和 trace 独立。

## 3. 因果闭环与事件

服务器 EGL MuJoCo + 两个独立 Fake Provider 已完成 INSPECT_CUBE：

1. 捕获真实 MuJoCo RGB；
2. 模型 A 生成与 observation/frame 对齐的语义；
3. 模型 B 引用该 observation 并选择 Skill；
4. Safety Gate 校验；
5. 执行 place/release、observe、regrasp、pitch -90、reobserve；
6. 新 RGB 再次进入模型 A；
7. 更新语义后模型 B 重新决策；
8. 54/54 后 finish、validate、FINISH。

模型 A 的每次调用都带图像；模型 B 的每次调用均验证 `image_data_url is None`。测试要求
至少两个不同 frame_id，并验证真实 `reorient_cube` 执行。

新增实时 DecisionEvent：OBSERVATION_CAPTURED、VLM_INFERENCE_STARTED/COMPLETED、
PERCEPTION_UPDATED、AGENT_DECISION_STARTED/COMPLETED、SKILL_VALIDATED/REJECTED。
事件来源区分 `vlm_perception`、`llm_agent_planner`、`perception_fusion`、
`skill_registry_safety_gate` 和 `deterministic_policy`。

## 4. UI

现有右侧面板增加：

- Model A / Model B 的独立名称、连接状态和延迟；
- 最新 SemanticSceneObservation、遮挡、信息缺口和冲突；
- Agent 动作、依据、Safety Gate 与 Skill 反馈；
- observation/frame 关联的历史真实图片。点击 DecisionEvent 时读取当时保存的 image_url，
  不使用当前最新帧冒充历史帧。

LIVE/SAMPLE/REPLAY 隔离保持不变，真实模型仍受页面密码门保护。

## 5. 配置

模型 A 使用 `CUBERELAY_PERCEPTION_*`，模型 B 使用 `CUBERELAY_AGENT_*`。完整变量见
`.env.example`。两个 endpoint 必须兼容 OpenAI Chat Completions、image_url（模型 A）和
JSON object structured output。

## 6. 测试结果

- 本地 Schema/Provider/Safety/UI/API：18 passed（MuJoCo 项按环境跳过）。
- 服务器真实 MuJoCo M4-B 独立双 Provider：4 passed；物理闭环用例约 38 秒。
- M4-B 首轮发现双模型每轮两次调用会提前耗尽 M4-A 的 16-call 默认预算；已修复为默认
  32 次总模型调用，同时仍保留 16 个决策轮上限。

## 7. 对照实验状态

已具备四组的接口分解：

- A Deterministic Baseline：现有 M3-D 可运行；
- B VLM Perception + Deterministic Planner：Provider 可独立调用，但尚未完成全 Mission
  的 observational hook 实验 runner；
- C CV + LLM Agent：Agent Provider 可读取 CV context，但尚未完成独立矩阵 runner；
- D VLM Perception + LLM Agent：Fake 双 Provider + 真实 MuJoCo 已完成。

M4-A 的真实图像/无图像/替换图像消融仍有效；M4-B 新测试证明不同语义输入会改变独立
Agent 的 Skill 选择，错误 evidence observation ID 会失败。

## 8. 在线验收阻塞

服务器 `.env` 当前只有旧的 `CUBERELAY_VLM_*`，没有独立的
`CUBERELAY_PERCEPTION_*` 与 `CUBERELAY_AGENT_*`；且已知服务器不能访问 Gemini。
因此本轮尚未完成“两次真实 VLM + 两次真实 Agent”的在线双模型验收，不能把 Fake
Provider 物理闭环称为在线模型通过。配置服务器可访问的两个 endpoint 后才能执行最终
在线验收和四组统计实验。

## 9. 物理边界

仍只支持已验收的单次 U 正向物理转面；U'、U2 和其他面保持能力阻塞。VLM 语义不会
覆盖贴片 CV 结果，Agent 不能直接写 MuJoCo 状态或关节力矩。
