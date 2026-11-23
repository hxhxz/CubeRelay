# CubeRelay M4-C 抓取视觉因果链审计、Trace 导出与位置扰动实验报告

> **核心结论（基于真实 MuJoCo 物理仿真与实测实验包）**：CubeRelay 机器人的抓取目标并非固定坐标或 MuJoCo 真值驱动，而是严格由最新标定 RGB-D 传感器帧经 `DeterministicCubeLocalizer` 计算 `PoseEstimateRecord` 后生成 `GraspTargetRecord`，再驱动关节/笛卡尔轨迹与 `ContactRecorder` 多时间窗接触验证。+5 cm 与 +10 cm 位置扰动实验中，RGB-D 估计 ΔX（`+0.050062 m`、`+0.099722 m`）与 Grasp Target ΔX（`+0.050106 m`、`+0.099795 m`）高精度响应真实位移；视觉中断负对照下系统准确拒绝定位并中止任务（0 个抓取目标、0 次真值泄漏）。

---

## 一、代码与 `inspect_snapshot.json` 审计结论（五大已知异常根因与修复）

| 已知异常 | 代码级实证根因 | M4-C 修复方式 |
| --- | --- | --- |
| 1. `regrasp_cube` 标记 `VERIFIED` 但 `bilateral_contact_fraction=0` | `MuJoCoEmbodiedBackend.task_regrasp()` 调用 `FailureAwareSkillAgent` + `task_align_scan_axes()`，此前两者均未更新 `self.last_grasp_telemetry`；随后 `task_regrasp()` 读取仍是 `__init__` 默认值 `GraspTelemetry(False, 0, 0, 0, 0, "not attempted")` 导致统计为空样本默认 0，而上层未做接触门槛阻断即放行。 | `skill_approach_grasp()` / `skill_establish_grasp()` / `skill_test_lift()` / `task_align_scan_axes()` 均实时写入 `self.last_grasp_telemetry` 与 `ContactRecorder` 连续样本；`task_regrasp()` 与 `SimulationSession` 强制校验证书条件（`bilateral_contact_fraction >= 0.80`、法向力 ≥ `minimum_normal_force_n`、滑移 ≤ `slip_limit_m`、抬升 ≥ `0.06 m`、0 意外接触），新增 `bilateral=0` 回归失败测试 `test_10`。 |
| 2. 后续 `reorient_cube` 中双侧接触率 `1.0`、最大滑移 `~0.00726 m` | `task_reorient()` 直接返回 `_monitored_rotation()` 的全时域接触统计，而非默认 telemetry。M4-C 实测 Baseline 中 `reorient_cube` 仍观测到 `bilateral_contact_fraction = 1.0`、`relative_slip_m = 0.007277 m`。 | 在 `task_reorient()` 中同步接入 `ContactRecorder.finalize_verification()`，与 `initial_grasp`、`regrasp_cube` 统一采用 `min_bilateral >= 0.80`、`max_slip <= 0.03 m` 口径并分 5 个时间窗口报告。 |
| 3. `inspect_snapshot.json` 缺乏原始 RGB-D、Pose→Grasp→Trajectory→Contact 因果引用 | 旧快照只保留压缩 JPEG、最终 state 与部分 skill 输出，缺失 `.npy` 无损米制深度、相机内外参、`PoseEstimateRecord`、`GraspTargetRecord`、连续控制轨迹及分阶段接触时序。 | 构建独立非侵入式 `src/cube_relay/experiment/` 模块与 `ExperimentRun` 异步缓冲落盘机制，保存原始 `.png` + float32 `.npy` 深度、`camera_calibration.json`、`pose_estimates.jsonl`、`grasp_targets.jsonl`、`robot_states.csv`、`trajectory_commands.csv`、`contact_samples.csv`、`contact_verifications.jsonl` 及可选 `audit_only_poses.csv`。 |
| 4. 历史 `timeline` 事件全部引用最后一个 stage | `SimulationSession._build_snapshot()` 每次动态遍历 `event_log.events`，用当前 `current_step.step_id`、`telemetry` 和当前 `completed_stage_index` 覆写全部历史条目。 | 改为在 `_record_decision()` 事件发生瞬间通过 `_record_timeline_from_decision()` 固化不可变 `stage_id`、`sim_time`、遥测和已完成阶段数，不再后写或覆写历史阶段。 |
| 5. `feedback_observation_id` 引用旧观测、且 `observations` 遗漏 `observe_workspace` 及 `frame_id` | `_run_mission_sync()` 在 `_execute_plan_step()` 后无条件执行 `selected_ev.feedback_observation_id = self.last_observation_ref.observation_id`，导致纯动作技能挂接上一轮旧观测；`_build_snapshot()` 亦从 `trace_log` 与 `_agent_observation_history` 拼接且缺失 `observe_workspace`。 | 仅当当步 Skill 实际产生新观测时绑定 `step_produced_obs_id`，纯动作技能置为 `None`；新增 `_register_observation()` 按发生时序记录并携带 `frame_id` 与 `observe_workspace` 定位条目。 |

