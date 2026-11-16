# CubeRelay 回放时间对齐与运动耗时审计报告

## 结论摘要

针对单场景真物理全流程（`scripts/physical_u_step.py --seed 0`，初始扫描 + 重抓 + Pitch 观测 + 搬运对接 + 外置接触拧动 U 面 + 拧后释放验证）已出现“仿真实际耗时 `60.770 s` 而 `episode.mp4` 长达 `210.75 s`（`2,529` 帧 @ `12 fps`）、扫描与上下移动后机械臂重新缓慢入场”的问题，本轮在不改动任何控制轨迹与物理参数的前提下完成配对录制审计与仿真时钟回放修复：

| 对比维度 | 修改前基线 (`legacy`) | 修改后 (`sim_time`) | 变化 / 验证结果 |
|---|---:|---:|---|
| 控制/物理步数 (`physics_steps`) | `30,385` | `30,385` | **完全一致**（`dt = 0.002 s`，零跳步） |
| 物理状态摘要 (`physics_digest`) | `f5b5b62faa798ede...7eadcf7` | `f5b5b62faa798ede...7eadcf7` | **逐物理步 `(qpos, qvel)` SHA-256 完全一致** |
| 有效仿真时间跨度 (`sim_time`) | `0.400 → 61.170 s` (`60.770 s`) | `0.400 → 61.170 s` (`60.770 s`) | **完全一致**，最终状态 `AFFECTED_21_VERIFIED` |
| 视频总帧数 (`episode.mp4` @ `12 fps`) | `2,529` 帧 | `730` 帧 | 移除高频超采与零间隔快照（`-71.1%`） |
| 视频播放总时长 (`duration`) | `210.75 s` | `60.833 s`（元数据 `60.83 s`） | **总倍速从 `3.468x` 恢复至 `1.001x`** |
| 逐帧时间分布 (`dt_min / p50 / dt_max`) | `0.000 / 0.002 / 1.216 s` | `0.082 / 0.084 / 0.084 s` | 对齐至 `1/12 s = 0.0833 s`；误差 `<= 0.002 s` |
| 两次 `capture_released_views` (`4.760 s` 仿真) | `1,756` 帧 / `146.33 s` (`30.74x`) | `57` 帧 / `4.75 s` (`1.00x`) | 消除 `20 ms` 周期下约 `41.7x` 的回放放慢 |
| 全套回归测试 (`pytest -q`) | — | `173 passed in 28.83s` | 含 [`tests/test_replay_timing.py`](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/tests/test_replay_timing.py) `4 passed` |

**核心定位结论：**
1. **“首次扫描与上下移动后重新缓慢入场”纯粹是视频编码采样率与播放帧率失配导致的回放假象，不是仿真运动慢**。`_move_gantry_xy_damped` 每次以 `step_seconds = 0.02 s` 调用 `_set_controls(..., 0.02)`；在旧 `legacy` 模式下，`_set_controls` 以 `sample_every = max(1, 10 // 6) = 1` 在每个 `2 ms` 物理步录制 1 帧（`500 fps`），却统一按 `12 fps` 编码，造成主移动循环 **`500 / 12 = 41.67x`** 的时间膨胀（叠加末尾 `0.08 s` tail 后，单次 `_move_gantry_xy_damped` 平均被拉长为 **`37.22x–38.14x`**）。事实上，仿真中两次“重新入场”（片段 `[18]` 和 `[139]`）仅用 **`0.680 s`** 和 **`0.780 s`**，TCP 平均速度达 **`1.431 m/s`** 和 **`1.892 m/s`**，稳态误差 `<= 0.45 mm`。
2. **整段轨迹中真实存在但被视频假象掩盖的控制等待/振荡问题**：
   - `task_align_scan_axes` 与 `task_reorient` 调用的 `_monitored_rotation` 固定运行 `4.000 s`（例如 `task_regrasp` 内部片段 `[115]` 在 `wrist_yaw_joint` 已处于 `1.5708 rad`、`Δyaw = 0.0000 rad` 时仍空跑 `4.000 s`）；
   - `ContactUTurn` 中若干固定时长动作提前收敛并长时间静止等待（如 `[136] BASE_CLEAR_FOR_VISION` `2.000 s` 中静止 `1.892 s`，`[123] BASE_CLOSE` `2.000 s` 中静止 `1.328 s`，`[125] ROBOT_RELEASE` `1.000 s` 中静止 `0.714 s`）；
   - 第二次 `capture_released_views` 开头的 `[138] _set_controls(..., 0.45)` 在夹爪本已打开且停于 `robot_z_ctrl=-0.02` 时完全静止空等 `0.450 s`；
   - `[14]` 首次 `task_place_release` 中的无阻尼 XY 阶跃退避（`targets={'robot_x_ctrl': -0.45, 'robot_y_ctrl': 0.45}, 0.8 s`）作用于欠阻尼龙门架（`ζ ≈ 0.030`），在 `0.661 m` 净位移上产生 `2.654 m` 来回振荡路径。

