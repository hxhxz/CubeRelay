# CubeRelay v8 完整六面主动感知实现与评测报告

## 结论

已完成基于纯相机像素（RGB-D）与机器人自身关节本体感觉的完整六面主动感知闭环实现与验证。在不使用仿真器 `cube` 真值位姿或 `_appearance_state` 的前提下，机器人能够自主抓取、对齐扫描轴、放置与释放、无遮挡观测释放魔方（含上表面 `U` 及四个侧面）、重新抓取、连续旋转（Pitch/Yaw）补全下表面 `D` 及缺失格，并通过 `validate_facelets` 合法性校验重建完整的 54 格状态。

相比先前 20/50/20 基准上的 **0% 完整扫描 / 0% 精确 54 格**，本轮评测结果提升为：

| 评测任务 / 流水线 | 场景数 | 完整扫描 / 成功率 | 精确 54/54 率 | 合法率 | 平均正确格数 | Regrasp 最终成功 |
|---|---:|---:|---:|---:|---:|---:|
| `ContinuousActiveInspector` (`sequential`) | 20 | 95% (19/20) | 95% (19/20) | 95% (19/20) | 53.55 / 54 | 20 / 20 |
| `ContinuousActiveInspector` (`nbv`) | 50 | 76% (38/50) | 76% (38/50) | 76% (38/50) | 47.78 / 54 | 46 / 46 (4 场初始抓取失败) |
| `ContinuousActiveInspector` (`difficult`) | 20 | 60% (12/20) | 60% (12/20) | 60% (12/20) | 41.85 / 54 | 17 / 17 (3 场初始抓取失败) |
| `SixFaceActiveInspector` | 20 | 95% (19/20) | 95% (19/20) | 95% (19/20) | — | — |
| `EmbodiedTaskAgent` (`RuleTaskPlanner`) | 20 | 95% (19/20) | 95% (19/20) | 95% (19/20) | — | — |

## 关键实现与修复

### 1. 纯相机 6D 朝向与平移/尺度不变 D4 格映射
- **`src/cube_relay/embodied/six_face_inspection.py`**：
  - `estimate_orientation_from_centers` 在 24 种魔方离散旋转群上联合中心贴纸颜色与朝向先验求解唯一朝向（包含 `align_scan_axes` / `reorient` 引起的纯 Z 轴消歧）。
  - `solve_d4_assignment` 在投影 2D 轮廓角点与实测四边形之间采用中心化+尺度归一化后的平移/尺度不变 D4 分配，并验证边缘间隔。
  - `SixFacePerception` 增加 `_corners_in_frame` 与 `_quad_aspect_ok`：在 `detect` 阶段拒绝贴边裁剪或大畸变四边形（置 `label=None`）；在 `map_detection` 需要重投影时先校验投影四边形位于图像内且中心贴纸一致且无空值贴纸后再输出。
  - `InformationGainViewPlanner` 与 `SixFaceActiveInspector` 按未知格数分布与抓持防遮挡约束规划下一步 Pitch/Yaw 动作。

### 2. 无遮挡顶部观测、龙门架避障与主动阻尼定位
- **`simulation/cube_relay_v2.xml`**：新增偏置向下相机 `inspection_down_pos_y` (`pos="0 .22 -.30"`) 与 `inspection_down_neg_y` (`pos="0 -.22 -.30"`)，观察桌面魔方上表面 `U` 时使夹爪偏移出视野。
- **`src/cube_relay/embodied/mujoco_v2.py`**：
  - `_place_and_release`：释放后以 `robot_z_ctrl=-0.02` 抬升避开龙门横梁（`robot_z_joint` 稳定在约 `-0.089`，指垫离地约 `0.90 m`、同时 `robot_z` 胶囊低于 `robot_base` 梁），随后退避至 `(-0.45, +0.45)`，远离 `human_receiver (+0.55, +0.35, 0.82)` 与 `overhead` 相机视线。
  - `_move_gantry_xy_damped`：仅读取机器人自身 `robot_x_joint` / `robot_y_joint` 编码器位置和速度（不接触物体状态），对欠阻尼龙门架执行 PD 速度阻尼定位，并在 `jnt_range` 范围内限幅。
  - `capture_released_views`：先以 `overhead` 粗定位后用水平四向相机 `RELEASED_SIDE_CAMERAS`（`inspection_x`/`inspection_neg_x` 精修 X、`inspection_y`/`inspection_neg_y` 精修 Y）消除 `overhead` 斜视约 2 cm 的 Y 偏置，再精准将 `inspection_down_pos_y` / `inspection_down_neg_y` 移至魔方正上方捕获无遮挡顶视图，最后回到精修中心 `(cx, cy)` 拍摄四向侧面。
  - `task_observe_released` / `task_observe_held`：接入 `SixFacePerception` 与 `estimate_orientation_from_centers`；在 `active_inspection_v7.py` 与 `task_agent_v7.py` 中 `regrasp` 成功后立即补采 `task_observe_held` 刷新抓持朝向先验。
  - `task_reorient`：由于 `inspection_*` 相机随手臂共同挂载于 `robot_y`，移除会晃动已俯仰魔方的 XY 假回中平移运动，改为多相机视觉定位核验与双指接触保持检查。
  - `refresh_visual_world_state`：扩展 `world_top` 与 `HELD_CAMERAS` 候选视角，并在单目四角点缺失但 RGB-D 成功定位且动作链已有可靠旋转锚点时使用 `rgbd_detection+action_history_orientation_anchor` 回退，避免误报 `WORLD_STATE_REFRESH_FAILED`。

