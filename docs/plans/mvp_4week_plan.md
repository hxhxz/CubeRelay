# 人机接力解魔方：4 周 MVP 实施计划（Codex 工程任务书）

> 版本：v1.0｜规划日期：2026-11-10｜项目代号：CubeRelay
>
> **Codex 执行指令**：把本文件当作产品需求和验收规范。先搭建可运行、可测试的软件闭环，再做相机与机器人适配。每个阶段提交可运行代码、自动化测试、运行命令与简短完成报告。不要在没有硬件配置时假装已经完成真机控制。

## 0. 项目定义与边界

### 0.1 核心目标

开发一个**人和机器人轮流操作 3×3 魔方**的最小闭环系统。系统保持可验证的世界状态，计算解法，支持人类在任意轮次执行非预期转面，并能重新估计状态、修复计划、继续任务。最后提供虚拟机器人接口和真机适配接口，为 ROS 2 / MoveIt 2 及真机迁移建立可操作的边界。

### 0.2 四周完成时必须可演示的故事

1. 打开本地网页，选择预置打乱状态或输入合法 54 facelet 状态。
2. 系统显示完整魔方二维展开图，规划一条求解动作序列。
3. 用户执行一手动作（UI 操作）。系统更新状态并验证。
4. 虚拟机器人执行下一手动作，显示执行前后状态及动作日志。
5. 用户**不按推荐动作**额外转动某一面；系统检测到预期轨迹偏离，停止旧计划，重新求解。
6. 人机继续交替操作直到 solved；导出 JSON/CSV 运行记录和实验指标。
7. 可切换到 `dry_run` 机器人适配器，输出未来机械臂动作请求，但**不驱动真实硬件**。

**软件闭环为必达项。** 摄像头识别、真实机械臂转面在第四周是有条件的扩展项，不可把它们当作不具备硬件时的阻塞项。

### 0.3 明确不做

- 不训练新的 VLA / 强化学习策略，不复刻 OpenAI Dactyl。
- 不要求真实机械臂任意姿态抓取并连续完成 6 个面的转动。
- 不要求单 RGB 视角推断看不见的全部贴片。
- 不要求 LLM 从零推导魔方解法；调用确定性求解器。
- 不要求 ROS 2、MoveIt 2 在普通笔记本环境中作为软件 MVP 的启动前置条件。

### 0.4 成功标准

| 指标 | 最低验收要求 | 测试方式 |
| --- | --- | --- |
| 基础状态/转面正确性 | 18 种标准动作均有测试；逆操作和四次旋转恢复初态 | `pytest` |
| 合法打乱求解 | 20 个固定 seed 的随机打乱，求解并逐步执行后全部回到 solved | 集成测试 |
| 人机交替 | 连续完成 1 局，动作角色可追踪 | UI 演示 + 日志 |
| 计划修复 | 人类非预期干预后重新规划，至少 10 个固定测试用例通过 | 自动化测试 |
| 数据可信度 | 任一动作后记录 `actual_state`，且新计划从 **actual** 而非原始预计状态产生 | 测试断言 |
| 无硬件可运行 | 新机器根据 README 用 3 条以内命令启动核心 Demo | 人工验收 |
| 机器人抽象层 | `SimRobotAdapter`、`DryRunRobotAdapter` 均符合统一接口 | Mock 测试 |
| 安全性 | 真机未连接时绝不向物理设备发命令；实际驱动必须有人工使能和急停/安全区域检查 | 代码检查 |

## 1. 范围与主要技术决策