---

## 1. 对齐 MuJoCo `sim_time`、录制帧时间戳与视频播放时间

为保证不跳过任何物理步、不插值伪造画面，在 [`src/cube_relay/embodied/replay_timing.py`](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/embodied/replay_timing.py) 中新增了三部分非侵入式机制并集成至 [`src/cube_relay/embodied/mujoco_v2.py`](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/embodied/mujoco_v2.py) 与 [`src/cube_relay/embodied/physical_u.py`](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/embodied/physical_u.py)：

1. **`MuJoCoEmbodiedBackend.step_physics()` 统一节拍**：所有 `mj_step` 推进均调用 `step_physics()`，同步触发 `self.motion_timing.tick()` 与 `self.frames.capture_due()`。
2. **`TimedFrames` 严格仿真时钟采样（`video_timing="sim_time"` 默认开启）**：
   - 在 `sim_time` 模式下，`capture_due()` 仅当 `data.time + 1e-9 >= next_capture` 时渲染当前默认 `video_camera` 并记录 `float(data.time)`，随后 `next_capture += 1.0 / video_fps`（`12 fps` 对应 `0.08333... s`，离散化为 `0.082 s` 或 `0.084 s` 物理步）。
   - `TimedFrames.append()` 在非 `legacy` 模式下直接忽略感知回调（`capture_rgbd` / `_record_capture`）或局部循环中手动插入的快照，避免零时间间隔重复帧或变帧率采样破坏时间轴（调试 RGB-D 图像仍独立保留给感知模块）。
   - `ContactUTurn.video_frame()`（[`src/cube_relay/embodied/physical_u.py`](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/embodied/physical_u.py#L113-L122)）仅在 `legacy` 模式下渲染，在 `sim_time` 模式下统一通过 `step_physics()` 触发的 `capture_due()` 按 `video_camera="turn_overview"` 采样。
3. **`resample_indices(timestamps, fps)` 与 `.timing.json` 对账单**：
   - [`resample_indices`](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/embodied/replay_timing.py#L121-L133) 根据单调递增时间戳为均匀的 `i / fps` 目标时间点选取最近的真实物理帧索引（最近邻实采，误差上限为 1 个物理步长 `0.002 s`，绝不合成插值帧）。
   - `write_video()` 同步导出 `episode.timing.json`，记录 `mode`、`fps`、`source_sim_times`、`video_frames` 逐帧映射（`frame`、`video_seconds`、`source_index`、`sim_time`）、`motion_segments`、`physics_steps` 与 `physics_digest`。

---

## 2. `_move_gantry_xy_damped` 与控制器详细核查

源码位于 [`_move_gantry_xy_damped`](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/embodied/mujoco_v2.py#L1538-L1602) 及模型定义 [`simulation/cube_relay_v2.xml`](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/simulation/cube_relay_v2.xml#L38-L89)：

1. **物理动力学与 PD 增益**：
   - 模型位置执行器 `robot_x_ctrl`、`robot_y_ctrl` 均设定 `kp = 500.0`，关节被动阻尼 `dof_damping = 2.0 N·s/m`，有效等价质量通过 `mj_fullM` 实测为 `m_eff_x = 2.2304 kg`、`m_eff_y = 2.1804 kg`。
   - 被动开环阻尼比极低（`ζ_undamped,x = 0.0299`，`ζ_undamped,y = 0.0303`），若直接给阶跃位置指令会产生大幅超调和持续振荡（即片段 `[14]` 中的情况）。
   - `_move_gantry_xy_damped` 仅读取机器人自身编码器位置 `(px, py)` 与速度 `(vx, vy)`，在控制率中施加 `ctrl_x = clip(goal_x - kd * vx, x_low, x_high)`（`kd = 0.12 s`）。由于执行器输出力 `kp * (ctrl - p) = kp * (goal - p) - (kp * kd) * v`，等效总阻尼为 `c_eff = 2.0 + 500 * 0.12 = 62.00 N·s/m`，对应临界阻尼比为 **`ζ_x = 0.928`、`ζ_y = 0.939`**（接近临界阻尼，无超调且快速收敛）。
2. **速度限幅与收敛判据**：
   - **轨迹速度限幅**：目标位置上**无显式斜坡/速度上限（`trajectory_velocity_limit = None`）**，仅受 `jnt_range` 位置限幅（`robot_x_joint ∈ [-0.68, 0.68] m`、`robot_y_joint ∈ [-0.55, 0.55] m`）；实际速度由位置误差与 `kd = 0.12` 的阻尼项自然限制（`1.11 m` 大行程峰值附近平均速度达 `~1.44 m/s`）。
   - **收敛条件**：每 `step_seconds = 0.02 s` 检查 `|goal_x - px| <= 0.003 m`、`|goal_y - py| <= 0.003 m`、`abs(vx) <= 0.015 m/s`、`abs(vy) <= 0.015 m/s`，要求连续满足 **`settled >= 2`** 次（`max_seconds = 1.6 s` 上限）。配对运行中 **6 次调用全部 `converged_before_tail = True`**，迭代仅 **`26–35` 步**（即 **`0.520–0.700 s`**）。
3. **尾部等待逻辑与 `legacy` 慢放根因**：
   - 主循环收敛退出后固定追加 **`0.08 s`** 的纯位置目标保持（`self._set_controls({"robot_x_ctrl": goal_x, "robot_y_ctrl": goal_y}, .08)`）。此时撤除了 `-kd * v` 速度阻尼项，残余约 `0.3 mm` 偏差激发约 `0.015–0.018 m/s` 极微幅摆动（完全不影响 `<= 0.45 mm` 的对中精度）。
   - **回放放慢 `41.7x` 的精确机理**：在主循环每 `0.02 s` 调用 `_set_controls(..., 0.02)` 时，`_set_controls` 内 `steps = int(0.02 / 0.002) = 10`、`sample_every = max(1, 10 // 6) = 1`，每个 `2 ms` 物理步录制 1 帧（即 **`500 fps`**），然后以 `12 fps` 播放，时间膨胀比为 **`500 / 12 = 41.67x`**。叠加 `0.08 s` tail（`sample_every = 40 // 6 = 6` -> 录制 `7` 帧）及顶部/侧面相机快照（`1` 或 `4` 帧，零仿真时长增加），单次 `_move_gantry_xy_damped` 总计产生了 `268–357` 帧（`22.33–29.75 s`），综合膨胀比 **`37.22x–38.14x`**。

---

## 3. 全流程逐动作仿真时长、距离、平均速度、等待时间与视频对比

> 下表统计来自配对输出 [`results/replay_timing_before/episode.timing.json`](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/results/replay_timing_before/episode.timing.json) 与 [`results/replay_timing_after/episode.timing.json`](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/results/replay_timing_after/episode.timing.json)。其中“静止等待 `stat`”定义为仿真单步 TCP 速率 `< 0.001 m/s` 的累计仿真秒数；“指令保持 `hold`”定义为显式空指令稳态保持（`targets == {}`）的仿真秒数；视频帧数按所在时间区间内的 `sim_time` 归属统计（片段 `0` 在端点处因首帧采样包含 `0.402 s` 与 `0.650 s` 两个节拍点，故显示 `4` 帧 / `1.33x`，相邻片段 `1` 对应 `8` 帧 / `0.96x`，区间和严谨守恒）。

### 3.1 全部 30 个顶层动作阶段全表

| `id` | 动作阶段 (`name`) | 仿真区间 (`sim_time`) | 仿真时长 (`s`) | 末端XY净位移 (`m`) | XY轨迹路程 (`m`) | 3D TCP路程 (`m`) | 平均速度 (`m/s`) | TCP静止等待 (`s`) | 指令保持 (`s`) | Legacy视频帧 (`s` / 倍速) | Sim-Time视频帧 (`s` / 倍速) | 说明 |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `0` | `_set_controls` | `0.400–0.650` | 0.250 | 0.022 | 0.036 | 0.042 | 0.167 | 0.120 | 0.000 | 7 (0.58s / 2.33x) | 4 (0.33s / 1.33x) | 预抓指垫归零打开 |
| `1` | `_set_controls` | `0.650–1.348` | 0.698 | 0.005 | 0.015 | 0.017 | 0.025 | 0.598 | 0.000 | 7 (0.58s / 0.84x) | 8 (0.67s / 0.96x) | 预抓腕偏航/俯仰对齐 |
| `2` | `_guarded_stage_motion` | `1.348–2.148` | 0.800 | 0.252 | 0.280 | 0.439 | 0.549 | 0.240 | 0.000 | 13 (1.08s / 1.35x) | 9 (0.75s / 0.94x) | 受保护趋近 XY+(-Z=-0.22) |
| `3` | `_guarded_stage_motion` | `2.148–2.648` | 0.500 | 0.030 | 0.134 | 0.319 | 0.639 | 0.000 | 0.000 | 13 (1.08s / 2.17x) | 6 (0.50s / 1.00x) | 受保护下降至抓取高度 -0.29 |
| `4` | `skill_establish_grasp` | `2.648–3.994` | 1.346 | 0.013 | 0.038 | 0.051 | 0.038 | 0.022 | 0.000 | 13 (1.08s / 0.80x) | 17 (1.42s / 1.05x) | 闭合建立双指接触并确认 |
| `6` | `_monitored_motion` | `3.994–4.794` | 0.800 | 0.000 | 0.003 | 0.307 | 0.383 | 0.000 | 0.000 | 13 (1.08s / 1.35x) | 9 (0.75s / 0.94x) | 试探微抬 (`z=-0.24`) |
| `7` | `_monitored_motion` | `4.794–6.192` | 1.398 | 0.000 | 0.004 | 1.078 | 0.771 | 0.000 | 0.000 | 13 (1.08s / 0.77x) | 17 (1.42s / 1.01x) | 全抬升 (`z=-0.16`) |
| `8` | `task_align_scan_axes` | `6.192–10.192` | 4.000 | 0.000 | 0.004 | 1.023 | 0.256 | 0.008 | 0.000 | **19 (1.58s / 0.40x)** | 48 (4.00s / 1.00x) | 对齐扫描轴 (`yaw 1.830→1.571`) |
| `10` | `task_place_release` | `10.192–13.824` | 3.632 | 0.911 | **3.094** | **4.234** | 1.166 | 0.804 | 0.000 | 35 (2.92s / 0.80x) | 44 (3.67s / 1.01x) | 首次放回桌面并释放退避 |
| `16` | `capture_released_views` | `13.824–16.154` | 2.330 | 0.913 | 1.927 | 2.201 | 0.945 | 0.000 | 0.000 | **853 (71.08s / 30.51x)** | **28 (2.33s / 1.00x)** | 首次释放态 5 视角主动观测 |
| `106` | `task_regrasp` | `16.154–25.908` | 9.754 | 0.016 | 0.101 | 2.881 | 0.295 | 0.206 | 0.000 | 100 (8.33s / 0.85x) | 117 (9.75s / 1.00x) | 重新抓取并抬升重对齐 |
| `117` | `task_reorient` | `25.908–29.908` | 4.000 | 0.001 | 0.032 | 0.169 | 0.042 | 0.000 | 0.000 | **22 (1.83s / 0.46x)** | 48 (4.00s / 1.00x) | Pitch=-π/2 暴露 D 面 |
| `119` | `task_reorient` | `29.908–33.908` | 4.000 | 0.001 | 0.014 | 0.028 | 0.007 | 0.082 | 0.000 | **21 (1.75s / 0.44x)** | 48 (4.00s / 1.00x) | Pitch 回正 (`+1.562 rad`) |
| `121` | `TRANSPORT` | `33.908–36.908` | 3.000 | 0.299 | 0.299 | 0.300 | 0.100 | 0.000 | 0.000 | 60 (5.00s / 1.67x) | 36 (3.00s / 1.00x) | 搬运至 U-turn 工位 |
| `122` | `DOCK_LOWER` | `36.908–37.840` | 0.932 | 0.000 | 0.007 | 0.127 | 0.136 | 0.006 | 0.000 | 19 (1.58s / 1.70x) | 11 (0.92s / 0.98x) | 接触感应下降置台 |
| `123` | `BASE_CLOSE` | `37.840–39.840` | 2.000 | 0.000 | 0.001 | 0.002 | 0.001 | **1.328** | 0.000 | 40 (3.33s / 1.67x) | 24 (2.00s / 1.00x) | 底座夹紧闭合 |
| `124` | `BASE_HOLD` | `39.840–40.040` | 0.200 | 0.000 | 0.000 | 0.000 | 0.000 | 0.200 | 0.200 | 4 (0.33s / 1.67x) | 2 (0.17s / 0.83x) | 底座夹持确认 |
| `125` | `ROBOT_RELEASE` | `40.040–41.040` | 1.000 | 0.000 | 0.001 | 0.001 | 0.001 | **0.714** | 0.000 | 20 (1.67s / 1.67x) | 12 (1.00s / 1.00x) | 机械爪释放归零 |
| `126` | `ROBOT_RETREAT_Z` | `41.040–42.040` | 1.000 | 0.000 | 0.004 | 0.283 | 0.283 | 0.140 | 0.000 | 20 (1.67s / 1.67x) | 12 (1.00s / 1.00x) | 机械爪 Z 轴退避 (`-0.02`) |
| `127` | `ROBOT_RETREAT_XY` | `42.040–44.040` | 2.000 | 1.143 | 1.173 | 1.196 | 0.598 | 0.000 | 0.000 | 40 (3.33s / 1.67x) | 24 (2.00s / 1.00x) | 机械爪 XY 退避 (`-0.45,+0.45`) |
| `128` | `HEAD_LOWER` | `44.040–46.040` | 2.000 | 0.024 | 0.428 | 0.431 | 0.216 | 0.000 | 0.000 | 40 (3.33s / 1.67x) | 24 (2.00s / 1.00x) | 顶部拧头下降就位 |
| `129` | `HEAD_CLOSE` | `46.040–48.040` | 2.000 | 0.010 | 0.166 | 0.168 | 0.084 | 0.000 | 0.000 | 40 (3.33s / 1.67x) | 24 (2.00s / 1.00x) | 拧头夹爪闭合 U 层 |
| `130` | `CONTACT_CONFIRM` | `48.040–48.240` | 0.200 | 0.001 | 0.009 | 0.009 | 0.045 | 0.000 | 0.200 | 4 (0.33s / 1.67x) | 3 (0.25s / 1.25x) | 拧前双夹持确认 |
| `131` | `CONTACT_TURN` | `48.240–52.240` | 4.000 | 0.000 | 0.084 | 0.084 | 0.021 | 0.000 | 0.000 | 80 (6.67s / 1.67x) | 48 (4.00s / 1.00x) | 外置转子摩擦拧 U (`-π/2`) |
| `132` | `TURN_HOLD` | `52.240–52.740` | 0.500 | 0.000 | 0.003 | 0.003 | 0.006 | 0.000 | 0.500 | 10 (0.83s / 1.67x) | 6 (0.50s / 1.00x) | 拧后保持确认 |
| `133` | `HEAD_OPEN` | `52.740–53.740` | 1.000 | 0.001 | 0.005 | 0.005 | 0.005 | 0.012 | 0.000 | 20 (1.67s / 1.67x) | 12 (1.00s / 1.00x) | 顶部拧头松开 |
| `134` | `HEAD_RETRACT` | `53.740–55.740` | 2.000 | 0.000 | 0.005 | 0.005 | 0.002 | 0.146 | 0.000 | 40 (3.33s / 1.67x) | 24 (2.00s / 1.00x) | 顶部拧头抬升撤离 |
| `135` | `BASE_OPEN` | `55.740–56.740` | 1.000 | 0.000 | 0.001 | 0.001 | 0.001 | 0.148 | 0.000 | 20 (1.67s / 1.67x) | 12 (1.00s / 1.00x) | 底座夹爪松开 |
| `136` | `BASE_CLEAR_FOR_VISION` | `56.740–58.740` | 2.000 | 0.000 | 0.001 | 0.001 | 0.001 | **1.892** | 0.000 | 40 (3.33s / 1.67x) | 24 (2.00s / 1.00x) | 底座导轨整体避让视觉视野 |
| `137` | `capture_released_views` | `58.740–61.170` | 2.430 | 1.110 | 1.557 | 2.251 | 0.926 | **0.452** | 0.000 | **903 (75.25s / 30.97x)** | **29 (2.42s / 0.99x)** | 拧后释放态 5 视角验证观测 |
| **合计** | **全 30 项顶层阶段** | **`0.400–61.170`** | **60.770** | — | — | — | — | **7.118** | **0.900** | **2,529 (210.75s / 3.47x)** | **730 (60.83s / 1.00x)** | 物理轨迹与接触判定 100% 相同 |

### 3.2 关键组合阶段子动作拆解（含所有 `_move_gantry_xy_damped` 调用）

| 子段 `id` (父节点) | 子动作 (`name`) | 仿真区间 (`sim_time`) | 仿真时长 (`s`) | 末端XY净位移 (`m`) | XY路程 (`m`) | 3D路程 (`m`) | 平均速度 (`m/s`) | 静止等待 (`s`) | 指令保持 (`s`) | Legacy视频 (`s` / 倍速) | Sim-Time视频 (`s` / 倍速) | 说明 / 收敛遥测 |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| ↳ `11` (p=10) | `_lower_until_table_supported` | `10.192–11.174` | 0.982 | 0.000 | 0.000 | 0.139 | 0.142 | 0.032 | 0.000 | 7 (0.58s / 0.59x) | 12 (1.00s / 1.02x) | 触台稳定提前触发 |
| ↳ `12` (p=10) | `_set_controls` | `11.174–11.974` | 0.800 | 0.000 | 0.000 | 0.000 | 0.000 | **0.770** | 0.000 | 7 (0.58s / 0.73x) | 9 (0.75s / 0.94x) | 张开手指释放（几乎全程静止） |
| ↳ `13` (p=10) | `_set_controls` | `11.974–12.774` | 0.800 | 0.000 | 0.000 | 0.816 | 1.020 | 0.002 | 0.000 | 7 (0.58s / 0.73x) | 10 (0.83s / 1.04x) | Z 抬升至 `robot_z_ctrl=-0.02` |
| ↳ `14` (p=10) | `_set_controls` | `12.774–13.574` | 0.800 | 0.661 | **2.654** | **2.811** | 3.514 | 0.000 | 0.000 | 7 (0.58s / 0.73x) | 10 (0.83s / 1.04x) | 无阻尼 XY 阶跃退避引发强烈振铃 |
| ↳ `15` (p=10) | `_set_controls` | `13.574–13.824` | 0.250 | 0.276 | 0.439 | 0.467 | 1.869 | 0.000 | 0.250 | 7 (0.58s / 2.33x) | 3 (0.25s / 1.00x) | 退避后空等（承接 `[14]` 余振） |
| ↳ `17` (p=16) | `_set_controls` | `13.824–14.274` | 0.450 | 0.055 | 0.631 | 0.666 | 1.481 | 0.000 | 0.000 | 7 (0.58s / 1.30x) | 5 (0.42s / 0.93x) | 打开/保持期间仍在消化 `[14]` 余振 |
| ↳ `18` (p=16) | `_move_gantry_xy_damped` | `14.274–14.954` | **0.680** | 0.869 | 0.875 | 0.973 | **1.431** | 0.000 | 0.000 | **307 (25.58s / 37.62x)** | **8 (0.67s / 0.98x)** | **30 步收敛**，`err=[+0.45,-0.30]mm` |
| ↳ `50` (p=16) | `_move_gantry_xy_damped` | `14.954–15.554` | **0.600** | 0.200 | 0.200 | 0.284 | 0.474 | 0.000 | 0.000 | **268 (22.33s / 37.22x)** | **7 (0.58s / 0.97x)** | **26 步收敛**，`err=[0.00,-0.28]mm` |
| ↳ `78` (p=16) | `_move_gantry_xy_damped` | `15.554–16.154` | **0.600** | 0.221 | 0.221 | 0.277 | 0.462 | 0.000 | 0.000 | **271 (22.58s / 37.64x)** | **8 (0.67s / 1.11x)** | **26 步收敛**，`err=[0.00,+0.31]mm` |
| ↳ `107` (p=106) | `_set_controls` | `16.154–16.404` | 0.250 | 0.001 | 0.003 | 0.037 | 0.149 | 0.000 | 0.000 | 7 (0.58s / 2.33x) | 3 (0.25s / 1.00x) | 重抓预张开手指 |
| ↳ `108` (p=106) | `_set_controls` | `16.404–17.102` | 0.698 | 0.001 | 0.005 | 0.092 | 0.132 | 0.000 | 0.000 | 7 (0.58s / 0.84x) | 8 (0.67s / 0.96x) | 重抓腕角预设 (`yaw=1.571`) |
| ↳ `109` (p=106) | `_guarded_stage_motion` | `17.102–17.902` | 0.800 | 0.016 | 0.017 | 0.229 | 0.287 | 0.000 | 0.000 | 13 (1.08s / 1.35x) | 10 (0.83s / 1.04x) | 受保护趋近 XY+(-Z=-0.22) |
| ↳ `110` (p=106) | `_guarded_stage_motion` | `17.902–18.402` | 0.500 | 0.001 | 0.003 | 0.100 | 0.200 | 0.000 | 0.000 | 13 (1.08s / 2.17x) | 6 (0.50s / 1.00x) | 受保护下降 (`-0.29`) |
| ↳ `111` (p=106) | `skill_establish_grasp` | `18.402–19.710` | 1.308 | 0.003 | 0.012 | 0.022 | 0.017 | 0.204 | 0.000 | 13 (1.08s / 0.83x) | 15 (1.25s / 0.96x) | 闭合确认（含子段 `112` `0.15 s` hold） |
| ↳ `113` (p=106) | `_monitored_motion` | `19.710–20.510` | 0.800 | 0.002 | 0.019 | 0.304 | 0.380 | 0.000 | 0.000 | 13 (1.08s / 1.35x) | 10 (0.83s / 1.04x) | 试探微抬 (`-0.24`) |
| ↳ `114` (p=106) | `_monitored_motion` | `20.510–21.908` | 1.398 | 0.000 | 0.021 | 1.076 | 0.770 | 0.000 | 0.000 | 13 (1.08s / 0.77x) | 17 (1.42s / 1.01x) | 全抬升 (`-0.16`) |
| ↳ `115` (p=106) | `task_align_scan_axes` | `21.908–25.908` | **4.000** | 0.001 | 0.022 | 1.020 | 0.255 | 0.002 | 0.000 | **21 (1.75s / 0.44x)** | 48 (4.00s / 1.00x) | **Δyaw=0.0000 仍跑满 4.0 s**（含 Z 轴余振） |
| ↳ `138` (p=137) | `_set_controls` | `58.740–59.190` | 0.450 | 0.000 | 0.000 | 0.000 | 0.000 | **0.450** | 0.000 | 7 (0.58s / 1.30x) | 5 (0.42s / 0.93x) | 夹爪本已打开静止，纯空等 0.450 s |
| ↳ `139` (p=137) | `_move_gantry_xy_damped` | `59.190–59.970` | **0.780** | 1.114 | 1.126 | 1.476 | **1.892** | 0.002 | 0.000 | **357 (29.75s / 38.14x)** | **9 (0.75s / 0.96x)** | **35 步收敛**，`err=[+0.13,-0.26]mm` |
| ↳ `176` (p=137) | `_move_gantry_xy_damped` | `59.970–60.570` | **0.600** | 0.211 | 0.211 | 0.413 | 0.688 | 0.000 | 0.000 | **268 (22.33s / 37.22x)** | **8 (0.67s / 1.11x)** | **26 步收敛**，`err=[+0.01,-0.30]mm` |
| ↳ `204` (p=137) | `_move_gantry_xy_damped` | `60.570–61.170` | **0.600** | 0.221 | 0.221 | 0.362 | 0.604 | 0.000 | 0.000 | **271 (22.58s / 37.64x)** | **7 (0.58s / 0.97x)** | **26 步收敛**，`err=[0.00,+0.31]mm` |

---

## 4. 严格区分：视频编码回放倍速失真 vs 真实仿真运动/等待行为

### A. 纯视频编码与帧采集逻辑导致的播放失真（非控制/仿真过慢）

1. **`_move_gantry_xy_damped` 约 `41.7x` 回放放慢（`37.22x–38.14x` 全段含尾随帧）**：
   - `legacy` 模式全片 `2,529` 帧中，有 **`1,701` 帧间隔恰好为 `dt = 0.002 s`**（中位帧间隔仅 `0.0020 s`），几乎全部来自两次 `capture_released_views` 中的 `6` 次 `_move_gantry_xy_damped` 调用。
   - 这 6 次移动实际共只耗时 `0.680 + 0.600 + 0.600 + 0.780 + 0.600 + 0.600 = 3.860 s`（含入场与顶/侧视对中），而在旧视频中占用了 **`1,742` 帧 = `145.17 s`**（加 2 段开头各 `7` 帧合计 **`146.33 s`**，占 `210.75 s` 视频总长的 **`69.4%`**）。
2. **`ContactUTurn.move` / `lower_to_support` 约 `1.67x` 慢放**：
   - 片段 `121–136`（仿真总长 `24.832 s`）在 `legacy` 模式下每 `25` 步（`0.05 s = 20 fps`）插 1 帧，以 `12 fps` 播放时统一放慢 **`20 / 12 = 1.667x`**（`41.42 s`）；`sim_time` 模式下恢复为 exact **`1.00x`**。
3. **`_monitored_rotation`（`4.000 s`）约 `2.2x–2.5x` 过快压缩**：
   - 片段 `8`（`task_align_scan_axes`）、`117`/`119`（`task_reorient`）实际耗时各 `4.000 s`，但 `legacy` 模式按 `steps // 18` 仅录 `19` 帧（`1.58 s`，`0.40x` 倍速，即快放 `2.53x`）；片段 `117`/`119` 还在末尾因 `capture_held_views()` 混入了 `2` 与 `1` 个 **`dt = 0.000 s`** 的零间隔重复时间戳快照。
4. **`skill_establish_grasp` 闭合与全局帧间隔抖动**：
   - 在闭合采样（`sample_every = close_steps // 6`）及长时动作交界处，`legacy` 最大帧间跳变达到 **`1.216 s`**（等效 `14.6x` 快进），全片共有 **`10` 帧 `dt = 0.000 s`** 重复时间戳快照。`sim_time` 模式将全片 `dt` 收敛到 **`[0.082 s, 0.084 s]`**，彻底消除时间畸变。

### B. 真实存在的仿真静止等待与无阻尼振荡问题（配对轨迹下保持未改、供后续控制优化参考）

1. **固定 `4.000 s` 耗时与冗余 `task_align_scan_axes`**：
   - `_monitored_rotation` 无论目标角差多少，均固定执行 `seconds = 4.0 s`（片段 `8` 仅转 `-0.259 rad`，片段 `115` 在 `task_regrasp` 后因 `wrist_yaw_joint` 已在 `1.5708 rad` 而 **`Δyaw = 0.0000 rad` 仍运行满 `4.000 s`**）。
2. **机械臂/工装 Z 轴被动无阻尼及阶跃指令余振**：
   - `robot_z_ctrl` (`kp=500, damping=2.0`) 仅在 `_guarded_stage_motion` 与 `_monitored_motion` 中做 `1.4 s` / `0.8 s` 光滑插值，但到达目标时存在惯性余振（如片段 `7` 结束 `vz = +0.801 m/s`，余振延续至片段 `8` 造成 `1.023 m` 的 Z 向累计路径）。
   - `[14]` 首次 `task_place_release` 中的 XY 退避使用无阻尼 `_set_controls({"robot_x_ctrl": -0.45, "robot_y_ctrl": 0.45}, .8)`，在 `0.661 m` 净位移上造成 **`2.654 m` XY 剧烈振荡路程**，余振跨过 `[15]`（`0.439 m`）一直持续到 `[17]`（`0.631 m`）。若后续将该退避改为复用 `_move_gantry_xy_damped(-0.45, 0.45)`，可直接消除振荡并使 `[17]` 立即进入稳态。
3. **固定长时等待区间（纯静止等待累计达 `7.118 s`）**：
   - 顶层 `7.118 s` TCP 静止时间主要由以下几处固定时长构成：`[136] BASE_CLEAR_FOR_VISION`（`2.000 s` 中 `1.892 s` 静止）、`[123] BASE_CLOSE`（`2.000 s` 中 `1.328 s` 静止）、`[125] ROBOT_RELEASE`（`1.000 s` 中 `0.714 s` 静止）、`[12]` 放回桌面后开指 `_set_controls(..., 0.8)`（`0.800 s` 中 `0.770 s` 静止）、`[1]` 初始对齐腕角 `_set_controls(..., 0.7)`（`0.698 s` 中 `0.598 s` 静止）、`[138]` 第二次观测前开指保持 `_set_controls(..., 0.45)`（**`0.450 s` 全程完全静止**），以及显式保持 `[124]`/`[130]`/`[132]`（共 `0.900 s`）。

---

## 5. 改动文件与验证结果

### 修改与新增文件清单
- [`src/cube_relay/embodied/replay_timing.py`](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/embodied/replay_timing.py)：新增 `MotionTiming`、`TimedFrames`、`resample_indices`。
- [`src/cube_relay/embodied/mujoco_v2.py`](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/embodied/mujoco_v2.py)：默认启用 `video_timing="sim_time"`，统一 `step_physics()` 节拍，记录 `_move_gantry_xy_damped` 控制器遥测，并在 `write_video()` 输出 `<video>.timing.json`。
- [`src/cube_relay/embodied/physical_u.py`](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/embodied/physical_u.py)：将 `ContactUTurn.move` 与 `lower_to_support` 纳入 `motion_timing.segment`，在 `sim_time` 模式下由 `step_physics()` 统一按仿真时钟渲染。
- [`scripts/physical_u_step.py`](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/scripts/physical_u_step.py)：增加 `--video-timing {legacy,sim_time}` 参数（默认 `sim_time`），生成配对对比产物。
- [`tests/test_replay_timing.py`](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/tests/test_replay_timing.py)：新增 4 项回归测试（重采样时钟一致性、感知快照过滤、非单调时间戳拒绝、`legacy` vs `sim_time` 物理步数与 `physics_digest` 全等性及视频时间对齐校验）。
- 配对输出产物：
  - 修改前：[`results/replay_timing_before/episode.mp4`](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/results/replay_timing_before/episode.mp4)、[`results/replay_timing_before/episode.timing.json`](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/results/replay_timing_before/episode.timing.json)
  - 修改后：[`results/replay_timing_after/episode.mp4`](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/results/replay_timing_after/episode.mp4)、[`results/replay_timing_after/episode.timing.json`](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/results/replay_timing_after/episode.timing.json)

### 回归测试命令与实测输出

```bash
# 1. 回放时间对齐专题回归测试
/private/tmp/cuberelay-py313/bin/python -m pytest tests/test_replay_timing.py -q
# 实测输出: 4 passed in 1.20s

# 2. 全量测试套件（含所有单测与 MuJoCo 物理集成测试）
/private/tmp/cuberelay-py313/bin/python -m pytest -q
# 实测输出: 173 passed in 28.83s
```
