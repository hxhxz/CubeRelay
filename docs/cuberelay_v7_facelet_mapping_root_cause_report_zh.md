# CubeRelay v7 Facelet Mapping 根因修复报告

## 1. 本轮范围与结论

本轮只修复 held/released 多视角贴片到 cube-local 54 格 canonical index 的映射。未增加 Agent、Gemini、Memory、重试次数、扫描轮次或机械臂控制策略，也未修改抓取、碰撞和物理转面模型。

修复后，独立几何消融的四层配置均达到 1296/1296 正确贴片；固定 seed=0 的真实连续观察从 released 阶段的 36/54 无冲突正确覆盖，增加到 held 阶段的 45/54，无冲突且没有错误贴片被写入。剩余 9 格 U 面保持 unknown。该 episode 随后因既有 `REORIENT_OR_RECENTER_FAILED` 停止，因此没有声称已完成 54 格扫描或合法重建。

## 2. 根因

定位到四类相互叠加的问题：

1. canonical 面坐标不是单一真源。MuJoCo XML 中 U/D 与侧面的图像网格手性不同，旧 `_LOCAL_FACE_FRAME` 又把 U、D 的 row direction 写反，导致面内旋转或镜像。
2. released 与 held 路径各自使用局部旋转规则，观测网格没有统一经过同一套 observed-to-canonical D4 映射。
3. 单面图像只能约束可见法向，不能唯一消除绕该法向的四重离散姿态歧义；旧路径会将不可靠姿态强行写成确定 index。
4. 对齐后的 gripper/world 初始方向缺少明确标定锚点，导致部分视角出现对面身份错误。另有 dominant-face corner detector 偶尔选择相邻面的问题。

这解释了此前“观测数量高、正确贴片低、冲突索引多”的表现：主要问题不是颜色分类，而是 face identity、面内旋转和镜像的系统性错误。

## 3. 唯一 canonical 坐标规范

实现位于 `src/cube_relay/embodied/canonical_facelets.py`。六个面的 cube-local frame 为：

| Face | normal | row（index 向下） | column（index 向右） |
|---|---|---|---|
| U | +Z | +Y | +X |
| D | -Z | -Y | +X |
| F | -Y | -Z | +X |
| B | +Y | -Z | -X |
| R | +X | -Z | +Y |
| L | -X | -Z | -Y |

面内 canonical index 使用 `index = 3 * row + column`，范围 0～8。坐标变换统一为：

```text
p_world = R_world_from_cube · p_cube + t_world_from_cube
p_camera = T_camera_from_world · [p_world, 1]
pixel = project(K, p_camera)
```

映射器将九个 canonical cell center 投影到图像，枚举方形 D4 群（4 个 quarter-turn × mirror/no-mirror），以归一化投影误差选择 observed grid 到 canonical index 的唯一映射；同时检查 face identity、最大重投影误差与最佳/次佳解间隔。姿态或面身份不可靠时只保留旋转不变的中心格，其余格标为 unknown，不强行赋值。

## 4. held/released 统一路径

`MujocoEmbodiedBackend._read_visible_face_frame` 现在是 released 与 held 的共同入口，统一执行：

1. 从实际相机图像检测面、四角点和 3×3 颜色；
2. 读取刷新后的 cube-to-world、world-to-camera 变换；
3. 调用同一个 canonical D4 映射器；
4. 用同一 assignment 重排颜色和置信度；
5. 不可靠项保持 unknown；
6. 输出 face、canonical assignment、quarter-turn、mirror、误差和可靠性原因。

单面视觉固有的四重姿态歧义由已执行的 `align_scan_axes` 与整体旋转动作历史提供离散方向锚点。该锚点只追踪坐标变换，不改变魔方内部排列。若视觉检测面与预测面不一致，可使用姿态投影四角点重新采样，但必须通过中心贴片颜色与逻辑 face 的一致性校验，否则整面保持 unknown。

GT pose、GT corner、GT color 只存在于测试初始化、诊断和评分脚本，不进入正式 Inspector、融合器或 Planner，也不用于补齐 unknown。

## 5. 独立几何测试

测试使用非纯色固定打乱状态 `R U2 F' L D B2 R' U F2`，覆盖：