- **魔方规格**：3×3；魔方贴片采用标准 `URFDLB` 面名，状态以固定顺序 `U R F D L B` 的 54 字符 facelet 串表示。具体转面方向与求解库约定一致，写入单元测试。
- **动作集合**：`U U' U2 R R' R2 F F' F2 D D' D2 L L' L2 B B' B2`。
- **软件栈**：Python 3.11+；FastAPI + Pydantic（后端）；轻量 HTML/TypeScript 或原生 JS（前端）；pytest；uv 或 pip 管理依赖。选最轻、最稳的实现，不启动复杂前端基础设施也可。
- **魔方动作引擎**：自研**小型、可单测**的 54 贴片状态置换层，或封装已验证库；避免“动画显示的状态”和“求解器内部状态”使用不同约定。
- **求解器**：优先复用成熟的 Kociemba / two-phase 开源实现，例如 `RubikTwoPhase`；统一封装 `solve(facelets)->list[str]`。注意首次调用查表生成耗时以及返回格式差异，启动时预热/缓存并在 README 说明。不要自行手写求解算法。
- **Agent**：默认**确定性状态机**，LLM 作为可选高层解释器（仅做交互解释/错误分类，不直接控制关节），无 API Key 也必须完整运行。
- **可视化**：平面展开图显示 6 面颜色和 turn-by-turn 历史，最小闭环不要求 3D 渲染。
- **摄像头**：第三周开始可选 OpenCV 模块；默认通过 UI 或 6 面人工扫描输入完整状态。视觉识别失败时采用人工确认，不得伪装为自动识别成功。
- **机器人**：统一 `RobotAdapter` 接口；MVP 的“机器人转面”由模拟适配器执行；真实驱动不作为四周默认承诺。
- **工作平台**：macOS / Linux / Windows 可运行纯软件模块；ROS 2 / MoveIt 2 仅在适配 Ubuntu + 已知机械臂型号后单独部署。

### 1.1 资源清单

**最低必需**：一台普通笔记本/工作站、Python 环境、浏览器、互联网（仅安装依赖）、可选实体魔方。**不需要 GPU 和 LLM API Key**。

**可选视觉**：USB RGB 摄像头、稳定光照、三脚架、统一贴纸配色。

**可选真机**：现成 6-DoF 机械臂和厂商 SDK/ROS 驱动、匹配的平行夹爪、专用转面夹具、急停及安全限位；是否能转面必须先做独立机构验证。

## 2. 系统架构

```text
                  Human (UI / optional camera)
                          |
                  ObservationAdapter
               (Manual / CameraOptional)
                          |
                   CubeState (54)
                          |
                   StateValidator
                          |
              Agent / Turn Coordinator
                /        |          \
         SolverAdapter  PlanRepair   EventLog
                \        |          /
                  PlannedMove
                          |
             RobotAdapter (Sim / DryRun / Real*)
                          |
                Execution / Observation
                          |
                      Verify
                          |
                    Next turn

 *Real robot adapter is disabled by default and conditional.
```

### 2.1 核心数据契约

```python
from typing import Literal
from pydantic import BaseModel, Field

Actor = Literal['human', 'robot']

class CubeObservation(BaseModel):
    facelets: str   # 54 chars, order U R F D L B
    source: Literal['sim', 'manual', 'camera']
    confidence: float = Field(ge=0, le=1)
    timestamp: str

class MoveRequest(BaseModel):
    actor: Actor
    move: str       # one of 18 legal moves
    expected_before: str

class MoveResult(BaseModel):
    success: bool
    move: str
    observed_after: str | None
    error: str | None = None

class SessionState(BaseModel):
    session_id: str
    actual_state: str
    planned_moves: list[str]
    next_actor: Actor
    plan_version: int
    status: Literal['idle', 'running', 'paused', 'solved', 'error']
```

**关键不变量**：

1. `actual_state` 是系统唯一权威状态；不能在观察确认之前仅凭计划把真实世界状态标记为已执行。
2. 仿真模式允许 `SimRobotAdapter` 产生权威转面结果；真机模式必须使用外部观测或人工确认。
3. 执行动作前 `expected_before` 必须等于当前实际状态，否则拒绝执行并触发重规划。
4. 状态不合法或观察低置信度时进入 `paused`，不得盲目继续。
5. 人类发生非预期动作后，`plan_version += 1`；清除/废弃旧计划，基于最新已确认状态重新求解。
6. **偏离计划 ≠ 状态非法**：有效但不同于计划的转面属于可恢复事件；被识别为不可能的魔方配置则必须请求重扫/人工确认。