---

## 二、M4-C 核心工程实现清单

- **实验记录与因果关联协议**（`src/cube_relay/experiment/`）：
  - [schema.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/experiment/schema.py)：统一 `run_id` / `session_id` / `mission_id` / `skill_execution_id` / `observation_id` / `frame_id` / `pose_estimate_id` / `grasp_target_id` / `trajectory_id` / `contact_verification_id` 引用模型与 `DataSourceKind` / `QualityStatus` 枚举。
  - [boundary.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/experiment/boundary.py)：`TruthAccessCategory` 四分类隔离与运行时守卫 `TruthAccessBoundary`（若感知/规划作用域内企图读取仿真真值立即抛出 `TruthAccessViolation`）。
  - [recorder.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/experiment/recorder.py)：`_AsyncDiskWriter` 后台守护线程队列落盘（含 `max_disk_mb` 限额、`flush()`/`close()`/`atexit` 恢复与密钥脱敏 `redact_secrets`），以及 `EventStore`、`PoseEstimateRecorder`、`GraspTargetRecorder`、`TrajectoryRecorder`（50 Hz 可配采样与独立 `audit_only_poses.csv`）、`ContactRecorder`（5 个时间窗口：`Approach`、`Initial Contact`、`Grasp Closure`、`Lift / Hold`、`Reorientation`）。
  - [exporter.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/experiment/exporter.py)：`ArtifactExporter` 支持 `full_mission` / `grasp_causal_chain` / `events_only`，校验 `manifest.json` 字节数与 SHA-256、外键引用完整性 `verify_reference_integrity`、敏感信息脱敏、目录穿越防护及严格拒绝 `SYNTHETIC_SAMPLE`（`SAMPLE_MODE_FORBIDDEN`）。
- **具身感知、物理后端与编排接入**：
  - [v2_types.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/embodied/v2_types.py)、[perception_v2.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/embodied/perception_v2.py)：`RGBDFrame.frame_id`；`DeterministicCubeLocalizer.locate_with_diagnostics()` 记录边界框、像素中心、米制深度统计、像素→相机→世界坐标转换及置信度。
  - [mujoco_v2.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/embodied/mujoco_v2.py)：新增受控扰动初始化入口 `reset_with_perturbation()`、`vision_fault_mode` 故障注入、全状态清理的 `reset_random()`、`truth_boundary` 运行时隔离、50 Hz 物理轨迹与 5 窗口接触验证。
  - [skill_agent.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/embodied/skill_agent.py)、[failure_aware_v6.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/embodied/failure_aware_v6.py)、[session.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/mission/session.py)：完整打通 `PoseEstimate -> GraspTarget -> Trajectory -> ContactVerification` 并区分保存 Pose Estimate、Grasp Target（同时输出世界系 `x_m, y_m, z_m` 与控制量 `robot_x_ctrl, robot_y_ctrl`）及 Actual End-Effector Pose。
- **后端导出 API 与前端 Export UI**：
  - [main.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/api/main.py)：新增 `GET /api/m3d/runs`、`GET /api/m3d/export/manifest`、`GET/POST /api/m3d/export`（含路径穿越 HTTP 400、范围校验 HTTP 422、`SYNTHETIC_SAMPLE` 拒绝 HTTP 403）。
  - [cuberelay_v4.tsx](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/web/console/cuberelay_v4.tsx) & [cuberelay_v4.css](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/web/console/cuberelay_v4.css)：新增 `Experiment / Trace Export` 弹窗（当前 `run_id`、采集状态及计数、历史运行列表、导出范围、RGB-D/高频轨迹/审计真值开关、真实后端 ZIP 下载与错误信息、Strict SAMPLE 隔离），已通过 TypeScript 类型检查与离线打包。
