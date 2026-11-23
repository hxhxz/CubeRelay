# CubeRelay M4-A：Gemini VLM-in-the-Loop 验收报告

## 1. 结论

M4-A 已实现 Gemini 读取真实 MuJoCo RGB 图像、输出结构化 Skill 决策、经
`SkillRegistry` 校验后执行物理动作、采集新图像并再次决策的闭环。确定性
`ContinuousActiveInspector` 仍作为独立控制组保留，没有重写 M3-D Mission 系统。

本报告区分两类证据：

- `results/m4a_acceptance/` 是 2026-11-16 已完成的真实 Gemini 在线实验；
- 本次断点续作后的代码在 `47.116.185.156` 完成 MuJoCo/Fake Client 与 M3-D
  回归，但该服务器无法访问 Gemini，因此修复后的在线复验受网络条件阻塞。

不得将 Fake Client 回归或服务器网络失败统计为新的 Gemini 在线成功。

## 2. 实现范围

- `AgentObservation` 对齐 `observation_id`、`frame_id`、`sim_time`、相机元数据、
  RGB data URL、可见贴片、unknown/conflict、最近 Skill 反馈和能力边界。
- `_EnvLoadedGeminiClient` 使用环境变量读取 endpoint、model 和 API key；密钥不写入
  前端、Trace 或 repr。客户端提交图像和文本，并用 `VLMDecisionOutput` 严格校验 JSON。
- `GeminiMissionPlanner` 实现既有 `DecisionPolicy`，与
  `DeterministicMissionPlanner` 可替换；只有真实客户端完成有效响应后
  `llm_connected=true`。
- VLM-Controlled Inspection 暴露 `place_and_release`、`observe_visible_faces`、
  `regrasp_cube`、`reorient_cube`、`finish_inspection`，不向模型暴露黑盒
  `active_six_face_scan`。
- 所有动作继续经过参数、前置条件、物理能力、Mission 状态和调用预算校验。
- 等待 Gemini 时检查 MuJoCo `sim_time` 不变化；记录模型延迟、仿真 Skill 时长和
  wall time。
- DecisionEvent 和层级 Skill Trace 区分 `gemini_vlm` 与
  `deterministic_policy`，并关联输入帧、执行 ID 和反馈 observation ID。
- 前端 Agent/Skill 双标签展示真实 planner、模型、帧、结构化决策、安全门、执行反馈、
  延迟和可展开扫描子事件；SAMPLE 与 LIVE 数据仍隔离。

## 3. 真实在线闭环证据

实际模型为 `gemini-3.5-flash-lite`，provider 为
`gemini_openai_compatible`。`INSPECT_CUBE` Seed 0 在线运行结果：

- 状态：`COMPLETED`；54/54 已观测，unknown=0，conflict=0；
- 10 次 Gemini 调用，全部包含真实 MuJoCo 图像；
- 输入 22,643 tokens，输出 1,176 tokens；累计模型延迟 23,797.41 ms；
- 仿真时间 29.942 s，执行 wall time 26.8283 s；
- 无确定性 fallback。

关键动作序列：

1. `observe_workspace`；
2. `place_and_release`；
3. `observe_visible_faces(released)`，unknown 54 → 9；
4. `regrasp_cube`；
5. `observe_visible_faces(held)`；
6. `reorient_cube(pitch, -90)`；
7. 使用动作后的新图像执行第二阶段 `observe_visible_faces(held)`，unknown 9 → 0；
8. `finish_inspection`；
9. `validate_cube_state`；
10. `FINISH`。

输入图像 SHA-256 随物理状态发生变化，例如初始帧
`50e739...9a3ed`、释放态 `aad465...c58e`、重抓态 `f6cfc0...35b5`、翻转后
`c8f945...0b26`，证明闭环没有重复使用同一张图冒充反馈。

详细逐轮决策、frame 引用和 Skill 结果见：

- `results/m4a_acceptance/vlm_inspect_cube_seed0.json`
- `results/m4a_acceptance/frames/`

## 4. 视觉依赖对照

`results/m4a_acceptance/visual_ablation_seed0.json` 使用相同 seed、相机和可执行能力，
只改变图像条件：

- 真实释放态图像：2/2 选择 `regrasp_cube`；
- 真实持握态图像：2/2 选择 `reorient_cube(pitch,-90)`；
- 无图像：释放态和持握态均退化为 `observe_visible_faces`，与真实图像条件不同；
- 图像替换：动作跟随替换后的视觉内容变化，再由真实 scene state 的 Safety Gate
  拒绝不满足物理前置条件的动作。