### 2.2 必需接口

```python
class CubeEngine:
    def apply_move(self, facelets: str, move: str) -> str: ...
    def is_solved(self, facelets: str) -> bool: ...

class CubeSolver:
    def solve(self, facelets: str) -> list[str]: ...

class ObservationAdapter:
    def observe(self) -> CubeObservation: ...

class RobotAdapter:
    def execute_move(self, request: MoveRequest) -> MoveResult: ...
    def emergency_stop(self) -> None: ...

class TurnCoordinator:
    def start(self, facelets: str) -> SessionState: ...
    def submit_human_move(self, move: str) -> SessionState: ...
    def execute_robot_turn(self) -> SessionState: ...
    def override_observation(self, observation: CubeObservation) -> SessionState: ...
```

接口既可以同步实现，也可以在真实硬件适配层使用 async 包装；不要让控制器直接依赖 Web 框架。

### 2.3 推荐仓库结构

```text
cube-relay/
├── README.md
├── pyproject.toml
├── .env.example
├── docs/
│   ├── architecture.md
│   ├── demo_script.md
│   └── ros2_real_robot_integration.md
├── src/cube_relay/
│   ├── cube/
│   │   ├── state.py
│   │   ├── moves.py
│   │   ├── validation.py
│   │   └── solver.py
│   ├── agent/
│   │   ├── coordinator.py
│   │   ├── replanner.py
│   │   └── policies.py
│   ├── adapters/
│   │   ├── observation.py
│   │   ├── sim_robot.py
│   │   ├── dryrun_robot.py
│   │   └── camera_optional.py
│   ├── telemetry/
│   │   ├── events.py
│   │   └── metrics.py
│   └── api/
│       └── main.py
├── web/
│   ├── index.html
│   ├── app.js
│   └── style.css
├── scripts/
│   ├── demo.py
│   └── benchmark.py
└── tests/
    ├── test_moves.py
    ├── test_solver.py
    ├── test_coordinator.py
    ├── test_intervention.py
    └── test_api.py
```

## 3. 四周任务计划

### Week 1：魔方状态、转面与求解器（核心算法闭环）

**目标**：不需要 UI、相机和机械臂，完成“打乱 → 求解 → 验证 solved”的确定性闭环。

**任务**：

1. 初始化仓库、虚拟环境、依赖锁定、pytest、基本 CI（有条件可用 GitHub Actions）。
2. 统一 `URFDLB` facelet 格式、18 种动作、颜色/面名约定。
3. 实现或封装 `CubeEngine`：`apply_move`、`apply_moves`、`is_solved`、`scramble(seed,n)`。
4. 实现 `CubeSolver`：可处理合法打乱，可识别无法求解/非法输入，统一输出动作记号。
5. 做好合法性验证：长度、字符、颜色/中心数量与 solver 可解性；对不可解的真实贴片状态不返回虚假路径。
6. 完成 20 个固定 seed 的回归测试；记录求解时延（首次预热与后续执行分开）。

**交付物**：`src/cube_relay/cube/*`、`tests/test_moves.py`、`tests/test_solver.py`、`scripts/demo.py`。

**验收**：
- `pytest -q` 全通过。
- `python scripts/demo.py --scramble "R U R' U'"` 能展示初态、打乱、求解路径和最终 `SOLVED`。
- 在不同面、逆向转动和半转的组合下，置换结果与求解器约定一致。

**工作检查点**：如果两天内求解库与自研置换层存在坐标不一致，优先切换到一个可靠的状态/动作库，避免重复造轮子拖延项目。

### Week 2：人机交替 Agent + 可视化（MVP 必达核心）

**目标**：浏览器中完整体验人机交替，支持非预期转面后的自动重规划。

**任务**：

