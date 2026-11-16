# CubeRelay v7 源码审计、实现状态与100场景报告

## 结论

v7 已新增任务级 `EmbodiedTaskAgent`、统一 Planner 接口、Gemini 从任务开始参与的受限 Skill 决策、真实调用追踪、固定扫描工位相机以及物理 PLACE/RELEASE/REGRASP/REORIENT 接口。v6 `FailureAwareSkillAgent` 被保留并作为抓取子任务调用，没有重写其接近碰撞、双侧接触、试抬和恢复逻辑。

但“随机魔方→完整六面扫描→54格准确重建→合法性验证”的物理闭环目前**未达标**。100个固定随机场景的离线底层评测为：完整扫描0%，合法重建0%，准确54格0%，重抓成功率8.29%。因此没有启动100场景 Gemini 在线评测；在底层物理闭环全失败时调用模型只会浪费调用并把物理缺陷混入决策指标。

## 全源码能力审计

| 能力 | 结论 | 证据 | 真实性说明 |
|---|---|---|---|
| v6抓取子任务 | 已实现、已复用 | `failure_aware_v6.py:543`；v7 `task_agent_v7.py` 调用 `FailureAwareSkillAgent(...).run(reset_scene=False)` | MuJoCo接触物理，无机器人weld |
| 真实VLM观察 | 部分实现 | `vlm.py` 有云端场景VLM；v7 `GeminiTaskPlanner` 接收实际RGB图像和任务观测 | Gemini负责高层Skill选择；精确姿态/颜色仍由确定性模块负责 |
| Gemini从任务开始参与 | 已实现 | `task_agent_v7.py:128-187`；首个允许Skill为 `observe_cube` | 每个循环/Skill结果后重新调用；越权Skill被拒绝 |
| 主动六面扫描 | 代码存在但端到端未通过 | `mujoco_v2.py:1028-1095`；固定四侧、顶视和重定向相机位于XML | 当前100场景完整扫描0%，不得称为完成 |
| PLACE/RELEASE | 真实物理但低可靠 | `mujoco_v2.py:993-1026` | 通过保持接触下降、打开指爪、接触检查；81/100终止于此 |
| REGRASP | 真实物理但低可靠 | `mujoco_v2.py:1097-1105`；v7恢复路径复用v6 | RGB-D定位、摩擦接触抓取；100场景成功率8.29% |
| REORIENT/翻转 | 真实腕关节运动但不稳定 | `mujoco_v2.py:1107+` | 监测双侧接触和滑移，并用RGB-D再居中；未能稳定暴露底面 |
| 坐标追踪 | 部分实现 | v7 `pose_track`；重定向后由overhead RGB-D再定位 | 不用逻辑Cube State；尚无完整SE(3)面坐标历史与不确定度传播 |
| 54贴片融合 | 数据结构已实现 | `perception_v2.py:115-177` | 保存颜色、置信度、来源视角、遮挡/unknown；不以真值补全 |
| 54贴片视觉识别 | 未达标 | `mujoco_v2.py:930-991` | 当前观察贴片准确率26.14%；透视下3×3索引和颜色仍有错误 |
| 状态合法性 | 已实现但本轮未到达 | `StickerStateFusion.validated_facelets()` 调用独立 `validate_facelets` | 只有54格齐全才验证；不会补全unknown |
| 受约束转面 | 已实现、简化模型 | `mujoco_executor.py`；`execute_physical_turn()` | 单面铰链/执行器反馈，不是26-cubie高保真动力学 |
| 人类交接 | Mock | XML `human_grasp_weld`、`mujoco_v2.py:hand_over()` | 明确为虚拟人类夹持器weld，不应称为真实物理人手 |
| Fixed/Rule Planner | 仅离线对照 | `FixedTaskPlanner`、`RuleTaskPlanner` | 不作为Gemini失败时的在线回退 |

## v7任务架构

```text
GeminiTaskPlanner
  输入：真实RGB、视觉位姿、融合覆盖、失败历史、允许Skill
  输出：一个受约束TaskSkill
            |
            v
EmbodiedTaskAgent
  observe_cube
  grasp_cube_v6 ----------> FailureAwareSkillAgent v6
  align_scan_axes                 |
  place_release                   +--> 既有碰撞/接触/试抬安全门
  observe_released
  regrasp
  reorient_pitch/yaw
  observe_held
  validate_state ----------> StickerStateFusion + validate_facelets
```

VLM不能输出关节目标、物体位姿、贴片答案、碰撞开关或安全绕过。Planner选择不在当步白名单内时，调用记录错误并终止，不回退到Rule。

## 100场景固定随机评测

命令：

```bash
MUJOCO_GL=glfw python scripts/evaluate_task_agent_v7.py \
  --planner rule --episodes 100 --seed 0 \
  --output results/task_agent_v7_rule_100.json
```

| 指标 | 结果 |
|---|---:|
| 完整扫描率 | 0% |
| 合法重建率 | 0% |
| 精确54格率 | 0% |
| 54格总体准确率（unknown按错） | 19.98% |
| 已观察贴片准确率 | 26.14% |
| 重抓成功率 | 8.29% |
| 平均动作数 | 8.84 |
| 平均墙钟耗时 | 0.799秒 |
| PLACE_OR_RELEASE_FAILED | 81 |
| TASK_STEP_LIMIT | 19 |
| VLM调用 | 0（离线物理门禁评测） |

真值只在评测脚本完成episode后计算指标，不进入Agent、Planner、融合器或合法性模块。

## 为什么没有运行100场景Gemini

Gemini接口已实现并有单元测试证明从第一个任务决策开始调用。当前底层在同一100场景上完整扫描率为0；在线运行预计只会产生大量调用，无法区分模型规划能力与必然的物理/视觉失败。启动门槛应至少是Rule对照在相同Skill下获得可测的非零完整扫描率，并修复已观察贴片仅26.14%的视觉索引问题。

## 当前根因

1. 侧放时魔方在指爪卸载后发生大位移，导致工位丢失；虽已加入overhead RGB-D再定位，但后续放置仍不稳定。
2. 平行夹爪完成第一次翻转后，侧放状态的重新抓取成功率极低。
3. 斜视图的九贴片组件会跨面混选，图像网格顺序没有完整投影到魔方局部面坐标，造成颜色虽来自真实像素但索引错误。
4. 持握翻转时夹爪遮挡严重；被遮挡贴片保持unknown，没有用内部状态补齐，这是正确但尚未闭环。
5. 当前魔方是一个带54个视觉贴片的刚体；转面仍是独立受约束铰链近似，不是26个cubie接触模型。

## 下一修复顺序

1. 增加物理V形侧放托架或受约束scan cradle，稳定释放但不固定魔方到末端；
2. 用相机标定和单应性将每个可见面的贴片投影到规范3×3坐标，禁止仅按图像行列排序；
3. 在翻转前后以视觉中心贴片和面法向验证真正发生了目标整体旋转；
4. 先通过10/100场景Rule物理门禁，再运行Gemini 100场景；
5. Gemini、Fixed、Rule必须继续使用完全相同的Skill、安全约束和随机种子。
