# CubeRelay M5-A：全六面 26-Cubie“翻面喂料”物理闭环、控制/延迟修复与可中断 ActionChunk 底座技术报告

> **报告日期**：2026-11-19  
> **任务阶段**：M5-A（衔接已完成的 M4-E 感知与 Agent 架构规整，面向后续 M5-B 动态人机交互与 M5-C VLA 接入）  
> **核心交付物**：
> - 控制与思考预算收敛（Part 1）：[mujoco_v2.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/embodied/mujoco_v2.py)、[dual_model.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/mission/dual_model.py)、[runners.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/benchmark/runners.py)、[test_m5a_control_and_budget.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/tests/test_m5a_control_and_budget.py)
> - 全六面 26-Cubie 物理魔方与单臂“翻面喂料”（Part 2）：[physical_cube_26.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/embodied/physical_cube_26.py)、[flip_and_feed.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/embodied/flip_and_feed.py)、[skill_registry.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/mission/skill_registry.py)、[planner.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/mission/planner.py)、[session.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/mission/session.py)、[test_m5a_full_cube.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/tests/test_m5a_full_cube.py)
> - 统一可中断 `ActionChunk` 与 `CancellationToken` 执行底座（Part 3）：[action_chunk.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/execution/action_chunk.py)、[test_m5a_action_chunk.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/tests/test_m5a_action_chunk.py)
> - 跨轴端到端验证产物：[verification_report.json](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/results/m5a_cross_axis_u_rp_d2/verification_report.json)、[cross_axis_u_rp_d2.mp4](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/results/m5a_cross_axis_u_rp_d2/cross_axis_u_rp_d2.mp4)、[cross_axis_u_rp_d2.timing.json](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/results/m5a_cross_axis_u_rp_d2/cross_axis_u_rp_d2.timing.json)

---

## 一、 执行摘要（Executive Summary）

M5-A 围绕动力学底层精度、LLM 决策实时性、全六面真实物理操作以及可抢占控制底座四个维度完成闭环落地与实测验证：