- **可重复扰动 Runner 与自动化因果分析**：
  - [perturbation.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/experiment/perturbation.py) & [scripts/run_m4c_experiments.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/scripts/run_m4c_experiments.py)
  - [analyzer.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/experiment/analyzer.py) & [scripts/analyze_m4c_experiments.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/scripts/analyze_m4c_experiments.py)

---

## 三、四组真实 MuJoCo 位置扰动实验与因果分析结果

### 1. 执行命令与数据位置

```bash
/private/tmp/cuberelay-py313/bin/python scripts/run_m4c_experiments.py --seed 0 --output-dir results/m4c_experiments --sample-hz 50
/private/tmp/cuberelay-py313/bin/python scripts/analyze_m4c_experiments.py --index results/m4c_experiments/experiment_index.json --output-dir results/m4c_experiments/analysis
```

- 实验索引：[results/m4c_experiments/experiment_index.json](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/results/m4c_experiments/experiment_index.json)
- 自动化分析报告：[results/m4c_experiments/analysis/causal_analysis_report.md](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/results/m4c_experiments/analysis/causal_analysis_report.md)
- 全量指标 JSON：[results/m4c_experiments/analysis/causal_analysis_metrics.json](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/results/m4c_experiments/analysis/causal_analysis_metrics.json)
- 导出 ZIP 实验包目录：[results/m4c_experiments/bundles](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/results/m4c_experiments/bundles)

### 2. X 轴扰动因果传导对照表

| Condition | `run_id` | Mission 状态 | $\Delta X_{\text{GT}}$ (m) | $\Delta X_{\text{RGB-D Est}}$ (m) | $\Delta X_{\text{Grasp Target}}$ (m) | $\Delta X_{\text{Actual EE}}$ (m) | 引用完整性 | 真值合规 |
| --- | --- | --- | ---: | ---: | ---: | ---: | :---: | :---: |
| `baseline` | `run-1794839956-9a46cdef` | `COMPLETED` | `0.000000` | `0.000000` | `0.000000` | `0.000000` | `True` | `True` |
| `translate_x_005` | `run-1794839960-ea07e812` | `FAILED` (`geometric_misalignment` @ `regrasp_cube`) | `+0.050000` | `+0.050062` | `+0.050106` | `+0.042032` | `True` | `True` |
| `translate_x_010` | `run-1794839963-357553ec` | `FAILED` (`initial_grasp`) | `+0.100000` | `+0.099722` | `+0.099795` | `+0.129527` | `True` | `True` |
| `vision_missing_negative_control` | `run-1794839964-761bfc7c` | `FAILED` (`INSUFFICIENT_MASK_PIXELS`) | `+0.050000` | `None` | `None` | `None` | `True` | `True` |

### 3. 全量 12 项实测指标摘要

| Condition | RGB-D 3D 定位误差 (m) | 首抓 Target vs Actual XY 误差 (m) | 轨迹样本数 | 首抓双侧接触率 / 结果 | 总最大滑移 (m) | 平均双侧接触率 | Pose 新鲜度 (`pose_age_sim_s`) | `sim_time` / Wall (s) |
| --- | ---: | ---: | ---: | :---: | ---: | ---: | ---: | ---: |
| `baseline` | `0.012796` | `0.000456` | `1478` | `1.000` / `True` | `0.007277` | `1.0000` | `0.0` | `30.328` / `3.3675` |
| `translate_x_005` | `0.012660` | `0.017219` | `2042` | `1.000` / `True` | `0.004707` | `0.5275` | `0.0` | `41.614` / `2.9986` |
| `translate_x_010` | `0.013959` | `0.056827` | `598` | `0.000` / `False` | `0.000000` | `0.0000` | `0.0` | `12.744` / `0.8332` |
| `vision_missing_negative_control` | `None` | `None` | `0` | — | `None` | `None` | `None` | `0.800` / `0.1070` |

