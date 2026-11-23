# CubeRelay M5-A.1：26-Cubie 多 Seed 物理鲁棒性标定、半拧抢占回退与全绿清障技术报告

> **报告日期**：2026-11-19  
> **任务阶段**：M5-A.1（M5-B 快慢双环异步人机交互核心算法前置排雷与物理标定）  
> **核心交付物**：
> - 半拧抢占回退恢复原语与晶格前置守卫：[physical_cube_26.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/embodied/physical_cube_26.py)、[flip_and_feed.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/embodied/flip_and_feed.py)、[mujoco_v2.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/embodied/mujoco_v2.py)、[action_chunk.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/execution/action_chunk.py)、[skill_registry.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/mission/skill_registry.py)
> - 20-Seed 压测脚本与实测翻面代价先验：[calibrate_m5a1_flip_and_feed.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/scripts/calibrate_m5a1_flip_and_feed.py)、[flip_cost_profile.json](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/results/m5a1_calibration/flip_cost_profile.json)
> - 26-Cubie 会话标准配置与 API 统合：[session.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/mission/session.py)、[planner.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/mission/planner.py)、[main.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/api/main.py)、[server.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/server.py)
> - 硬化专项单测与历史回归全绿清理：[test_m5a1_hardening.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/tests/test_m5a1_hardening.py)、[test_mujoco_integration.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/tests/test_mujoco_integration.py)、[test_six_face_inspection.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/tests/test_six_face_inspection.py)、[test_visual_turn_loop.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/tests/test_visual_turn_loop.py)、[test_m3d_orchestration.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/tests/test_m3d_orchestration.py)

---

## 一、 执行摘要（Executive Summary）

围绕 M5-A 遗留的 4 项工程隐患，M5-A.1 在不引入新 LLM 算法、不放宽接触证书门槛、不修改 M4-D/E 评测结论的前提下完成了全部物理排雷、多 Seed 标定与双环境全量回归清障：

1. **Task 1（半拧安全回退与晶格对齐守卫）**：实现了转面工位晶格状态追踪（`is_lattice_aligned`、`residual_slice_angle_rad/deg`）与纯接触恢复原语 `recover_preempted_turn_slice(mode="UNWIND_TO_ZERO" | "ALIGN_NEAREST_DETENT")`；未恢复前强制阻断任何提离、翻面或切轴尝试（`SLICE_MISALIGNED_JAM` + `SkillRegistry` 前置守卫 `station_lattice_aligned`）；实测在 `U` 转至 `-35° ~ -50°` 触发 `CancellationToken` 后安全阻断 `R'`、纯接触回退至 `< 2.0°`（54 格状态与转前完全一致）并紧接完成翻面 + `R'` 100% 成功。
2. **Task 2（20-Seed 随机物理压测与翻面代价标定）**：通过 [calibrate_m5a1_flip_and_feed.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/scripts/calibrate_m5a1_flip_and_feed.py) 定位并修复了工位近邻抓持垫块干涉、初始倾斜魔方 45° 视觉角混淆、2-Flip `flipB` 平滑退爪与姿态跟踪协同、`turn_station` 提取与桌放低落差抛物翻转等真实物理缺陷，在 **`seeds = 0..19`** 上实测 **`0_flip` 19/20（95.0%）**、**`1_flip` 20/20（100.0%）**、**`2_flip` 19/20（95.0%）** 与 **连续 3 步混合序列 10/10（100.0%）**，并将真实带失败分类统计导出至 [flip_cost_profile.json](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/results/m5a1_calibration/flip_cost_profile.json)。
3. **Task 3（`full_26_cubie=True` 标准配置统合与双环境全绿清障）**：在 LIVE `/api/m3d/*`（[main.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/api/main.py)）与 [server.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/server.py) 中启用 `full_26_cubie=True` + `SkillRegistry(physical_full_cube=True)` 为标准运行配置（支持 `RESET_SCENE` / `START_MISSION` / `SET_FULL_26_CUBIE` / `POST /api/m3d/configure` 显式切换），同时完整保留 `SimulationSession(full_26_cubie=False)` 的 M3-D/M4-D 兼容默认值与 `CL_05` 能力阻塞验证。容器内全量测试 **`259 passed, 0 failed, 0 errors`**；宿主机非 GL 测试 **`204 passed, 48 skipped, 0 failed, 0 errors`**。

---