1. 实现 `TurnCoordinator`（状态机）：`idle → running → paused/solved`，区分 `human`、`robot` 角色。
2. 实现 `SimRobotAdapter`：机器人动作在虚拟魔方状态中精确生效。
3. 实现 `PlanRepair`：人类动作变化后，基于最新 actual state 重新调用求解器。
4. 实现 FastAPI 接口：
   - `POST /session`：创建任务，传入 scramble 或 facelets。
   - `GET /session/{id}`：读取状态和日志。
   - `POST /session/{id}/human-move`：执行/登记人的一步。
   - `POST /session/{id}/robot-turn`：虚拟机器人执行一步。
   - `POST /session/{id}/observe`：手动更正当前已观测状态。
   - `GET /session/{id}/events`：读取结构化日志。
5. 编写零复杂构建的 Web UI：54 个贴片展开图、当前角色、推荐动作、18 个转面按钮、机器人执行按钮、重新规划历史、完成状态。
6. 支持 `unexpected intervention`：UI 可在人的轮次执行任意合法转面，不强制符合原方案；显示 `PLAN_REPAIRED` 事件。
7. 增加动作事件 `HUMAN_MOVE`、`ROBOT_MOVE`、`STATE_MISMATCH`、`PLAN_REPAIRED`、`SOLVED`。

**交付物**：可运行 Web Demo、CLI Demo、交替与干预测试。

**验收**：
- 固定打乱状态从开始到还原成功。
- 人故意做一个与原规划不同的转面后，旧计划被废弃，新计划从实际状态生成。
- UI 不允许 `solved` 后继续执行无意义动作（除显式 reset）。
- `curl`/API 测试能在无浏览器情况下运行。

### Week 3：观测、异常与评测（可信的 Agent 行为）

**目标**：将可运行 Demo 变成有实验价值的、可重复测量的闭环。

**任务**：

1. 实现 `ManualObservationAdapter`：允许用户提供完整 54 facelets 覆盖观测；覆盖前做合法性检查并要求人工确认。
2. 可选相机扩展：OpenCV 固定拍照、四角标定/颜色样本校准、单个可见面的九格提取；必须提供逐面扫描/人工确认流程才可宣称获得完整 cube state。
3. 加入观测失败和错误恢复：`INVALID_OBSERVATION`、`LOW_CONFIDENCE`、`RETRY_SCAN`、`MANUAL_CONFIRMATION`。
4. 模拟执行失误：`SimRobotAdapter` 可配置某一步 `no-op` 或执行不同转面；验证后发现 expected/actual 不一致时暂停并重规划。
5. 评测脚本生成 3 类任务集：
   - A：无干预，20 个固定种子；
   - B：指定轮次随机但合法的人类额外转面，10 个种子；
   - C：模拟机器人动作失误，10 个种子。
6. 记录每一局 `success`、`total_moves`、`human_moves`、`robot_moves`、`replan_count`、`mismatch_count`、`recovery_success`、`runtime_ms`。
7. 至少两个 baseline：
   - `fixed-plan`：只执行初始求解序列，发生意外时不重新规划；
   - `replan`：每当实际状态发生变化就从实际状态求解。
   注意在 A 类任务中两者都应可成功；在 B/C 中比较差异。

**交付物**：`scripts/benchmark.py`、`docs/experiment_protocol.md`、指标 CSV/JSON、失败案例回放（日志或逐帧 UI）。

**验收**：
- 基准用固定 seed 可复现；指标计算有单测；不允许用“虚拟执行成功”当成“物理执行成功”。
- 系统可注入 no-op、错误转面和无效观测而不崩溃、不继续盲执行。
- 运行 `python scripts/benchmark.py --output results/` 生成汇总结果。

### Week 4：演示封装、真机迁移接口与可选相机/硬件集成

**目标**：交付其他人能运行的 MVP，并将仿真到真机需要替换的组件明确化。

**必做任务**：

