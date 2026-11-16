# v8 视觉重建 → 求解 → 单步铰链执行 → 视觉复核

## 结论与验收口径

固定 seed=0 的求解首步 `U'`，以及独立重置同场景的回归动作 `R`、`F2`，均完成了 **54/54 视觉状态与符号预测一致、0 unknown、0 冲突、0 差异**。求解输入只来自完整 v8 相机扫描；解法经独立 CubeEngine 逐步执行至复原态验证。

这是既有**独立受约束铰链仿真 + 关节反馈门控贴片外观更新**范围内的闭环，不是机器人接触驱动的真实层块转面。没有建立机器人向转面夹具的物理装夹，也没有增加 26-cubie 模型。面板碰撞仍按原模型关闭，不能把零接触解释为接触抓持成功。

因此报告中 `simplified_loop_passed=true` 表示上述支持范围通过；`acceptance_passed=false` / `contact_physics_verified=false` 明确保留接触驱动转面的未实现边界。这不是视觉验证失败。不能据此声称完整接触式物理转面已经验收。

## 代码审计与复用

| 能力 | 源码 | 实现边界 |
|---|---|---|
| 六面视觉与融合 | `active_inspection_v7.py`、`six_face_inspection.py`、`perception_v2.py` | 实际 RGB-D，沿用 v8；未改 canonical mapping、Agent 或抓取模型 |
| 状态约定 | `cube/state.py`、`canonical_facelets.py` | URFDLB，每面9格 row-major；已经与 Kociemba 对齐，无额外换面/转置 |
| 求解 | `cube/solver.py` | 真实 Kociemba；没有把打乱历史倒放冒充求解 |
| 符号预测 | `cube/moves.py` | 独立几何置换 CubeEngine，不依赖求解器解法执行器或仿真真值 |
| 铰链执行 | `embodied/mujoco_executor.py`、`simulation/cube_relay.xml` | 独立 MjModel 中六个位置伺服铰链，实际 mj_step 与关节反馈；不是接触转层 |
| 外观提交 | `mujoco_v2.py:execute_physical_turn` | 仅 feedback.success 后应用置换和更新材质；这是既有外观抽象，不是物理排列涌现 |
| 新闭环 | `visual_turn_loop.py`、`scripts/verify_visual_turn.py` | 视觉输入、符号验证、执行日志、全新观测 epoch、差异拒绝与不足未验证 |

外观模拟器仍维护内部贴片状态用于渲染，但它不传给本轮求解、融合或比较器。脚本丢弃 reset 返回的真值元数据。新一轮视觉融合不继承转面前贴片，也不使用预测补格。预测仅用于比较。

## 实际修复

1. 外向法线铰链采用右手定则，标准顺时针应对应负角度；修复原正负号相反的问题。`U'` 目标为 +π/2，`R` 为 −π/2，`F2` 为 −π。
2. 执行成功同时要求位置误差 ≤0.03 rad、速度 <0.08 rad/s。记录每步关节目标/实测、时间、接触距离/法向力/物体名称和面板碰撞开关。
3. 新增异常接触阻断：转动面板出现接触，或场景接触穿透超过1 cm、法向力超过10 kN、力非有限值时停止，不能提交外观。这些阈值是保守的实验诊断界限，不是真机安全认证。
4. 诊断发现旧夹具场景 `link1` 胶囊与 `robot_base` 重叠约5.5 cm，反馈出现约2.9×10^17 N。将胶囊轴线起点从0移至0.06 m，半径仍0.055 m，形成5 mm间隙。没有禁用该碰撞，也未修改 `cube_relay_v2.xml`。测试保存旧几何复现并验证安全阻断。
5. 首轮转面后 held 只看到27格；直接侧持放置报 `PLACE_SUPPORT_NOT_REACHED`。复用现有 `task_reorient` 按腕关节编码器回正，再执行现有放置释放和实际相机观察，补全54格。不修改物体位姿、关节限位或抓取策略。

## 固定场景结果

初始视觉状态：

```text
DFUBURBBBUBLLRFRFFRLLRFFDUUBBFDDUDLDRDUULUFRLFDBRBLRDL
```