1. **Part 1.1（`+10 cm` 横移过冲修复）**：将 [mujoco_v2.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/embodied/mujoco_v2.py#L2295-L2332) 中的 `_move_gantry_xy_damped` 固定 `0.8s` 阶跃驱动升级为 `ActionChunk.trapezoidal_xy(v_limit=0.24)` 自适应梯形速度规划 + 编码器阻尼（`kd=0.12`）+ 位置/速度双门控（`pos_tol=0.003 m`, `vel_tol=0.015 m/s`），并在 `_place_and_release` 中规避转面夹具垫块干涉区。在不放宽 M4-C 接触证书门槛、零读取 `qpos` 真值前提下，M4-C 四条件因果审计中 **`baseline`、`translate_x_005`、`translate_x_010` 全部 `COMPLETED`（`bilateral_contact_fraction = 1.0`）**，`translate_x_010` 末端定位误差由 ~31 mm 过冲压降至 **`0.002903 m`（2.9 mm）**，`vision_missing_negative_control` 保持安全阻断（`FAILED: INSUFFICIENT_MASK_PIXELS`）。
2. **Part 1.2（`AGENT` 思考预算可控化）**：在 [dual_model.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/mission/dual_model.py#L67-L143) 的 `OpenAICompatibleStructuredClient` 增加 `CUBERELAY_AGENT_REASONING_EFFORT` 与 `CUBERELAY_AGENT_THINKING_BUDGET`（`role="agent"` 默认 `1024`，支持 `off`/`none`/`null`/`-1` 显式关闭，对不支持端点优雅降级重试），并在 [runners.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/benchmark/runners.py#L168-L178) 打通 `reasoning_tokens` 全链路透传。在 `L1..L4` 全部 26 项 `GUIDE_MINIMAL + CV_ONLY` 实时基准上（`agent=gemini-3.8-flash`），单步平均延迟由 M4-E 的 `13.6s–16.6s`（最高 `91.5s` 超时）降至 **`4343.13 ms`**（中位 `4168.16 ms`，`p95 = 5192.89 ms`，`max = 6504.04 ms`），**0 次超时、0 次异常、Oracle 通过 `25/26`、Safety 通过 `26/26`**。
3. **Part 2（26-Cubie 真实全六面物理操作 + 单臂翻面喂料）**：淘汰旧“双砖粘死 U 层”模型，构建 26 个独立刚体小块（`cubie_00..25`）+ 54 张永久绑定贴片 + 6 轴被动旋转载体 `carrier_{U,D,F,B,L,R}` + 基于实时连续 `xquat` 重锚定的 `mjEQ_WELD` 物理结构；实现仅由顶层 `turn_pos_pad/turn_neg_pad` 接触摩擦力矩驱动且支持 `±90° / 180°` 的单顶层夹具；实现单夹爪 `FlipAndFeedController`（0/1/2 次翻面，含底面桌面侧放—对称松爪—RGB-D 重定位重抓—再翻 `90°` 送站）与 `CubeOrientationTracker`。跑通 **18/18 标准动作 54 格 100% 等价**、**连续跨轴 `U -> R' -> D2`**、**2-Flip `U -> D2`**、**独立相机 54/54 复核（0 冲突、0 改色、0 瞬移）**、**无接触驱动失败负对照（`CONTACT_DRIVE_FAILED`）**、**层角偏离 `>8°` 物理卡滞控制（`SLICE_MISALIGNED_JAM`）** 与 **`SimulationSession(SOLVE_CUBE)` 端到端求解闭环**。
4. **Part 3（可中断 `ActionChunkExecutor` 底座）**：在 [action_chunk.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/execution/action_chunk.py) 实现 `ActionChunk`、`CancellationToken`、`ChunkExecutionResult` 与 `ActionChunkExecutor`。实测空载进近抢占 **`14.00 ms`（`< 100 ms`）** 制动至 `0.01653 m/s`；持握魔方抢占 **`18.00 ms`** 制动至 `0.01959 m/s` 且 **`hold_grip_preserved=True`、`object_drop_detected=False`**；支持 `VLA_POLICY` 世界/目标版本号陈旧自动中止（`SAFETY_ABORTED: STALE_WORLD_REVISION`）与顶层夹具转面中段抢占安全停机。

---

## 二、 Part 1：控制收敛与 `AGENT` 思考预算修复

### 2.1 修复 `translate_x_010`（`+10 cm`）初始抓取横移过冲

* **根因回顾**：M4-E 中 `_move_gantry_xy_damped` 采用固定时间窗口做位置阶跃插值，`robot_x/y_joint`（`kp=500, damping=2.0`）在 `+10 cm` 跨度下蓄积过高动能并产生 ~31 mm 欠阻尼过冲，致使夹爪指尖错过方块侧面（`bilateral_contact_fraction = 0.00`）。
* **工程实现**：
  1. 在 [mujoco_v2.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/embodied/mujoco_v2.py#L2295-L2332) 中重塑 `_move_gantry_xy_damped`，通过 `ActionChunkExecutor` 执行 `ActionChunk.trapezoidal_xy(..., v_limit=0.24)` 限速梯形轨迹（严格只读取关节编码器 `robot_x_joint` / `robot_y_joint` 位置与速度），附加主动阻尼 `kd=0.12`，并在下探前执行 `pos_tol=0.003 m` 与 `vel_tol=0.015 m/s` 收敛门控（超时上限 `max_seconds=1.6`）。
  2. 在 `_place_and_release` 中保留桌面放置区与 `base_pos_pad` 转面工位之间的横移避障约束，确保工作区偏移 `[-10 cm, +10 cm]` 内桌面放置与重抓不发生意外碰撞。
  3. 全程保持 M4-C 接触证书门控（`bilateral_contact_fraction >= 0.80`、法向力、滑移与无意外接触约束）不变，未读取任何魔方隐藏真值。

#### M4-C 四条件因果审计实测对比（`seed=0, INSPECT_CUBE`）

| 实验条件 | 任务状态 | 目标物体 `gt_xyz` (m) | RGB-D 估计 `workspace_rgbd_est` (m) | 视觉定位误差 `loc_err_xy` (m) | 闭合实际末端 `actual_ee_close_xy` (m) | 目标/实际偏差 `ee_err_xy` (m) | 双侧接触率 `mean_bilat` | 最大相对滑移 `max_slip` (m) | 引用完整性 / 零泄漏 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `baseline` | `COMPLETED` | `[0.09587, -0.12892, 0.66000]` | `[0.10031, -0.13430, 0.67148]` | `0.00698` | `[0.11302, -0.12175]` | `0.00122` | `1.000` | `0.00729` | `True` / `False` |
| `translate_x_005` | `COMPLETED` | `[0.14587, -0.12892, 0.66000]` | `[0.15006, -0.13431, 0.67171]` | `0.00682` | `[0.15105, -0.13031]` | `0.00411` | `1.000` | `0.01245` | `True` / `False` |
| **`translate_x_010`** | **`COMPLETED`** | **`[0.19587, -0.12892, 0.66000]`** | **`[0.20121, -0.13430, 0.67171]`** | **`0.00758`** | **`[0.20190, -0.13712]`** | **`0.00290`** | **`1.000`** | **`0.00727`** | **`True` / `False`** |
| `vision_missing_negative_control` | `FAILED` (`INSUFFICIENT_MASK_PIXELS`) | `[0.14587, -0.12892, 0.66000]` | `None` | `None` | `None` | `None` | `None` | `None` | `True` / `False` (`neg_clean=True`) |

> 专项验收用例 `test_m4c_causal_audit.py`（含 `9` 项子测试）与 `test_translate_x_010_mujoco_causal_audit_convergence`（[test_m5a_control_and_budget.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/tests/test_m5a_control_and_budget.py)）全部通过。

### 2.2 控制 `AGENT` 思考预算消除长尾超时与延迟瓶颈

* **工程实现**：
  1. 在 [dual_model.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/mission/dual_model.py#L83-L143) 的 `OpenAICompatibleStructuredClient` 增加可选配置：
     * `CUBERELAY_AGENT_REASONING_EFFORT`（透传至 `payload["reasoning_effort"]`）
     * `CUBERELAY_AGENT_THINKING_BUDGET`（`role=="agent"` 默认 `1024`，可通过 `off`/`none`/`null`/`-1` 关闭，注入 `extra_body.google.thinking_config.thinking_budget`），保留充足可见输出上限防 JSON 截断。
     * 若远端 OpenAI 兼容网关不支持上述思考控制字段并返回参数错误，客户端自动剥离相关扩展字段并平滑重放请求，保证零接口报错。
  2. 解析多种兼容格式的 `reasoning_tokens`（单元测试覆盖 4 种响应格式 `412`/`333`/`256`/`128`），并在 [runners.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/benchmark/runners.py#L168-L178) 通过 `_build_token_usage` 写入 `DecisionRecord.token_usage` 与 `ClosedLoopEpisodeResult.token_usage`，协同记录 `latency_ms` 与 `agent_latency_ms`。

#### Live `L1..L4`（`GUIDE_MINIMAL`, `LLM_AGENT_CV_ONLY`, `agent=gemini-3.8-flash`, `thinking_budget=1024`, `n=26`）延迟与准确度统计

| 指标项 | M4-E 历史基线 | M5-A 受控思考预算实测（26 Cases） |
| :--- | :--- | :--- |
| 单步平均延迟 `mean_latency_ms` | ~`13,600–16,600 ms` | **`4,343.13 ms`**（`mean_agent_latency_ms = 4,341.54 ms`） |
| 中位 / P95 / 最大延迟 | 长尾最高 `91.5s`（`MODEL_TIMEOUT`） | `median = 4,168.16 ms` / `p95 = 5,192.89 ms` / **`max = 6,504.04 ms`** |
| 超时与非成功调用数 | 存在 `MODEL_TIMEOUT`（如 `CL_05`） | **`timeouts = 0`**, **`non_success_calls = 0`** |
| Oracle 通过数 / 决策合规 | — | **`25 / 26`**（仅 `L3_08_C4_VLM_LOW_CONFIDENCE_NO_EVIDENCE` 未通过 Oracle） |
| Safety 门控通过数 | — | **`26 / 26`** |
| `reasoning_tokens` 端到端观测 | 未统计 | 框架透传与单元测试 `4/4` 通过；本次远程代理响应 `usage` 未回传该字段（`reasoning_tokens_logged_count = 0`） |

---

## 三、 Part 2：全六面 26-Cubie 物理魔方 + 单顶层夹具 + 单臂翻面喂料

### 3.1 26-Cubie 持久化物理魔方结构与物理诚实红线

在 [physical_cube_26.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/embodied/physical_cube_26.py) 中，使用 `build_26_cubie_scene` 动态扩展基础场景 XML，彻底取代原 `physical_u.py` 的上下两砖结构：

* **几何与刚体架构**：
  * **中心载体 `cube_core`**（携带 6-DoF `freejoint="cube_free"`）：承载桌面支承、手爪抓取、搬运与 90° 侧翻时的整体刚体动力学。
  * **26 个持久化小块刚体**（`cubie_00..25`，格距 `CUBIE_STEP = 0.040 m`，半边长 `CUBIE_HALF_SIZE = 0.0198 m`，整颗魔方净宽 `119.6 mm`，放置桌面 `z=0.600` 后质心高度 `0.6598 m`）：54 张彩色贴片几何体作为对应 cubie 的子几何永久固定绑定，零动态换父体/换色。
  * **6 个同心被动铰链载体**（`carrier_{U,D,F,B,L,R}`）+ `mjEQ_WELD` 焊接约束（`w_core_*` 锁于 `cube_core`，`w_car_*` 连至对应轴转面载体）：自由搬运/抓取/放置阶段 26 个小块锁紧于其当前连续物理相对姿态（`_live_relpose_quat`），零位姿跳变、零瞬移。
* **真物理驱动与机械卡滞机制**：
  1. 转面时仅通过真实 3D 世界高度筛选位于夹具顶层的 9 个 cubie（`select_top_layer_from_world_coords`），释放为绕顶面法向旋转，下两层 17 个 cubie 由夹具底层对称垫块物理锁固。
  2. 顶层 9 个小块的 `±90° / 180°` 旋转 **100% 由上层夹具 `turn_pos_pad` / `turn_neg_pad` 的双向法向压紧与切向摩擦接触驱动**。
  3. **错层卡滞 (`SLICE_MISALIGNED_JAM`)**：切换转轴前严格执行 `validate_lattice_alignment(tol_deg=8.0)`；若前序转面偏离 `90°` 晶格容差，严禁软件吸附对齐，真实拦截并上报错层高度离散（如 `-14.999°` 部分转面后再切 `R'` 轴触发 `z spread=22.4mm > 8mm`）。
  4. **运行时防作弊锁**：`MuJoCoEmbodiedBackend` 启用 `_sticker_colors_locked` 阻断 `reset` 后任何 `_set_sticker_colors` 调用；启用 `full_26_cubie=True` 时 `execute_physical_turn` 直接抛出 `RuntimeError`；全过程 54 格状态由 `extract_54_geom_facelets_state` 直接读取物理世界坐标验证。

### 3.2 单顶层夹具 `±90° / 180°` 与单臂“翻面喂料（Flip-and-Feed）”

* **单顶层夹具双向与半圈支持**：`move_to_top_fixture_angle_rad` 严格对齐 [moves.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/cube/moves.py) 右手定则定义（如 `U -> -90°`, `U' -> +90°`, `U2 -> -180°` 等），通过 `ActionChunkExecutor` 光滑驱动 `turn_rotor_ctrl` 与对称夹紧垫块，经 `test_all_18_moves_real_flip_and_contact_fixture_54_cell_equivalence` 逐一验证全部 18 个标准动作。
* **3D 朝向跟踪器与三类翻面路径**（[flip_and_feed.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/embodied/flip_and_feed.py)）：
  * `CubeOrientationTracker` 基于 RGB-D 中心块观测与已验证物理翻面动作显式维护 `24` 种离散旋转矩阵与连续表盘偏航角，统计 `flips_executed`、`regrasps_executed` 与 `flip_time_s`，不读任何 `qpos`/`xpos`/`xmat`。
  * **关键物理稳定性工程修复**（本次实测排障落地）：
    1. **俯视视觉去遮挡与侧翻后重定位（`_relocalize_laid_cube`）**：先将机械臂安全停泊至 `(-0.42, 0.25)` 再采集 `overhead` RGB-D，消除腕部遮挡导致的 `-26.2°`（`45°` 偏移）yaw 误判（恢复为 `18.43°`，误差 `<0.05°`）；桌面 2 次翻面倒手间复用腕部下视相机 `inspection_down_neg_y` 深度方形轮廓角完成连续偏航纠偏。
    2. **质心抓取高度与手指夹持力匹配**：桌面/工位抓取统一采用 `z_grasp=-0.282`（靠近质心高度且与桌面保留安全余量，避免 `table` 摩擦顶死夹爪）并提高持握控制指令至 `grip_ctrl=0.082`，将 `flipA` 拆分为先垂直平转 `flipA_yaw_to_zero` 后俯仰 `flipA_pitch_neg90` 的解耦时序，消除 `-pi -> 0` 同步高速旋转引发的手指打滑与工位垫块碰撞。
    3. **桌面无旋侧放连招（`Flip B` 2-Flip 首翻）**：改进 `_lay_cube_90deg_on_table` 为俯仰 `88°` 轻触桌面 → 双指同步完全松开（`0.0 / 0.0`，消除单指拖拽造成的 `52.3°` 桌面旋转）→ 垂直抬升 Clear → 水平退避后再回正手腕，桌面 Yaw 飘移压制至 **`< 1°`**。

### 3.3 全六面物理转面、跨轴序列与负对照实测结果

| 验证项目 | 执行路径 / 参数 | 实测关键指标与物理证据 | 结果 |
| :--- | :--- | :--- | :--- |
| **18 动作符号-物理方向一致性** | `U/R/F/D/L/B` × `(90°, ', 2)` 全部 18 动作 | 每轴首动分别经历 `0 / 1 / 2` 次翻面，全部 18 步后 54 贴片几何位置与 `CubeEngine.apply_move` **0 格偏差**，`geom_rgba` 零改写 | **18/18 PASS** |
| **跨轴序列 1：`U -> R' -> D2`**（单 `MjModel/MjData`，[verification_report.json](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/results/m5a_cross_axis_u_rp_d2/verification_report.json)） | `seed=0` 打乱 4 步，连续执行 `U`（0 翻）→ `R'`（1 翻）→ `D2`（1 翻，180°） | `U`: `angle_err=0.0°`, `misalign=0.078°`, `top_hits=839/base_hits=920`<br>`R'`: `angle_err=0.004°`, `misalign=0.107°`, `top_hits=838/base_hits=920`<br>`D2`: `angle_err=0.005°`, `misalign=0.105°`, `top_hits=1340/base_hits=1420`<br>独立相机复核：`observed_count=54, conflict_count=0, unknown_count=0`，100% 匹配 | **PASS**（含视频 [cross_axis_u_rp_d2.mp4](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/results/m5a_cross_axis_u_rp_d2/cross_axis_u_rp_d2.mp4)） |
| **2-Flip 桌面倒手 `U -> D2`** | `seed=3` 随机偏航，先执行 `U` 后执行底面 `D2` | `D2`: `flips_executed=2`, `regrasps_executed=1`, `angle_error_deg=0.087°`, `max_slice_misalignment_deg=0.156°`, `top_hits=1229/base_hits=1420`, `total_flip_time_s=31.098`；独立相机 **54/54, 0 冲突** | **PASS** |
| **负对照：关闭上层夹具垫块碰撞** | `execute_top_face_turn(-pi/2, contact_enabled=False)` | `success=False`, `failure_code=CONTACT_DRIVE_FAILED`, `top_pad_contact_steps=0`, `actual_deg=-0.00` (`actual_angle_rad=-3.19e-10`), `error_deg=90.0°` | **PASS（真实失败拦截）** |
| **错层卡滞控制：`SLICE_MISALIGNED_JAM`** | `-15°` 部分转面（实际 `-14.999°`）后切换垂直轴 `R'` | `success=False`, `failure_code=SLICE_MISALIGNED_JAM`, `max_slice_misalignment_deg=15.005°`, `Top 9 cubies are not coplanar (z spread=22.4mm > 8mm)` | **PASS（真实卡滞拦截）** |
| **`SimulationSession(SOLVE_CUBE)` 端到端求解** | `seed=0, full_26_cubie=True, scramble_steps=2`；`SkillRegistry(physical_full_cube=True)` | 完整经由 `observe -> active_six_face_scan -> validate -> plan ['U', "L'"] -> check_capability -> execute_physical_face_turn ×2 -> verify_post_turn_state` 收敛为 `COMPLETED`，全六面独立相机 54/54 匹配 | **PASS** |

---

## 四、 Part 3：统一可中断 `ActionChunkExecutor` 底座（兼容 VLA）

### 4.1 架构设计

* **统一执行契约**（[action_chunk.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/execution/action_chunk.py)）：
  * `ActionChunk` 同时兼容经典确定性技能（`source_type="CLASSICAL_SKILL"`，提供 `linear_ramp` 与 `trapezoidal_xy` 构造函数）与后续 VLA 策略（`source_type="VLA_POLICY"`，携带 `world_revision`、`goal_revision` 与 `pose_estimate_id`）。
  * 懒加载 `import mujoco` 于 `ActionChunkExecutor.__init__`，确保纯软件非 GL 宿主环境无渲染库也能正常导入任务与校验模块。
* **线程安全抢占与安全保压悬停**：
  * `CancellationToken` 支持 `IMMEDIATE_HOLD` 与 `SAFE_CHECKPOINT` 模式。
  * `_enter_safe_hold` 通过 **`eq_sag = clip(qfrc_bias[dof_z] / kp_z, 0.0, 0.060)`** 精确前馈平衡垂直重力偏置（消除空载下落期间按瞬时控制差钳位引起的 `-0.0394 m/s` 重力漂移），锁定当前编码器 `xy_anchors` 并施加强粘滞制动（`kd_brake=0.65`），同时若 `hold_grip_on_interrupt=True` 则持续维持指压防松爪掉魔方。
  * 在 `ActionChunkExecutor._validate_invariants` 强制校验有限数值、步长跳变上限与 `world_revision / goal_revision` 一致性。

### 4.2 抢占与安全基准实测指标

| 测试场景 | 状态转移 `ChunkStatus` | 中断至安全停稳仿真耗时 (`<100 ms` 门限) | 最终末端速度范数 | 附加安全验证 |
| :--- | :--- | :--- | :--- | :--- |
| **空载高速横移进近动态抢占** | `PREEMPTED_SAFE_HOLD` | **`14.00 ms`**（7 步以内） | **`0.01653 m/s`**（`< 0.025 m/s`） | 零过冲安全悬停 |
| **持握 26-Cubie 魔方搬运抢占** | `PREEMPTED_SAFE_HOLD` | **`18.00 ms`** | **`0.01959 m/s`** | `hold_grip_preserved=True`, `object_drop_detected=False`, `closures=(0.0439, 0.0692)` |
| **`VLA_POLICY` 世界版本过期中止** | `SAFETY_ABORTED` | 步 30 即时触发（`30` 步处版本变更） | 安全中止退出 | `safety_violation = "STALE_WORLD_REVISION:10!=11"` |
| **顶层夹具接触转面中段抢占** | `PREEMPTED_SAFE_HOLD` | 在物理转层过程中立即中断 | 安全停机 | `preempted=True, failure_code="PREEMPTED", max_slice_misalignment_deg=7.71e-10°` |

---

## 五、 全量测试与回归验证矩阵

> 所有 MuJoCo 与 EGL 测试均在 Docker 仿真容器 `cuberelay-m5a-test`（Python 3.12 + MuJoCo 3.3.7 EGL）中完成并记录真实结果；宿主机 Python 3.14 环境未安装 `mujoco`，同步汇报宿主机非 GL 测试输出。

| 验证范围与执行环境 | 运行命令 | 结果汇总 | 说明与未通过项精准说明 |
| :--- | :--- | :--- | :--- |
| **M5-A 全部新增专项套件（容器）** | `pytest -v tests/test_m5a_action_chunk.py tests/test_m5a_control_and_budget.py tests/test_m5a_full_cube.py` | **`16 passed` (`0 failed`, `88.93s`)** | 覆盖 ActionChunk 抢占、思考预算、+10 cm 因果审计、18 动作全等价、负对照/错层卡滞、跨轴 `U->R'->D2`、2-Flip `U->D2`、54/54 独立相机及 `SOLVE_CUBE` |
| **M3-D + M4-A~E + M5-A 核心回归集（容器）** | `pytest -q tests/test_physical_u.py tests/test_m3d_orchestration.py tests/test_m4a_vlm_loop.py tests/test_m4b_dual_model.py tests/test_m4c_causal_audit.py tests/test_m4d_benchmark.py tests/test_m4e_consolidation.py tests/test_replay_timing.py tests/test_m5a_*.py` | **`88 passed` (`0 failed`, `158.96s`)** | 既有 M3-D 单 U 层、VLM 双模型主链、M4-C 因果审计、M4-D Benchmark 与 M4-E 架构规整全部无回归保持 100% 通过 |
| **仓库全量测试集（容器，含旧版 v2 集成基线）** | `pytest -q` | **`249 passed, 5 failed` (`170.26s`)** | 仅遗留基线 [test_mujoco_integration.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/tests/test_mujoco_integration.py) 5 项失败：<br>1) 3 项历史硬编码“必失败/多轮重试”断言（`seed=9` 由失败改为首抓成功，`attempts=1` 代替 `seed=1` `attempts==2` 与 `seed=56` `attempts==3`）因 Part 1.1 修复 XY 过冲而首次尝试即成功；<br>2) `seed=1` 两项（`test_v2_random_scene_rgbd_localize_grasp_lift_rotate_reobserve` 与 `test_v2_occlusion_recovery_...`）在旧单砖模型夹爪力保持校验处因 `right_normal_force_n=2.232N`（`contact=0.933`）停止 |
| **宿主机非 GL 测试（macOS Python 3.14）** | `env CUBERELAY_SKIP_GL_TESTS=1 PYTHONPATH=src pytest -q` | `202 passed, 19 skipped, 22 failed, 4 errors` (`10.87s`) | 宿主机无 `mujoco` 包：`test_m5a_control_and_budget.py` 6 项非 GL 单测及全部纯逻辑单测通过；22 失败与 4 错误仅位于强制实例 MuJoCo 的 `test_six_face_inspection.py`、`test_visual_turn_loop.py`、`test_m3d_orchestration.py`（未配置 EGL Skip），已在 `cuberelay-m5a-test` 容器内完整执行 |

---

## 六、 M5-B / M5-C 后续演进建议

1. **M5-B（实时动态交互与抢占重规划）**：可直接复用 `ActionChunkExecutor` 与 `CancellationToken`，在人体接近安全阈值触发 `PREEMPTED_SAFE_HOLD`（`14–18 ms` 内停稳且零掉落）后，基于最新 `world_revision` 重新下发局部避让或交接 Chunk。
2. **M5-C（挂载 VLA 策略）**：`ActionChunk` 已原生承载 `source_type="VLA_POLICY"`、`world_revision` 与 `goal_revision` 防陈旧中断校验，后续仅需将 VLA 输出的相对关节/笛卡尔控制序列封装为固定步长 `ActionChunk` 即可无缝接入现有安全护栏与保压悬停机制。