1. 实现 `DryRunRobotAdapter`：接收标准转面动作，打印/记录 `move`, `expected_before`, `plan_version`, `safety_mode`，默认不执行物理运动。
2. 编写 `docs/ros2_real_robot_integration.md`，说明如何把逻辑动作映射到 `reorient_cube` / `rotate_face` / `confirm_observation` 等物理原语，以及坐标系/末端标定/夹具的依赖。
3. 增加 `robot_mode` 配置：`sim`（默认）、`dry_run`、`real`（默认禁用，若无真实驱动直接明确报错）。
4. 完成 README：安装、运行、测试、演示、评测、已知限制。
5. 提供 90 秒演示脚本：预置打乱 → 人机轮流 → 人的非预期操作 → `PLAN_REPAIRED` → 还原成功 → 导出日志。
6. 整理周报和项目报告：架构、实验结果、失败类型、真机迁移风险、下一轮科研问题。

**有真机时的可选路线**：

- 先用厂商 SDK/ROS 2 做关节回零、使能、急停和限定工作区自检。
- 用独立夹具测试**一个确定方向的单面 90° 转动**，不要承诺所有 18 种动作。
- 将该动作绑定到 `RobotAdapter` 的能力声明，其他动作请求返回 `UNSUPPORTED_MOVE` 或由人执行。
- 动作后通过相机/人工确认再更新 actual state；任何置信度不足立即停止。
- 低速、空载、有人监护；机械臂和人类轮流进入工作区，禁止同时伸入危险工作范围。
- 记录真实操作成功率与仿真不同之处；不把软件模拟成功率称为真机成功率。

**验收**：
- README 所述流程在干净环境跑通。
- `pytest -q` 和 benchmark 脚本通过。
- `sim` 和 `dry_run` 都可运行；`real` 无配置时无法下发命令。
- Demo 可稳定展示至少一次人的非预期操作后成功恢复。
- 有真机设备时额外提交单面动作视频、动作前后观察记录及安全检查表；无硬件时提交真机接口和迁移文档即可。

## 4. 演示行为规范

### 4.1 推荐交互

- 初始打乱选择 `scramble = "R U R' F2 D"`（示例，可更换）。
- 初次生成解法后 UI 显示 `Next: Human` 和推荐转面。
- 人执行推荐转面或选择其他任意转面；系统先记录新状态。
- 机器人根据最新状态从队列取下一步执行。
- 在第 3～6 步注入非预期人类转面，UI 明显显示 `Unexpected move → Replanning`。
- 运行结束显示最终 solved 状态、动作总数、重规划次数以及 JSON 导出。

### 4.2 模式区分

- `sim`: 用户点击“人类动作”，机器人点击“Robot turn”执行模拟动作；状态由动作引擎推导。
- `camera/manual`: 观测结果独立于动作意图，实际状态须经人工确认或完整扫描。
- `dry_run`: 只输出动作请求，不自动将其视为真实世界已执行；可通过模拟确认 API 或人工确认闭环。
- `real`: 仅当硬件驱动、安全检查、观测链路都存在时启用。

## 5. 测试用例清单（Codex 必须实现）

1. `move + inverse(move) -> identity` 对所有基础动作成立。
2. 同一面 90° 转动四次 -> identity。
3. 合法打乱 `scramble(seed)` 后 solver 结果使状态变成 solved。
4. 54 字符非法、字符集不合法、颜色数错误应得到可解释错误。
5. 手动状态覆盖为合法状态后，下一步规划必须来源于覆盖后的状态。
6. 人类做了非预期 `F`，系统不得沿用原计划剩余部分作为有效解法。
7. `plan_version` 仅在重新规划时递增，旧版本动作不可提交执行。
8. 虚拟机器人执行失败（no-op）后产生 `STATE_MISMATCH` 并进入暂停或恢复过程。
9. 求解库异常时前端可显示错误，不能返回成功状态。
10. 同一 seed、同一干预序列的事件序列和评测指标可复现。
11. `real` 模式没有连接配置和安全使能时绝不发送命令。
12. `solved` 判断基于当前实际状态，而不是“计划动作已用完”。

## 6. 交给 Codex 的执行方式

### 6.1 第一条任务消息（可复制）