Kociemba 解法（21步），独立符号执行到复原态：

```text
U' F' R2 B' L D2 F' U' D2 B2 R' F2 L2 F2 U' R2 F2 U' L2 D2 F2
```

`U'` 预测和相机实际重建状态均为：

```text
URBFUBDBBRLLLRFRFFRDURFFDUUBBFDDUDLDFDBULUFRLUBLRBLRDL
```

| 动作 | 来源 | 关节位置误差 rad | 最终速度 rad/s | 新相机状态匹配 | unknown / 冲突 |
|---|---|---:|---:|---:|---:|
| U' | 求解器首步 | 0.008235 | 0.012479 | 54/54 | 0 / 0 |
| R | 显式回归动作，非求解器首步 | 0.008235 | 0.012479 | 54/54 | 0 / 0 |
| F2 | 显式回归动作，非求解器首步 | 0.016470 | 0.024958 | 54/54 | 0 / 0 |

三次观察状态均另外通过 `validate_facelets`。修正后夹具执行期间未记录接触；这仅说明未出现上述场景穿透，不证明面板接触物理有效。

## 测试与 v8 回归

- 新增23项测试：解法符号验证、缺失/冲突/差异拒绝、全部18种动作关节方向与收敛、失败反馈不提交外观、旧几何穿透阻断、修复后的严格检查。
- 完整测试：163 passed；机器可读结果 `results/visual_turn_regression.xml`。
- v8 常规20场重新评测：19/20完整、19/20精确54格、19/20合法，平均正确53.55格，平均冲突0。seed18仍为扫描周期耗尽、45格，未改变原95%表现。结果 `results/visual_turn_v8_regression20.json`，回放 `results/replays/visual_turn_v8_regression20/`。
- 没有新增多种子的转面成功率声明；当前转面视觉端到端验证仅 seed0 三个动作。18种动作测试是独立关节层测试，不是18场视觉端到端实验。

## 复现

```bash
env MUJOCO_GL=glfw PYTHONPATH=src PYTHONPYCACHEPREFIX=/private/tmp/cuberelay-pycache \
  /private/tmp/cuberelay-py313/bin/python scripts/verify_visual_turn.py \
  --seed 0 --output results/visual_turn_seed0_solution

# 分别独立重置场景测试 R 和 F2；默认不传 --move 才是求解器首步
env MUJOCO_GL=glfw PYTHONPATH=src /private/tmp/cuberelay-py313/bin/python \
  scripts/verify_visual_turn.py --seed 0 --move R --output results/visual_turn_seed0_R
env MUJOCO_GL=glfw PYTHONPATH=src /private/tmp/cuberelay-py313/bin/python \
  scripts/verify_visual_turn.py --seed 0 --move F2 --output results/visual_turn_seed0_F2

env MUJOCO_GL=glfw PYTHONPATH=src /private/tmp/cuberelay-py313/bin/python \
  -m pytest -q --junitxml=results/visual_turn_regression.xml
```

每个输出目录包含 `report.json`、`facelets.png`、扫描/操作回放 `episode.mp4`、独立铰链回放 `hinge.mp4`、每张 RGB PNG 和包含深度/内参/外参的 NPZ。铰链视频慢速播放，真实仿真时间以 joint_trace 为准。两段视频是两个独立模型，不伪装成机器人实际装夹的同一场景。

## 失败证据与剩余限制

- `results/visual_turn_seed0_final/`：早期诊断，关节到位但存在旧底座穿透；随后放置失败，只有27格。不得引用为安全成功案例。
- `results/visual_turn_seed0_guarded/`：旧几何被严格安全检查第一步阻断，未提交外观。
- `results/visual_turn_seed0_solution/`、`..._R/`、`..._F2/`：修正后的支持范围内成功案例。
- MuJoCo/OpenGL 输出 ARB_clip_control 不可用警告，深度精度受限；保留原始 RGB-D，未把深度质量声明为无误差。
- 完整接触转层、物理装夹与26-cubie不在本轮实现范围。若下一轮要求接触驱动转面，需要单独改造机构，不能靠材质更新或本报告的视觉匹配证明它已存在。
