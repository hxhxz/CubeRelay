# CubeRelay M3-D：通用任务编排、Agent 决策可观测性与前端真实集成归档报告

## 1. 归档概览

- **文档位置**：[cuberelay_m3d_mission_orchestration_report_zh.md](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/docs/cuberelay_m3d_mission_orchestration_report_zh.md)
- **验收数据目录**：[results/m3d_acceptance](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/results/m3d_acceptance)
  - 汇总报告：[summary.json](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/results/m3d_acceptance/summary.json)
  - `INSPECT_CUBE` 快照：[inspect_cube_snapshot.json](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/results/m3d_acceptance/inspect_cube_snapshot.json)
  - `VERIFY_PHYSICAL_U_TURN` 快照：[verify_physical_u_turn_snapshot.json](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/results/m3d_acceptance/verify_physical_u_turn_snapshot.json)
  - `SOLVE_CUBE` 快照：[solve_cube_snapshot.json](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/results/m3d_acceptance/solve_cube_snapshot.json)

---

## 2. 仓库审计与架构变更清单

### 2.1 可复用既有基线
- **MuJoCo 仿真与感知**：`MuJoCoEmbodiedBackend`、`capture_rgbd`、`task_observe_released`、`video_timing="sim_time"`（`src/cube_relay/embodied/mujoco_v2.py`、`simulation/cube_relay_v2.xml`）、`DeterministicCubeLocalizer` / `StickerStateFusion`（`src/cube_relay/embodied/perception_v2.py`）、`ContinuousActiveInspector`（`src/cube_relay/embodied/active_inspection_v7.py`）。
- **M3-A 符号求解**：`CubeSolver`、`StateValidator`、`LEGAL_MOVES`（18 种标准符号操作：`U/R/F/D/L/B` 及其 `' / 2` 变体）。
- **M3-B 物理 U 转面与复核**：`ContactUTurn`、`build_u_scene`（`src/cube_relay/embodied/physical_u.py`）、`compare_observations`（`src/cube_relay/embodied/visual_turn_loop.py`）。
- **相机与时间轴基线**：`MotionTiming`、`TimedFrames`（`src/cube_relay/embodied/replay_timing.py`）。

### 2.2 本轮新增与修改文件
1. **Mission / Plan / Skill / DecisionEvent 核心包（`src/cube_relay/mission/`）**
   - [models.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/mission/models.py)：定义 `MissionType`（`INSPECT_CUBE`、`VERIFY_PHYSICAL_U_TURN`、`SOLVE_CUBE`）、`MissionStatus`（`CREATED`、`OBSERVING`、`PLANNING`、`EXECUTING`、`VERIFYING`、`BLOCKED_CAPABILITY`、`COMPLETED`、`FAILED`、`CANCELLED`）、`PlannerMode`、`PlanStepStatus`、`ObservationReference`、`PlanStep`、`PlanState`、`SkillExecutionState`、`MissionState`、`AgentObservabilityState`。
   - [events.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/mission/events.py)：定义 13 类 `DecisionEventType`、`DecisionEvent` 与保证序列及 `sim_time` 单调不减的 `DecisionEventLog`。
   - [skill_registry.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/mission/skill_registry.py)：建立 `SkillRegistry`，区分 `symbolic_supported_moves`（18 种合法符号动作）与 `physical_supported_moves`（仅 `["U"]`），提供 `can_execute_physical_move(move, scene_state)` 与 `audit_move_sequence(moves, scene_state)`，强制校验 `physical_u_scene_enabled`、`cube_localized_and_scanned`、`turn_station_available`、`single_u_turn_not_yet_consumed`。
   - [planner.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/mission/planner.py)：定义 `DecisionPolicy` 协议与确定性规划器 `DeterministicMissionPlanner`（显式声明 `status_label = "当前由确定性任务规划器执行，LLM Agent 尚未接入"`）。
   - [session.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/mission/session.py)：实现 `SimulationSession`，支持 macOS OpenGL 专用单线程执行（`use_dedicated_thread`）、主视口与腕部 RGB-D 实测帧编码（`frame_source = "REAL_MUJOCO_RENDERER"`）、反作弊校验与三类 Mission 端到端闭环。
   - [__init__.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/mission/__init__.py)：统一导出 Mission 包公共接口。