> **扰动条件物理分析**：
> - **`translate_x_005`（+5 cm）**：首次抓取（`cv-0001-d4d16e`）完全通过接触验证（`bilateral_contact_fraction = 1.0`、`relative_slip_m = 0.001477 m`、`lift_height_m = 0.146956 m`）。后续 `regrasp_cube` 时方体释放落点邻近扭面基座并发生非预期接触 `base_pos_pad`，新接触验证门控（`bilateral_contact_fraction = 0.055 < 0.80`）如实拦截并报 `FAILED (geometric_misalignment)`，绝不虚标 `VERIFIED`。
> - **`translate_x_010`（+10 cm）**：工作空间可达性审计为 `REACHABLE / CLEAR`，RGB-D 定位（`+0.099722 m`）与 Grasp Target（`+0.099795 m`）准确平移 +10 cm；但因机械臂每次从 `(0.0, 0.065)` 起步在固定 `0.8 s` 步进窗口内高速横移 `dx=+0.213 m, dy=-0.187 m`，末端发生 `0.0568 m` 横向过冲并与方体边缘碰撞触发保守位移守卫，随后接触验证如实报告 `bilateral_contact_fraction = 0.0` 并中止。

### 4. 生成的 6 张可视化因果分析图表

1. 三维定位对比：[01_3d_localization_comparison.png](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/results/m4c_experiments/analysis/plots/01_3d_localization_comparison.png)
2. 抓取目标与 Delta-X 对比：[02_grasp_target_comparison.png](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/results/m4c_experiments/analysis/plots/02_grasp_target_comparison.png)
3. 末端轨迹对比：[03_end_effector_trajectory_comparison.png](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/results/m4c_experiments/analysis/plots/03_end_effector_trajectory_comparison.png)
4. 左右指法向接触力时序：[04_contact_forces_timeseries.png](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/results/m4c_experiments/analysis/plots/04_contact_forces_timeseries.png)
5. 相对滑移时序：[05_relative_slip_timeseries.png](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/results/m4c_experiments/analysis/plots/05_relative_slip_timeseries.png)
6. 因果全链路图：[06_causal_chain_diagram.png](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/results/m4c_experiments/analysis/plots/06_causal_chain_diagram.png)

---

## 四、针对第 15 节七个核心问题的逐项回答

1. **最新 RGB-D 是否真正决定魔方 Pose？**
   **是。** `observe_workspace` 与 `SkillRuntime.observe_cube` 在 `TruthAccessCategory.RUNTIME_LOCALIZATION_FORBIDDEN` 作用域内采集当帧 `overhead` RGB（`.png`）与 float32 米制深度（`.npy`，实测帧时间差 `rgb_depth_sim_time_delta_s = 0.0 s`），通过相机内参/外参矩阵计算像素表面三维坐标并投影到方体中心；+5 cm / +10 cm 扰动下估计位置立即跟踪偏移 `+0.050062 m` / `+0.099722 m`；传感器黑屏负对照明确返回 `INSUFFICIENT_MASK_PIXELS` 与 `PoseEstimate=MISSING`。
2. **估计 Pose 是否真正进入抓取目标计算？**
   **是。** `GraspTargetRecord` 显式绑定并引用最新 `pose_estimate_id`（且 `pose_age_sim_s = 0.0 s`）；`SkillRuntime.plan_grasp` 仅使用 `detection.center_world_m` 和 `yaw_radians` 生成并校验候选抓点。实验包严格区分存储了三组不同坐标：`Pose Estimate`（如 Baseline `[0.10147, -0.13576, 0.66925]`）、`Grasp Target`（含 `+10/-15 mm` 局部偏置 `[0.11339, -0.12223, 0.80000]`）和 `Actual EE Close`（实测 `[0.11376, -0.12249, 0.76002]`）。
3. **魔方平移后抓取目标与机器人轨迹是否合理变化？**
   **是。** +5 cm 时 `Grasp Target` 平移 `+0.050106 m`、末端实际轨迹响应 `+0.042032 m` 并高稳定完成首抓（双侧接触率 `1.0`、滑移 `0.001477 m`）；+10 cm 时 `Grasp Target` 平移 `+0.099795 m`、实际轨迹随之大步距响应 `+0.129527 m`；当平移过大导致高速开环进近过冲失稳或超越边界时，系统如实记录不可达/接触失败。