## 二、 Task 1：转面中途抢占“半拧安全回退”与晶格守卫

### 2.1 物理实现与零真值/零瞬移保证

1. **实时制动与晶格状态同步**：
   - 在 [action_chunk.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/execution/action_chunk.py#L416-L455) 的 `_enter_safe_hold` 中新增对 `turn_rotor_ctrl` 的 live `qpos` 锚定，防止转面抢占制动时转子弹性回弹。
   - 在 [physical_cube_26.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/embodied/physical_cube_26.py#L673-L685) 中维护 `is_lattice_aligned`、`residual_slice_angle_rad/deg`、`preempted_slice_axis`、`preempted_top_cubie_indices`、`refresh_lattice_status`，并在中段抢占时保留上下夹具闭锁力，避免半拧块脱离。
2. **`recover_preempted_turn_slice` 纯接触恢复**：
   - 位于 [physical_cube_26.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/embodied/physical_cube_26.py#L1121-L1310) 与 [mujoco_v2.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/embodied/mujoco_v2.py#L3510-L3541)。严禁任何 `qpos` 改写或软件瞬移：通过测量当前顶层残余偏角 `alpha_rad`，对齐上夹具转子与底座夹持垫块接触后，通过 `ActionChunkExecutor` 驱动 `turn_pos_pad / turn_neg_pad` 施加真实接触摩擦力矩反向回退至 `0°`（`UNWIND_TO_ZERO`）或补齐至最近 `90°` 晶格位（`ALIGN_NEAREST_DETENT`）。
   - 回退结束后经 `validate_lattice_alignment(tol_deg=8.0)`（恢复门槛 `LATTICE_RECOVERY_TOL_DEG = 2.0` deg）确认所有刚体块对齐后才将小块锁回 `cube_core` 并松开夹具。
3. **多层前置守卫**：
   - **执行器层**：[physical_cube_26.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/embodied/physical_cube_26.py)（`execute_top_face_turn`）、[flip_and_feed.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/embodied/flip_and_feed.py#L468-L526)（`_pick_up_cube` 与 `orient_face_up_and_dock`）及 [mujoco_v2.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/embodied/mujoco_v2.py#L3543-L3573) 均同步检查 `is_lattice_aligned`，只要 `not is_lattice_aligned`，直接返回 `SLICE_MISALIGNED_JAM` 并拒绝提离或切轴。
   - **技能规划层**：[skill_registry.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/mission/skill_registry.py#L323-L575) 注册了 `recover_preempted_turn_slice`（仅 `physical_full_cube=True` 时激活），为 `execute_physical_face_turn`、`regrasp_cube`、`reorient_cube` 及 `can_execute_physical_move` 增加 `station_lattice_aligned` 前置条件；同时在 [planner.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/mission/planner.py#L418-L431) 对纯观测/单 `U` 兼容任务屏蔽该技能，在 [session.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/mission/session.py#L3398-L3470) 的 `_execute_plan_step` 同步更新 `scene_state["is_lattice_aligned"]` 与 `residual_slice_angle_deg`。

### 2.2 必过单测实测结论

由 [test_m5a1_hardening.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/tests/test_m5a1_hardening.py) 在 MuJoCo 真实物理引擎中实测通过（5/5）：
* `test_preempted_mid_slice_unwind_to_zero_and_subsequent_r_prime`：`U` 转行进至 `-38°` 区间触发 `CancellationToken(IMMEDIATE_HOLD)` 停于 `PREEMPTED_SAFE_HOLD`（残余偏角在 `-35° ~ -50°`、`is_lattice_aligned=False`）→ 尝试直接切换 `R'` 与 `FlipAndFeed` 提取均被阻断并返回 `SLICE_MISALIGNED_JAM` → 调用 `recover_preempted_turn_slice("UNWIND_TO_ZERO")` 通过顶层接触力矩回退至 `< 2.0°`（`contact_driven=True`、`top_pad_contact_steps > 0`），54 格几何状态与转前完全一致 → 紧接着执行翻面 + `R'` 100% 成功（`< 2.0°` 晶格残差、54 格严格吻合 `CubeEngine.apply_move(init, "R'")`）。
* `test_recover_preempted_turn_slice_align_nearest_detent`：中段过半抢占后通过 `ALIGN_NEAREST_DETENT` 纯接触补齐至 `-90°` 晶格位，残差 `< 2.0°` 且 54 格等价。

---

## 三、 Task 2：20-Seed 随机压测排障与翻面代价实测标定

### 3.1 多 Seed 压测暴露并修复的真实物理瓶颈

在不改变 `reset_random` 初始随机分布、不放宽接触门槛且不读取运行时隐藏 `qpos` 真值的前提下，[calibrate_m5a1_flip_and_feed.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/scripts/calibrate_m5a1_flip_and_feed.py) 覆盖 `seeds = 0..19` 的随机工作区坐标与连续偏航角，定位并修复了以下 4 类确定性轨迹/视觉缺陷：

1. **工位旁随机抓取垫块干涉（`seed=9, 17`）**：新增 `select_collision_free_table_yaw`（利用 4 重对称性选取距 `turn_station` 与桌缘净空最大的抓取 yaw）并在近工位 `near_station` 抓取前主动缩回 `base_clear_ctrl = 0.25`。
2. **初始大偏角魔方中心判别混叠（`seed=1, 8, 15, 16`）**：对初始位置偏移较大或旋转斜置的桌面魔方，先由单臂夹持归正至 `(0.0, 0.0, yaw=0.0)` 后再执行 `task_observe_released()` 全六面主动扫描，消除 45° 边角视角引起的面中心色混叠与边缘出框漏检。
3. **跨轴连续序列工位提取碰撞与 YAW 阶跃甩脱（`mixed_3_step_sequence` `seed=0..9` 原 `0/10`）**：排查发现 `_lay_cube_90deg_on_table`（`flipB`）在从工位提取（`is_station=True`）后于 `flipB_lift` 阶段过早闭合 `base_clear_ctrl = 0.0` 且在 `flipB_move_table` 注入 `wrist_yaw_ctrl = 0.0` 瞬态阶跃，导致底座垫块撞击及半悬空甩脱。现已改在起吊后先经平滑 `flipB_yaw_to_zero`（`0.52s`）归零、携带移至 `(0.0, 0.0)` 脱离工位后才于 `flipB_pitch_90deg` 复位 `base_clear_ctrl = 0.0`。
4. **2-Flip 桌放高抛后翻缺陷（`seed=5` `D2->F2` 与 `mixed` `L2->B2`）**：原 `flipB` 存在 `flipB_pitch_88deg` 重力下垂欠角及 `flipB_lift_clear(robot_z_ctrl=-0.04)` 将魔方连带托高 `19 cm` 后抛落引起 `-90°` 绕 X 轴后滚翻的边界效应。调整为 `wrist_pitch_ctrl = 90°`、低位退爪抬升高度 `robot_z_ctrl = -0.22` 及干脆水平抽离（`0.12s`, `away * 0.20 m`），彻底消除了高抛翻滚。

### 3.2 `flip_cost_profile.json` 实测汇总统计

产物路径：[flip_cost_profile.json](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/results/m5a1_calibration/flip_cost_profile.json)（`schema_version: cuberelay_m5a1_flip_cost_profile_v1`，统计时间 `2026-11-19T07:59:47Z`）：

| 转面路径类别 | 样本数 (`sample_count`) | 成功数 (`success_count`) | 实测成功率 (`empirical_success_rate`) | 平均仿真耗时 (`mean_sim_time_s`) | P95 仿真耗时 (`p95_sim_time_s`) | 平均重抓次数 (`mean_regrasps`) | 失败分布 (`failure_breakdown`) |
|---|---:|---:|---:|---:|---:|---:|---|
| **`0_flip`**（顶面 `U/U'/U2`） | 20 | 19 | **95.0%** (`0.95`) | `32.9776 s` | `34.7006 s` | `0.0` | `UNEXPECTED_FLIP_COUNT`: 1 |
| **`1_flip`**（`R/F/L/B` 四侧单翻） | 20 | 20 | **100.0%** (`1.00`) | `34.4455 s` | `35.9802 s` | `0.0` | 无 |
| **`2_flip`**（底面 `D/D'/D2` 桌放重抓） | 20 | 19 | **95.0%** (`0.95`) | `42.3562 s` | `43.9400 s` | `1.0` | `UNEXPECTED_FLIP_COUNT`: 1 |
| **`mixed_3_step_sequence`**（连续 0→1→2 跨轴 3 步） | 10 | 10 | **100.0%** (`1.00`) | `79.9110 s` | `81.8731 s` | `1.0` | 无 |

> **如实失败记录说明**：未作任何种子筛选。唯一未通过种子为 `seed=10`：该种子初始 `reset_random(10)` 随机落点恰与工位闭合区 `base_pos_pad` 几何重叠，导致场景初始化阶段方块即被碰撞翻倒（上下倒置），随后物理操作虽仍完成 54 格精确等价转面（`angle_error_deg = 0.0°`、`max_slice_misalignment_deg = 0.078°`），但实际翻面次数偏离直立初始预期（`0_flip` `U'` 实执 `2` 次翻面；`2_flip` `D'` 实执 `0` 次翻面），按严格标定断言记为 `UNEXPECTED_FLIP_COUNT`。

---

## 四、 Task 3：26-Cubie 标准配置统合与双环境测试集 100% 全绿

1. **统合 `full_26_cubie` 会话配置**：
   - [session.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/mission/session.py)：保留 `SimulationSession(..., full_26_cubie: bool = False)` 默认兼容性；新增 `reconfigure_full_26_cubie` 与 `_apply_full_26_cubie_sync` 在 GL 线程安全切换 MuJoCo 后端与 `SkillRegistry(physical_full_cube=...)`，并在 `reset_scene`、`start_mission_async`、`run_mission` 与快照中完整暴露 `full_26_cubie`、`physical_full_cube` 与 `is_lattice_aligned`。
   - [main.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/api/main.py) 与 [server.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/server.py)：LIVE `/api/m3d/*` 服务默认 `_m3d_default_full_26_cubie = True`（可通过 `CUBERELAY_M3D_FULL_26_CUBIE` 环境变量、CLI `--full-26-cubie` / `--legacy-u-only`、命令 `SET_FULL_26_CUBIE` / `CONFIGURE_SESSION` 或 `POST /api/m3d/configure` 显式配置）。
2. **清理 [test_mujoco_integration.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/tests/test_mujoco_integration.py) 历史 5 项失败**：
   - 将 [mujoco_v2.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/embodied/mujoco_v2.py#L1552-L1562) 中 `approach_grasp_lift` Z 轴下探从 0.65s 阶跃目标恢复为平滑三次方轨迹（`_guarded_stage_motion(..., guarded=False)`），消除接触反弹，使 `seed=1` 的两项旧 v2 测试（`test_v2_random_scene_rgbd_localize_grasp_lift_rotate_reobserve` 与 `test_v2_occlusion_recovery_uses_place_release_observe_regrasp_rotate`）在不放宽 `GraspCertificate` 的前提下直接全绿通过。
   - 更新因 Part 1.1 修复 XY 过冲后已首抓成功的 3 个旧用例断言（`seed=9`、`seed=1` `SkillBasedGraspAgent`、`seed=56` `FailureAwareSkillAgent` 均一次抓取成功 `attempts=1`），并在 `test_v2_failed_random_grasp_is_reported_not_welded` 中保留了受控侧向闭爪扰动测试以继续验证失败诚实上报与零焊接作弊。
3. **清理宿主机无 `mujoco` 跳过守卫**：
   - 为 [test_six_face_inspection.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/tests/test_six_face_inspection.py)、[test_visual_turn_loop.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/tests/test_visual_turn_loop.py)、[test_m3d_orchestration.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/tests/test_m3d_orchestration.py) 与 [test_mujoco_integration.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/tests/test_mujoco_integration.py) 补齐 `CUBERELAY_SKIP_GL_TESTS=1` 与 `importlib.util.find_spec("mujoco") is None` 的标准 `pytest` 跳过守卫（纯符号与编排单测保持照常运行）。

### 全量验证命令与结果

| 验证环境 | 执行命令 | 实测结果 | 状态 |
|---|---|---|---|
| **Docker 容器（`cuberelay-m5a-test`：`linux` + Python 3.12.3 + MuJoCo 3.3.7 EGL）** | `docker exec cuberelay-m5a-test pytest -q` | **`259 passed`**, `0 failed`, `0 errors` (`207.61s`) | **PASS** |
| **宿主机（`darwin` macOS + Python 3.14.6，无 MuJoCo）** | `CUBERELAY_SKIP_GL_TESTS=1 PYTHONPATH=src pytest -q` | **`204 passed, 48 skipped`**, `0 failed`, `0 errors` (`13.66s`) | **PASS** |