minimal-metadata prompt 不包含 `cube_released_on_table`、`cube_held_in_gripper`、
unknown 索引或隐藏贴片真值，因此这组差异不能由直接泄漏答案解释。两次重复只能说明
该受控案例具有视觉依赖性，不能推出跨场景稳定的主动视觉能力。

## 5. 与确定性 Baseline 比较

Seed 0/1/2 的 `INSPECT_CUBE` 对比结果位于
`results/m4a_acceptance/baseline_vs_vlm_comparison.json`：

| 指标 | Deterministic | Gemini VLM |
| --- | ---: | ---: |
| 成功率 | 100% | 100% |
| 平均覆盖 | 54/54 | 54/54 |
| 平均物理动作数 | 1.0（复合 Skill 计数） | 3.0 |
| 平均仿真时长 | 32.753 s | 32.753 s |
| 平均 wall time | 2.584 s | 25.006 s |
| 模型调用 | 0 | 27 |
| 输入 / 输出 tokens | 0 / 0 | 61,086 / 3,211 |
| 失败数 | 0 | 0 |

确定性策略仍明显更快；VLM 的价值在于可观测、可替换的视觉条件决策，而不是当前性能。

## 6. 失败、能力边界与本次修复

早期在线结果中：

- `VERIFY_PHYSICAL_U_TURN` 因模型重复观察而触发 `MAX_OBSERVE_CALLS_EXCEEDED`；
- `SOLVE_CUBE` 因重复 yaw 重定位最终触发 `REORIENT_JOINT_LIMIT`。

根因是这两类 Mission 的 prompt 只描述扫描完成后的步骤，未复用 INSPECT 的安全扫描
阶段。本次修复让三类 Mission 共享同一 inspection guide，并在扫描未完成时：

- 工具 Schema 仅声明已验收的 `reorient_cube(axis='pitch', degrees=-90)`；
- 明确禁止从不变姿态重复观察、重复 place/release 和用 yaw 暴露隐藏面；
- 执行层拒绝不符合该扫描边界的重定位参数。

SkillRegistry 仍保留通用 yaw 参数能力；限制只作用于“尚未完成 54 格扫描”的动态决策
上下文，不改写既有物理控制器。

不支持的 `U'` 请求会生成 `CAPABILITY_BLOCKED`，不会修改贴片颜色或直接写仿真状态。

## 7. 测试与当前阻塞

- 本地 Python 3.14 协议测试：`8 passed, 1 skipped`；跳过项为 MuJoCo GL 闭环。
- 服务器 EGL 容器定向回归：`19 passed in 188.39s`，覆盖 M4-A 真实 MuJoCo
  Fake Client 闭环和 M3-D 三类 Mission。
- 服务器全量回归：`194 passed, 1 failed in 437.75s`。唯一失败为既有
  `test_v2_occlusion_recovery_uses_place_release_observe_regrasp_rotate`：Seed 1 的旧版
  `MuJoCoEmbodiedBackend.active_scan()` 在 `REGRASP` 后未进入 `ROTATE`。隔离复跑仍失败。
  本轮未修改该 backend；M3-D 的确定性扫描、物理 U 与 M4-A 定向回归均通过，因此将其
  记录为服务器 EGL 下的既有旧扫描路径问题，不把全量回归报告为通过。
- 前端 TypeScript 检查与 bundle：通过，bundle 413,137 bytes。

服务器 `47.116.185.156` 无法访问 Gemini endpoint，因此本次 prompt/Safety Gate 修复后
的真实在线三 Mission 复验尚未完成。既有在线 INSPECT、视觉消融和三 seed 对照证据有效，
但旧版 VERIFY/SOLVE 失败结果不能被修复后的离线测试替代。

## 8. 复现命令

```bash
python -m pip install -e '.[dev,simulation,vlm]'
export CUBERELAY_VLM_API_KEY='...'
export CUBERELAY_VLM_MODEL='gemini-3.5-flash-lite'
export CUBERELAY_VLM_ENDPOINT='https://generativelanguage.googleapis.com/v1beta/openai/'

MUJOCO_GL=egl python scripts/run_m4a_experiments.py --mode vlm_closed_loop --seed 0
MUJOCO_GL=egl python scripts/run_m4a_experiments.py --mode ablation --seed 0 --ablation-repeats 2
MUJOCO_GL=egl python scripts/run_m4a_experiments.py --mode baseline --seeds 0,1,2
MUJOCO_GL=egl pytest -q
```

UI 运行：

```bash
uvicorn cube_relay.api.main:app --app-dir src --host 0.0.0.0 --port 8000
```

打开 `/console` 后选择 `LLM_AGENT` 和 LIVE。若浏览器或部署环境无法访问本地端口，必须
报告网络/权限阻塞，不能用 SAMPLE 截图替代 LIVE 证据。