2. **FastAPI / WebSocket 服务端扩展**
   - [main.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/api/main.py)：保留既有 `GET /` 与 `/session/*` 路由，新增 `GET /api/m3d/state`、`GET /api/m3d/capabilities`、`GET /api/m3d/events`、`POST /api/m3d/command`、`WebSocket /ws/session`、`GET /console` 与 `/console-assets` 静态挂载。
   - [server.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/server.py)、`src/cuberelay/server.py`：服务启动入口。
3. **前端控制台集成与离线构建**
   - [cuberelay_v4.tsx](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/cuberelay_v4.tsx)：右侧 25% 面板重构为 `MissionType` 选择器 + `Agent / 决策` 与 `Skill / 执行` 双标签页；底部触发按钮改为动态发送 `{ type: 'START_MISSION', mission_type: selectedMission, seed: seedInput }`；`SAMPLE` 模式（`SYNTHETIC_SAMPLE` Canvas 2D 样本）与 `LIVE` 模式（`REAL_MUJOCO_RENDERER`）严格隔离。
   - [main.tsx](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/web/console/main.tsx)、[index.html](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/web/console/index.html)、[cuberelay_v4.css](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/web/console/cuberelay_v4.css)、[tsconfig.console.json](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/tsconfig.console.json)、[build_frontend.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/scripts/build_frontend.py)：基于本机 `~/.npm/_cacache` 完成离线依赖解压、TypeScript 严格检查及 `esbuild` 打包（生成 [bundle.js](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/web/console/bundle.js)）。
4. **验收脚本与测试**
   - [run_m3d_missions.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/scripts/run_m3d_missions.py)
   - [test_m3d_orchestration.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/tests/test_m3d_orchestration.py)

---

## 3. 真实 MuJoCo 三类 Mission 端到端验收数据（Seed=0）

以下数据来自 [summary.json](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/results/m3d_acceptance/summary.json)（2026-11-15 运行 `scripts/run_m3d_missions.py`）：

| Mission 类型 | 状态 | 仿真时长 (`sim_time`) | 实际执行 Skill 序列 | 实测指标与审计结果 |
| :--- | :--- | :--- | :--- | :--- |
| `INSPECT_CUBE` | `COMPLETED` | `29.942s` | `observe_workspace` → `active_six_face_scan` → `validate_cube_state` | `observed_count = 54`、`unknown_count = 0`、`decision_event_count = 15`；**未执行任何物理转面**。 |
| `VERIFY_PHYSICAL_U_TURN` | `COMPLETED` | `61.206s` | `observe_workspace` → `active_six_face_scan` → `validate_cube_state` → `compute_symbolic_plan` → `execute_physical_u_turn` → `verify_post_turn_state` | `actual_angle_deg = 90.0`（`actual_delta_rad = -1.57079627787289`，`layer_error_rad = 4.892200666795077e-08`），`min_base_contact_n = 0.859`，`min_turn_contact_n = 0.709`，`max_turn_brake_torque = 0.0`；`affected_21_verified = true`（D 面保持 `?????????` 未知），`no_recolor = true`，`logical_state_unchanged = true`，`same_model_and_data = true`，`active_equalities = []`，`decision_event_count = 25`。 |
| `SOLVE_CUBE` | `BLOCKED_CAPABILITY` | `29.942s` | `observe_workspace` → `active_six_face_scan` → `validate_cube_state` → `compute_symbolic_plan` (`VERIFIED`) → `check_physical_capability` (`BLOCKED`) | Kociemba 求解生成 21 步序列（首步 `U'`），在 `check_physical_capability` 阶段触发 `CAPABILITY_BLOCKED`（`de-0020`），未执行 `execute_physical_u_turn`，明确以“规划完成但物理执行在 `U'` 处受阻”终止。 |