- 24 种立方体整体朝向；
- U/D/F/B/L/R 六个面；
- 正视和斜视投影；
- 90°、180°、270° 面内旋转与镜像；
- face identity 错配和不可靠映射拒绝；
- XML facelet 坐标与每面手性的显式校验。

非纯色状态让测试能分别识别面内旋转、镜像、面身份错误和颜色错误，避免复原魔方纯色面掩盖索引问题。

## 6. 四层消融结果

每层为 24 个整体朝向 × 6 个面 = 144 个 view，共 1296 个贴片。

| 配置 | 正确/总数 | 准确率 | 可靠 view |
|---|---:|---:|---:|
| GT Pose + GT Corners + GT Colors | 1296/1296 | 100% | 144/144 |
| GT Pose + GT Corners + Vision Colors | 1296/1296 | 100% | 144/144 |
| GT Pose + Vision Corners + Vision Colors | 1296/1296 | 100% | 144/144 |
| Vision Pose + Vision Corners + Vision Colors | 1296/1296 | 100% | 144/144 |

最后一层使用与正式路径一致的视觉 pose、视觉 corners、视觉 colors，以及由已执行整体动作维护的 D4 方向锚点；没有使用仿真 cube state 补齐贴片。

## 7. 固定 seed 连续观察

seed=0 的逐动作结果：

| 阶段 | 新增正确覆盖 | 累计正确唯一格 | unknown | 冲突 | 错误写入 |
|---|---:|---:|---:|---:|---:|
| released 多面观察 | 36 | 36/54 | 18 | 0 | 0 |
| held 观察 | 9 | 45/54 | 9 | 0 | 0 |
| 后续 held 观察 | 0 | 45/54 | 9 | 0 | 0 |

released 阶段正确获得 R/B/L/F 四面各 9 格；首次 held 观察新增 D 面 9 格。U 面没有获得可靠观测，因此保持 unknown。轨迹在后续既有物理重定向阶段失败，但映射器没有用错误 index 或真值补齐来掩盖该失败。

逐 view 日志包含：当前 visible face、canonical indices、正确/错误贴片、unknown、冲突、累计覆盖、mapping source、quarter-turn、mirror、归一化误差和每个错误的归因。

## 8. 自动化测试

```bash
env MUJOCO_GL=glfw PYTHONPYCACHEPREFIX=/private/tmp/cuberelay-pycache \
  /private/tmp/cuberelay-py313/bin/python -m pytest -q
```

结果：`136 passed in 19.55s`。仅出现 MuJoCo/OpenGL 的 `ARB_clip_control` 环境警告，无测试失败。

独立消融：

```bash
/private/tmp/cuberelay-py313/bin/python scripts/evaluate_facelet_mapping_v7.py
```

最小连续观察：

```bash
env MUJOCO_GL=glfw /private/tmp/cuberelay-py313/bin/python \
  scripts/reproduce_facelet_mapping_seed_v7.py --seed 0
```

## 9. 交付物与剩余问题

- canonical 规范及 D4 映射：`src/cube_relay/embodied/canonical_facelets.py`
- 正式 held/released 统一接入：`src/cube_relay/embodied/mujoco_v2.py`
- pose frame 修正：`src/cube_relay/embodied/perception_v2.py`
- 几何回归：`tests/test_canonical_facelets_v7.py`
- 四层消融：`scripts/evaluate_facelet_mapping_v7.py`
- 固定 seed 最小复现：`scripts/reproduce_facelet_mapping_seed_v7.py`
- 消融数据/可视化：`results/facelet_mapping_v7_ablation.json`、`results/facelet_mapping_v7_minimal_failure.png`
- 连续观察日志/可视化/回放：`results/facelet_mapping_v7_seed0_trace_final.json`、`results/facelet_mapping_v7_seed0_trace_final.png`、`results/replays/facelet_mapping_v7_seed0_final.mp4`

剩余问题是固定 seed 未能可靠观察 U 面，并在既有 `REORIENT_OR_RECENTER_FAILED` 处停止。这属于后续物理重定向/相机可见性问题，不是 canonical facelet mapping 错误；根据本轮禁止事项没有修改该控制流程，也没有在未满足“完整固定 seed 扫描”前恢复 Sequential-20 或 NBV-50 全量评测。