4. **是否存在 MuJoCo 隐藏真值泄漏？**
   **运行时感知与抓取规划路径不存在真值泄漏。** 通过 AST 源码审计确认 [perception_v2.py](file:///Users/xina/project/cloudrobo/human_robot_rubiks_cube/src/cube_relay/embodied/perception_v2.py) 零引用 `xpos/xquat/xmat/qpos/geom_xpos/cvel/_true_cube_pose`；运行时 `TruthAccessBoundary` 在 `RUNTIME_LOCALIZATION_FORBIDDEN` 内对真值读取直接抛出 `TruthAccessViolation`；负对照实验在场景真实平移 +5 cm 且屏蔽相机帧时生成 `0` 个抓取目标、清零旧缓存，彻底排除读取隐藏真值或历史缓存可能。场景初始化与离线审计真值统一标注为 `SIMULATOR_GROUND_TRUTH_AUDIT_ONLY` 并隔离于 `audit_only_poses.csv`。
5. **抓取是否由接触与稳定性证据验证？**
   **是。** `ContactRecorder` 采集 `contact_samples.csv` 时序并按 `Approach`、`Initial Contact`、`Grasp Closure`、`Lift / Hold`、`Reorientation` 5 个窗口统计双侧接触占比、持续时间、左右法向力（Baseline 首抓达 `1.902 N / 1.902 N`）、相对滑移、物体随动、夹爪开度及非预期碰撞体；只有同时满足全部物理门槛方能判定 `verification_result=True`。
6. **`regrasp bilateral_contact_fraction=0` 的真实原因是什么？**
   直接原因是此前 `FailureAwareSkillAgent` 与 `task_align_scan_axes()` 在重抓成功后没有回写 `self.last_grasp_telemetry`，`task_regrasp()` 读取到了后台初始化默认值 `GraspTelemetry(False, 0, 0, 0, 0, "not attempted")`，且流程层未把 `bilateral_contact_fraction >= 0.80` 作为 `VERIFIED` 硬门控（只依赖后续步骤返回 True 就放行）。M4-C 已修复统计闭环与强门控：现在真实成功的 Baseline `regrasp_cube` 录得 `bilateral_contact_fraction = 1.0`、`slip = 0.0007 m`，而在 `translate_x_005` 重抓发生 `base_pos_pad` 碰撞导致实际接触率降为 `0.055` 时被精确拦截。
7. **当前机器人抓取链路是否具备可验证的视觉闭环特性？**
   **具备。** 从原生 `.png + float32 .npy` RGB-D 帧 → `PoseEstimateRecord` → `GraspTargetRecord` → `robot_states.csv / trajectory_commands.csv` → `ContactVerificationRecord` 全链路外键 100% 可解析（`reference_integrity_ok = True`），配合位置扰动对照与视觉失效负对照测试证明当前系统具备可独立审计、抗真值泄漏、接触证据闭环的视觉抓取能力。

---

## 五、全量验证与测试汇总

| 验证项目 | 执行命令 | 实测结果 |
| --- | --- | --- |
| 前端 TypeScript 类型检查与离线打包 | `/private/tmp/cuberelay-py313/bin/python scripts/build_frontend.py --typecheck` | `ok: true, typechecked: true, bundle_bytes: 456074, css_bytes: 12616` |
| 真实 MuJoCo GL 因果闭环 + M3-D + M4-A + M4-B + API/Skill 回归 | `/private/tmp/cuberelay-py313/bin/pytest -q tests/test_m4c_causal_audit.py tests/test_m3d_orchestration.py tests/test_m4a_vlm_loop.py tests/test_m4b_dual_model.py tests/test_api.py tests/test_skill_agent.py tests/test_failure_aware_v6.py tests/test_mujoco_integration.py` | **53 passed in 38.11s**（无失败、无跳过） |
| 真实 MuJoCo GL 录屏时序回归 | `/private/tmp/cuberelay-py313/bin/pytest -q tests/test_replay_timing.py` | **4 passed in 1.62s** |
| 核心状态/规划/求解/安全非 GL 单测 | `/private/tmp/cuberelay-py313/bin/pytest -q tests/test_camera_state.py tests/test_coordinator.py tests/test_embodied_v2.py tests/test_moves.py tests/test_policy_modes.py tests/test_robot_safety.py tests/test_solver.py tests/test_validation_randomized.py` | **85 passed in 14.39s** |