> 阅读仓库中的 `docs/plans/mvp_4week_plan.md`。按本文件的 Week 1 任务实现 CubeRelay。请先检查当前仓库与 Python 运行环境，然后创建可测试的 `CubeEngine`、`CubeSolver` 和 CLI Demo。优先使用成熟开源求解器，并验证 URFDLB 坐标约定一致。为所有动作写逆操作/四次旋转单测，为 20 个固定打乱 seed 写端到端求解测试。执行测试、修复所有失败，并在最后报告变更文件、运行命令、测试结果和剩余风险。不要开始 Week 2。

### 6.2 后续三条任务消息（按周依次提交）

**Week 2**：
> 按计划文件 Week 2 完成 `TurnCoordinator`、`SimRobotAdapter`、计划修复、FastAPI 和二维魔方 Web UI；必须证明人的非预期转面使旧计划失效并基于实际状态重规划。执行测试并提供演示命令。不要开始 Week 3。

**Week 3**：
> 按 Week 3 增加 ManualObservationAdapter、错误/低置信度处理、故障注入、固定种子 benchmark、fixed-plan 与 replan baseline、JSON/CSV 事件日志和实验协议。确保所有实验结果由实际代码运行产生，不编造指标。执行测试并报告结果。相机识别只作为可选扩展。

**Week 4**：
> 按 Week 4 加入 DryRunRobotAdapter、真机迁移接口文档、README、90 秒 Demo 脚本、完整回归测试和 benchmark。真实机械臂驱动仅在设备明确、接口与安全条件齐备时实现；否则保持禁用并明确说明。最终提交可复现运行步骤、测试报告、演示流程与未完成项。

## 7. 风险、取舍与扩展

| 风险 | MVP 处置 | 后续扩展 |
| --- | --- | --- |
| 单视角看不到 6 面 | 手动 54 格状态 / 可选择逐面扫描 | 多视角/主动扫描 |
| 普通夹爪难转全部魔方面 | 机器人动作由 SimRobotAdapter 执行 | 专用夹具、双夹持器、姿态重定向 |
| LLM 幻觉造成错误控制 | 状态机 + 确定性求解器，LLM 不直接控制底层动作 | 可解释策略/意图推断、工具调用策略 |
| 计划恢复看似简单 | 定量对比固定计划与状态重规划，并构造观测/执行错误 | 部分可观测状态、意图推断、成本约束规划 |
| 真机迁移对齐困难 | 统一高层动作接口、观测确认协议 | ROS 2 / MoveIt 2/设备厂商 SDK |
| 4 周超时 | 优先 Week 1+2 交付，砍掉相机和 3D UI | 后续迭代补充 |

## 8. 研究定位与后续创新

**本 MVP 的目标是复现一个可信、可观测、可量化的人机协作闭环，不宣称发明新的魔方求解算法，也不将简单重新调用 solver 等同于新的科学贡献。**

在完成 MVP 后，可形成下面的研究问题：

1. **不确定状态下的主动感知**：当颜色被手遮挡时，什么时候该转动魔方观察，什么时候该询问人？
2. **基于操作能力的人机分工**：让机械臂只做低成本且可靠的动作，把难动作分给人，是否能减少总完成时间与失败率？
3. **执行误差归因与长期技能记忆**：将特定物理失败归纳为可迁移恢复技能，是否能在新打乱状态或不同夹具上提高成功率？
4. **Sim-to-Real**：同一个高层 Agent 是否能在不修改逻辑策略的情况下，把 `SimRobotAdapter` 替换为实际机器人适配器，并在物理误差下继续完成协作？

## 9. 外部参考（可选，不作为 MVP 运行依赖）

- Two-phase 求解器项目： https://github.com/hkociemba/RubiksCube-TwophaseSolver
- MoveIt 2： https://moveit.picknik.ai/
- ROS 2 文档： https://docs.ros.org/
- OpenCV： https://opencv.org/

**最终验收定义**：一个新开发者只看 README 就能启动 Web Demo，看到人机交替转面、主动注入非预期动作、系统从当前实际状态重新求解并最终解开魔方；能够运行测试与 benchmark，导出可审计的事件日志；有明确且默认安全关闭的真机适配边界。
