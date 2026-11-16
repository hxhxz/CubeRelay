# CubeRelay M3-D Active Scan 分层 Trace 补强报告

## 结论

本轮只增强可观测性和事件接口，没有修改 `ContinuousActiveInspector` 的扫描顺序、机器人运动参数、接触控制或感知融合规则。Seed 0 仍通过原有六面扫描基线，M3-B 物理 U 层转动验收也保持通过。

## 现有 Skill 粒度分析

Mission Planner 将六面扫描视为一个 `active_six_face_scan` Composite Skill，这一粒度适合任务规划，但不适合作为执行审计的最小单位。Composite 内实际包含抓取、对齐、释放、多相机观测、重抓、姿态选择、旋转、再次观测和终止校验。

旧实现的 `InspectionEvent` 已在动作结束时记录部分结果，但 `SimulationSession` 只保留 `action_count`，没有把 `scan.events` 或运行中事件暴露给 UI，因此用户只能看到 Composite 的开始与结束。

## 新事件协议

新增六种层级事件：`mission`、`composite_skill`、`action`、`perception`、`decision`、`verification`。事件以 `parent_event_id` 形成树，以 `sequence` 重建顺序，并保存开始/结束仿真时间、时长、状态、证据和失败原因。

Inspector 在真实动作或观测完成时通过事件回调即时上报。Session 收到事件后使用缓存画面生成轻量快照，不触发新的 MuJoCo 渲染。完整历史保存在 `trace_events`，LIVE 与 REPLAY 消费同一事实记录。

## Seed 0 真实扫描

最终 Trace 位于 `results/seed0_active_scan_hierarchical_trace.json`。

执行链为：

1. `initial_grasp`
2. `align_scan_axes`
3. `place_release_refresh`
4. `observe_released`：5 台相机新增 45 个唯一 canonical facelet，unknown 54 → 9
5. `regrasp_required`：确定性策略说明需要改变物体姿态
6. `refresh_plan_regrasp`
7. `observe_held_after_regrasp`：2 台相机，新增 0，unknown 9 → 9
8. `object_reorientation_selected`：确定性策略选择 pitch
9. `reorient_pitch_refresh`：目标 -89.999°，实测 -89.505°
10. `observe_held`：3 台相机新增 9 个唯一 canonical facelet，unknown 9 → 0
11. `scan_termination_check`
12. `six_face_scan_verification`

三次 Perception 分别关联 5、2、3 张真实观测图。相机贡献按新增 canonical facelet 去重，原始检测次数不会被误计为机器人姿态调整次数。

## 失败诊断案例

测试构造了“初始抓取失败”场景，没有宣称它是真实物理实验。Trace 将失败定位到 `action/initial_grasp`，状态为 `FAILED`，来源为 `physical_skill`，扫描结果的 `first_failure_stage` 同步为 `initial_grasp`。后续未发生的动作不会出现在 Trace 中。

## VLM 预留接口

每次 Perception 同时生成结构化 Observation，包含 `observation_id`、`camera_ids`、`frame_refs`、`visual_summary`、coverage 和 `sim_time`。当前决策事件明确标记 `source=deterministic_policy`；本轮没有调用或伪装 Gemini/VLM 推理。

## 回归结果

- Seed 0：54/54、unknown=0、零冲突、合法可解。
- M3-B U 层：实测 90.0°，21/21 视觉验证通过。
- 防作弊：`no_recolor=true`、`logical_state_unchanged=true`、`same_model_and_data=true`。
- TypeScript 类型检查与前端 bundle 构建通过。
- 本地无 MuJoCo 环境的测试使用结构化 Fake Backend 验证事件协议；真实物理验收在部署服务器完成。
