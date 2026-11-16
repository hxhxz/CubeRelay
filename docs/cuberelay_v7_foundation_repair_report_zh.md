# CubeRelay v7 基础能力修复报告

## 结论

本轮暂停 Gemini Task Agent，仅独立验收 A（Place/Release/Regrasp）、B（视觉 Facelet Mapping）和 C（held observation）。B 已通过受控测试；A 的 Place/Release 已通过 16/16，Regrasp 提升到 10/16，但尚未达到可恢复任务级 Agent 全闭环的门槛。因此没有运行 Rule-based/Gemini 全闭环，也没有把部分成功包装成完整扫描成功。

## 失败集审计

输入：`results/task_agent_v7_rule_100_failures.jsonl`。

- place_release：33/114 成功。
- regrasp：16/193 成功。
- observe_released：42/193 成功。
- reorient_pitch_90：16/16 成功。
- observe_held：0/16 成功。

接触级复现显示，旧释放路径在张爪前没有桌面接触，样例 seed 0 的峰值线速度 2.588 m/s、峰值角速度 14.622 rad/s，属于空中释放后的掉落/翻滚。

## A：物理 Place/Release/Regrasp

实现：

- 记录左右接触点、法向、法向力、接触距离、世界位置/四元数/旋转矩阵、线速度、角速度、夹爪宽度、相对滑移和总位移。
- 固定高度张爪改为慢速下降、持续桌面接触与低速确认后才允许 Release。
- 取消不稳定的长距离横向运输，释放位置由 overhead RGB-D 重新定位，inspection gantry 随视觉位置重新居中。
- 新增视觉 6D 姿态：全分割 RGB-D 点云估计中心，面四角点与深度估计完整旋转。
- 根据 6D 姿态生成水平对向面候选；失败后退避、重新观察，并排除已经失败的 face pair。

16 个固定配对场景结果：

| 指标 | 修复前失败集 | 本轮独立验收 |
|---|---:|---:|
| Place/Release 成功 | 33/114 (28.9%) | 16/16 (100%) |
| released observation 有结果 | 42/193 (21.8%) | 16/16 (100%) |
| Regrasp 成功 | 16/193 (8.3%) | 10/16 (62.5%) |
| seed 0 Release 峰值角速度 | 14.622 rad/s | 0.002 rad/s |
| Release 前桌面接触 | 0 samples | 每场至少 6 samples |

仍失败 6 场：`REGRASP_FAILED` 2、`gripper_closure_insufficient` 2、`geometric_misalignment` 2。A 因此仅部分通过。

## B：视觉 Facelet Mapping

新增确定性流程：彩色面区域四角点、DLT 单应性、透视矫正、规范 3x3 采样、显式旋转/镜像 cube-local 索引和逐格置信度。黑暗、遮挡或可见面积不足的格子保持 `None`，接口不接收 simulator cube state；GT 只允许外部评测代码使用。

受控测试 5/5：正视、斜视、180 度翻转、单格遮挡 unknown、RGB-D 完整 6D 姿态。跨视角融合保留每格颜色、置信度、来源视角和帧号。

## C：observe_held 断点

原 high cameras 的世界光轴高度约 0.72 m，旋转后魔方位于其上方，彩色区域集中在图像上边界，部分四角点退化重合。修复包括：提高侧相机、扩大 FOV、调整 top-oblique 相机，并增加每相机彩色像素数、bbox、是否完整入画、四角点、unknown 数和失败阶段日志。

在 9 个成功完成 Regrasp + Reorient 的场景中，observe_held 为 9/9 有结果，每场 3–5 个视角；原失败集是 0/16。其余 7 场未进入有效 held 验收，其中 6 场由 Regrasp 阻塞，不能计为 held 相机失败。

## 可复现命令

```bash
env MUJOCO_GL=glfw python scripts/evaluate_foundations_v7.py \
  --episodes 16 \
  --output results/foundations_v7_a_c_16_retry.jsonl \
  --replays results/replays/foundations_v7_a_c_16_retry

env MUJOCO_GL=glfw python -m pytest -q
```

逐场日志位于 `results/foundations_v7_a_c_16_retry.jsonl`，16 个回放位于 `results/replays/foundations_v7_a_c_16_retry/`。完整自动化测试结果为 129 passed。

## 真实性边界

- Place、Release、Regrasp、Reorient：MuJoCo 接触与摩擦驱动，无 robot weld、无直接物体位姿赋值。
- Facelet mapping：只使用 RGB/RGB-D 和相机标定；不使用仿真内部 Cube State 补全。
- 受约束转面仍是简化 hinge 机制，不是 26-cubie 高保真模型。
- Human handoff 的 `human_grasp_weld` 仍是既有 Mock，本轮未用于 A/B/C 验收。
- Gemini Task Agent 本轮明确未运行；A 未完全通过前不恢复任务级对比评测。

## 下一步阻塞

继续针对 6 个 Regrasp 失败场景审计 6D 面角点质量、候选高度和 approach tangent offset；在 Regrasp 达到预设门槛后，再按相同场景运行 Rule-based 与 Gemini 完整扫描、54 格准确率和合法重建评测。
