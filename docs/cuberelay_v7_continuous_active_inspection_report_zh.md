# CubeRelay v7 Continuous Active Inspection Integration 报告

## 结论

已完成 Continuous Active Inspection 的代码集成、20 场固定顺序扫描、50 场 Rule-based NextBestView 扫描和 20 场困难集诊断。Gemini 未接入。

本轮建立了强制 World State Refresh 和可追踪的 cube-local 贴片融合，但完整扫描、精确 54 格和合法重建率仍均为 0。当前系统不能被描述为已经完成六面重建闭环。主要阻塞是跨视角 cube-local 索引冲突、连续 reorient/recenter 稳定性和困难场景 regrasp，而不是缺少 Agent 决策。

## Regrasp 统计口径核对

- 旧独立验收 8/16：第一候选单次成功。
- 旧独立验收 10/16：允许一次安全退避、重新观察和替代 face-pair 后的 Skill 最终成功。
- 旧独立验收 9/16：成功 regrasp 后继续通过 reorient 的场景数。

本轮所有报告同时保存第一候选成功数和最多两候选后的最终成功数，不再混用。

## 实现内容

### 强制 World State Refresh

Place/Release、Regrasp 前和每次 Reorient 后都必须刷新视觉世界状态。状态包含：

- revision 和产生该 revision 的 Skill；
- 相机来源；
- RGB-D 估计的世界位置；
- cube-to-world 3×3 旋转；
- 当前可见面和支撑面；
- 置信度和估计来源。

优先使用面四角点、单应性和 RGB-D 的完整 6D 解；四角点不足时允许使用相机标定坐标系、视觉中心面和 RGB-D 轮廓的完整 6D 近似。该路径明确标记为 `rgbd_calibrated_face_frame_approximation`，不是高精度模型，也不是仿真真值。

Regrasp 每次都基于最新 revision 重新生成候选，并继续使用既有 IK、桌边/手掌碰撞检查和接触安全条件。

### 连续主动观察

- 首次物理 Place/Release 后观察 released cube。
- 重新估计 6D 位姿和支撑面后执行 Regrasp。
- 保持稳定抓取期间连续执行受约束 Pitch/Yaw reorient、World State Refresh 和 held observation，避免重复执行已知不稳定的侧放。
- Sequential 使用固定 `pitch/yaw` 序列。
- NextBestView 根据各 cube-local 面剩余 unknown 数，在受验证的 pitch/yaw Skill 中选择下一视角。

### 视觉融合与评测隔离

- 所有面使用透视矫正后的规范 3×3 格坐标。
- 每条证据保存 face、index、color、confidence、source_view 和 frame。
- 未观察或遮挡贴片保持 unknown。
- 同一 canonical index 出现不同颜色时记录冲突，不静默覆盖。
- 仿真内部 Cube State 只在评测脚本中用于计算正确贴片数；不进入 Inspector、Planner、World State Refresh 或融合器。

## 评测结果

### 固定顺序 20 场

| 指标 | 结果 |
|---|---:|
| Place/Release + Refresh | 20/20 |
| Released observation | 20/20 |
| Regrasp 第一候选 | 10/20 |
| Regrasp 最终 | 13/20 |
| Regrasp 恢复收益 | +3 |
| Pitch reorient + Refresh | 17/19 |
| Yaw reorient + Refresh | 8/17 |
| Held observation | 25/25 |
| 平均正确贴片/54 | 21.0 |
| 平均 unknown | 21.3 |
| 平均冲突索引 | 12.2 |
| 完整扫描率 | 0% |
| 精确 54 格率 | 0% |
| 合法率 | 0% |

Released observation 的逐观测贴片为 514 正确、180 错误；Held observation 为 287 正确、448 错误。后者说明 held 视角的 cube-local 朝向映射仍是主要视觉问题。

### Rule-based NextBestView 50 场