---

## 4. 构建与测试记录

- **前端离线构建与类型检查**（2026-11-15）：
  - `/private/tmp/cuberelay-py313/bin/python scripts/build_frontend.py --typecheck` → 退出码 `0`（`typechecked: true`, `bundle_bytes: 392187`, `css_bytes: 10706`, `packages_count: 13`）；CSS 覆盖率校验 `MISSING_CSS_TOKENS: []`。
- **Pytest 验证（macOS MuJoCo CGL 需非沙箱环境运行）**（2026-11-15）：
  - `pytest tests/test_m3d_orchestration.py -q` → `8 passed in 54.39s`
  - `pytest tests/test_replay_timing.py tests/test_physical_u.py tests/test_api.py -q` → `16 passed in 6.14s`
  - `pytest -q` → `181 passed in 84.68s`
- **实时浏览器 UI 验证状态**：
  - `http://127.0.0.1:8765/console` 路由、静态资源与 `/ws/session` 握手已通过 FastAPI `TestClient` 验证。
  - 调用内置浏览器子代理打开 `http://127.0.0.1:8765/console` 时因 127.0.0.1:8765 权限弹窗等待超时 60s 返回 `BLOCKED / ORIGIN_PERMISSION_REQUIRED`（`visited_origins: none`, `latest_screenshot: none`），故本归档目录中**不包含真机浏览器渲染 PNG 截图**。

---

## 5. 能力边界诚实声明

- **已实现并经 MuJoCo 验证**：Mission/Plan/SkillRegistry/DecisionEvent 解耦架构、`SimulationSession` 实时渲染与反作弊锁、`INSPECT_CUBE`、`VERIFY_PHYSICAL_U_TURN`（单次 U 层顺时针 +90° 物理接触转面与 21 格复核）、`SOLVE_CUBE`（符号求解 + 物理能力边界拦截）以及 `cuberelay_v4.tsx` 离线构建产物。
- **仅样本模式展示**：UI 顶栏 `SAMPLE` 模式下的 Canvas 2D 合成画面（强制标注 `SYNTHETIC SAMPLE`），与 `LIVE` 模式严格隔离。
- **当前未实现 / 受阻能力**：`R / F / L / B / D` 多面实体铰链与连续重装夹、`U'` / `U2` 物理转层，以及 M3-D 通用编排层在线 Gemini / LLM 自主规划器（当前 UI 与后端明确显示 `"当前由确定性任务规划器执行，LLM Agent 尚未接入"`）。

---

## 6. 下一阶段 Gemini VLM 接入点

基于 [planner.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/mission/planner.py) 的 `DecisionPolicy` 协议，后续接入 Gemini VLM 仅需 5 个最小改动点：
1. 新增实现 `DecisionPolicy` 的 `GeminiMissionPlanner`（复用 `src/cube_relay/embodied/task_agent_v7.py` 中的 `_EnvLoadedGeminiClient` 或 OpenAI 兼容多模态客户端），设置 `PlannerMode.LLM_AGENT`、`llm_connected = True`、`llm_model`。
2. 将 `SimulationSession` 中的 `self._main_frame_url`、`self._wrist_rgb_url`、`self._wrist_depth_url`、`self.last_observation_ref` 与 `self.mission` 注入模型上下文。
3. 通过 `SkillRegistry.snapshot()` 导出可用工具、前置条件与 `physical_supported_moves` 作为结构化动作约束。
4. 保留 `SkillRegistry.validate_parameters()`、`check_preconditions()` 与 `can_execute_physical_move()` 作为硬性物理护栏，模型请求的未支持物理动作继续由 `SimulationSession._handle_capability_block()` 拦截并记录 `CAPABILITY_BLOCKED`。
5. 通过 `SimulationSession._record_decision()` 将模型工程化决策依据实时写入 `DecisionEventLog`，通过 `/ws/session` 同步至前端 `Agent / 决策` 标签页。