## 验证与可复现命令

```bash
# 全量单测与 MuJoCo 集成测试
env MUJOCO_GL=glfw PYTHONPATH=src PYTHONPYCACHEPREFIX=/private/tmp/cuberelay-pycache \
  /private/tmp/cuberelay-py313/bin/python -m pytest -q
# 结果: 140 passed in 22.01s

# Seed 0 完整六面复现
env MUJOCO_GL=glfw PYTHONPATH=src PYTHONPYCACHEPREFIX=/private/tmp/cuberelay-pycache \
  /private/tmp/cuberelay-py313/bin/python scripts/reproduce_facelet_mapping_seed_v7.py \
  --seed 0 --output results/u_face_seed0_final.json --replay results/replays/u_face_seed0_final.mp4
# 结果: success=true, final_unknown=0, final_conflicts=0, final_correct_unique=54

# 20/50/20 主动感知评测
env MUJOCO_GL=glfw PYTHONPATH=src PYTHONPYCACHEPREFIX=/private/tmp/cuberelay-pycache \
  /private/tmp/cuberelay-py313/bin/python scripts/evaluate_active_inspection_v7.py \
  --mode sequential --episodes 20 \
  --output results/active_inspection_v8_sequential_20.json \
  --replays results/replays/active_inspection_v8_sequential_20

env MUJOCO_GL=glfw PYTHONPATH=src PYTHONPYCACHEPREFIX=/private/tmp/cuberelay-pycache \
  /private/tmp/cuberelay-py313/bin/python scripts/evaluate_active_inspection_v7.py \
  --mode nbv --episodes 50 \
  --output results/active_inspection_v8_nbv_50.json \
  --replays results/replays/active_inspection_v8_nbv_50

env MUJOCO_GL=glfw PYTHONPATH=src PYTHONPYCACHEPREFIX=/private/tmp/cuberelay-pycache \
  /private/tmp/cuberelay-py313/bin/python scripts/evaluate_active_inspection_v7.py \
  --mode difficult --episodes 20 \
  --output results/active_inspection_v8_difficult_20.json \
  --replays results/replays/active_inspection_v8_difficult_20
```

评测输出保存在：
- `results/u_face_seed0_final.json` 与 `results/replays/u_face_seed0_final.mp4`
- `results/active_inspection_v8_sequential_20.json`
- `results/active_inspection_v8_nbv_50.json`
- `results/active_inspection_v8_difficult_20.json`
- `results/six_face_and_task_agent_20.json`

## 真实性边界与遗留问题

- **仿真真值隔离**：视觉感知、状态刷新、NBV 规划与贴片融合仅使用相机 RGB-D 像素与机器人关节本体感觉，魔方真值位姿与内部贴片状态仅用于评测计分。
- **剩余失败分布**：
  - `sequential` / `SixFaceActiveInspector` / `EmbodiedTaskAgent` 在 Seed 0–19 上均达到 19/20 (95%)，唯一共同失败来自 Seed 18（多轮抓取或释放阶段触碰桌面支撑判断 `PLACE_SUPPORT_NOT_REACHED` / 达到最大扫描周期 `SCAN_INCOMPLETE_AFTER_MAX_CYCLES`）。
  - `nbv` 50 场剩余 12 场失败中：4 场为 `initial_grasp`（Seed 25, 31, 46, 49），6 场为 `SCAN_INCOMPLETE_AFTER_MAX_CYCLES`（多为单侧面仍缺 9 格），2 场为 `REORIENT_JOINT_LIMIT`。