| 指标 | 结果 |
|---|---:|
| 初始抓取 | 46/50 |
| Place/Release + Refresh | 46/46 |
| Released observation | 46/46 |
| Regrasp 第一候选 | 28/46 |
| Regrasp 最终 | 33/46 |
| Regrasp 恢复收益 | +5 |
| Pitch reorient + Refresh | 169/171 |
| Yaw reorient + Refresh | 1/5 |
| Held observation | 170/170 |
| 平均正确贴片/54 | 20.32 |
| 平均 unknown | 21.9 |
| 平均冲突索引 | 14.12 |
| 平均动作数 | 11.6 |
| 完整扫描/精确54/合法率 | 0% / 0% / 0% |

首次停止原因：扫描轮次耗尽但仍有 unknown/冲突 27，reorient/recenter 失败 6，regrasp 类失败 10，初始抓取失败 4，World State Refresh 失败 3。

NBV 能持续获得观测，但没有改善最终正确率；这是基础坐标映射问题的证据，不能归因于需要更强的 Gemini 规划。

### 困难集 20 场

| 指标 | 结果 |
|---|---:|
| 初始抓取 | 17/20 |
| Place/Release + Refresh | 17/17 |
| Regrasp 第一候选 | 2/17 |
| Regrasp 最终 | 6/17 |
| Regrasp 恢复收益 | +4 |
| 平均正确贴片/54 | 13.2 |
| 平均 unknown | 33.35 |
| 平均冲突索引 | 6.1 |

Regrasp 首次失败分类：几何未对准 4、闭合不足 3、未分类 regrasp 失败 1、单侧推动 1；另有初始抓取失败 3和 World State Refresh 失败 2。

## 回归测试

完整测试：`132 passed in 20.18s`。新增测试覆盖：

- unknown 保留和 canonical index 冲突；
- NBV 对 U/D 缺失选择 Pitch；
- NBV 对侧面缺失选择 Yaw；
- 既有透视、翻转、遮挡、6D、MuJoCo 和安全回归继续通过。

## 可复现命令

```bash
env MUJOCO_GL=glfw python scripts/evaluate_active_inspection_v7.py \
  --mode sequential --episodes 20 \
  --output results/active_inspection_v7_sequential_20_final.json \
  --replays results/replays/active_inspection_v7_sequential_20_final

env MUJOCO_GL=glfw python scripts/evaluate_active_inspection_v7.py \
  --mode nbv --episodes 50 \
  --output results/active_inspection_v7_nbv_50.json \
  --replays results/replays/active_inspection_v7_nbv_50

env MUJOCO_GL=glfw python scripts/evaluate_active_inspection_v7.py \
  --mode difficult --episodes 20 \
  --output results/active_inspection_v7_difficult_20.json \
  --replays results/replays/active_inspection_v7_difficult_20

env MUJOCO_GL=glfw python -m pytest -q
```

三个回放目录分别包含 20、50、20 个 MP4。

## 真实性边界

- 抓取、释放、Regrasp 和整体旋转由 MuJoCo 接触/摩擦与 actuator 驱动。
- 未引入 robot weld、mocap 附着或物体位姿瞬移。
- 未以 `_appearance_state` 或 body pose 补齐未观测贴片。
- GT 仅在 `evaluate_active_inspection_v7.py` 中评分。
- 6D 标定坐标回退是近似模型，已在日志中明确标记。
- Human handoff weld Mock 和简化转面 hinge 仍是既有边界，本轮扫描未使用 Human handoff。
- Gemini 本轮没有调用。

## 下一优先级

1. 用受控 reorient 前后图像建立明确的六面索引旋转单元测试，修复 held observation 的 90°/镜像映射。
2. 将 NBV 的收益判据从“新增颜色”升级为“新增无冲突 canonical index”，对重复冲突视角停止继续 Pitch。
3. 单独修复 Yaw reorient/recenter 和困难场景的接近高度/闭合几何。
4. 只有当 54 格正确率和合法率非零且稳定后，才恢复 Gemini 对照。
