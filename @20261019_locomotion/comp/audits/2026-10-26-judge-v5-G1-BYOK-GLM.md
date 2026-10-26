```json
{
  "verdict": "FAIL",
  "decision": "REJECT",
  "checklist": [
    {
      "id": "A",
      "item": "规则忠实性（Part2 逐障碍成功/失败 + 分数表 + 尝试次数语义）",
      "verdict": "FAIL",
      "evidence": [
        "eval_blackw_part2.py:Part2OfficialJudge.update — 成功谓词为'四轮高度带 + 基座 x/y'，非接触/支撑判定；hold_s+TERMINAL_HOLD_EXTRA_S(0.1s)、WHEEL_ON_SURFACE_TOL_M(0.06)、gap 允许下沉 min(0.5*depth, wheel_r)、wall climb_z_min(0.52–0.58) 均为规则原文不存在的自拟阈值（规则 docs/00-competition/rules-team-race-2026.md §3 只说'越过即得分'）",
        "comp_part2_judge.py:Part2JudgeV2._cond — 同一'成功上到高台'在 V2 中是 base_z>=top_z+0.38 + foot tag + 无 ground_feet，与 v5 的四轮终态带语义实质漂移，两者不可能同时对规则忠实",
        "eval_blackw_part2.py:main — total_score 对 20 档全量尝试取最高成功档，完全没有建模'每种障碍至多 4 次挑战'（rules §3.1），产出不是规则口径的 Part2 得分",
        "docs/00-competition/rules-team-race-2026.md §3.2 vs comp_part2_judge.py:curve_points_floor — 分数曲线/floor/10cm 端点 0 分与规则一致（self-test 已断言），此项 PASS",
        "Part1 八障碍 judge（comp_part1_judge.py）未在材料中提供，A 类 Part1 条目全部无法核验"
      ],
      "fix": "对 v5 每个自拟阈值补规则依据或主办方书面口径；统一两套 judge 语义；在 runner 层实现 4 次尝试预算与官方计分口径"
    },
    {
      "id": "B",
      "item": "漏洞与可被利用面（绕行/贴边/卡边界/reward hacking）",
      "verdict": "FAIL",
      "evidence": [
        "eval_blackw_part2.py:platform/slope cond — 只检查 wheel_z∈[top-0.06, top+0.20] 与 base x∈x_range，不检查轮子是否在平台正上方/接触平台：机器人可用后两轮上台、前两轮抬至台面高度做 wheelie 保持 0.3s 判 success（'成功上到上平面'被弱化为高度带）；slope 同理可在 landing 边缘悬轮保持。若 judge 被用作训练 termination，这是明确的 reward-hacking 面",
        "eval_blackw_part2.py:gap — 槽内下沉允许 min(0.5*0.30, 0.103)=0.103 m：轮子可下探 ~10cm 仍算'越过沟壑'，规则无此容忍度依据",
        "eval_blackw_part2.py:wall — climb_z_min(20cm 墙=0.54) 接近站立基高(~0.42-0.46, 见 trials.jsonl base 字段)，爬升证据弱；主要靠 crossed+四轮落地兜底",
        "part2_official_levels.json:high_wall lane_half_width=0.7 == 墙体 y 半宽 0.7（part2_off_high_wall_*.xml size 0.7），车道与墙等宽、零余量，贴边挤过仅需基座 y 略偏（实际被碰撞兜住，但边界无安全带）",
        "正面确认：wall/gap 的 crossed 需在 lane 内发生、stairs/slope 有高度门槛、plum 在 cube_x_range 内触地即 fail——绕行路径基本被封死（fail-closed）"
      ],
      "fix": "成功谓词改为'轮底高度带 AND 轮心投影落在支撑面水平范围'或直接用接触法向/接触几何；收紧 gap 下沉容忍；wall 增加真实接触证据"
    },
    {
      "id": "C",
      "item": "协议诚实性（种子/起点/命令/操作手/judge 版本/一致性抽查）",
      "verdict": "WARN",
      "evidence": [
        "manifest.json:protocol — seeds=[]、seed_control='none（runner 未设种子/扰动）'、diagnostic=true，诚实标注；operator=scripted 已记录",
        "summary.json vs trials.jsonl 抽查 3 条：trench 4 条（r21-r24: 30/20/10/30cm 全 fail）、high_platform 4 条（r1-r4 全 fail）、plum 4 条（r9-r12 全 fail）与 summary 全 0 分、attempts_used=4 一致 ✓",
        "eval_blackw_part2.py:payload — 权威 v5 的输出不含 operator、seed（仅可由 args.seed 推算）、不产 manifest/trials/summary 三件套，违反 comp/eval/_protocol.md §6 的产物契约",
        "eval_blackw_part2.py:run_attempt — judge 创建后先 warmup 0.4s 不经过 judge.update（起点距障碍 ≥1.8m，实际不可达，风险低）",
        "V2 的 foot_tags/ground_feet 由 runner（run_part2_judged_eval.py）喂入，该 runner 未提供，V2 判定的输入端不可审计"
      ],
      "fix": "v5 输出对齐三件套 schema；记录 seed/operator/命令序列；提供 V2 runner 源码或废弃 V2"
    },
    {
      "id": "D",
      "item": "证据链（多仓 commit/sha256/uv.lock/成功证据可复现性）",
      "verdict": "FAIL",
      "evidence": [
        "manifest.json:repos — training commit='unknown:flat-ft-2500-part2-official-diag'（训练仓 commit 未采集）、task dirty=true、control 'unknown:not-used'；全 manifest 无 uv.lock/依赖锁定",
        "manifest.json:judge.version='comp_judge_v2@e1fe98733aa3' — 样例产物由非权威 V2 judge 生成，而验收口径（acceptance-eval-protocol.md §2.3）指定 v5 为权威；历史分数不可映射到 v5",
        "trials.jsonl — 所有 trial video:null；无任何成功样本（全 fail），成功侧证据链为零",
        "LABELS_PROVENANCE.md — rulecard/session 标签非盲标、judge 修复后未重新人工复核；C1 的 100% 一致率不含 v5"
      ],
      "fix": "补训练仓 commit + 依赖锁；v5 评测强制录像；成功 rollout 出现后重跑 C1 并以 v5 为对象"
    },
    {
      "id": "E",
      "item": "合规（传感器红线/力矩/仅 RL/真值用途）",
      "verdict": "WARN",
      "evidence": [
        "eval_blackw_part2.py:PolicyRunner._obs — obs 仅 commands/base_ang_vel/projected_gravity/joint_pos/joint_vel/last_action，无机身线速度/heightmap/足底力/足端高度/机身高度 ✓",
        "eval_blackw_part2.py:_apply_torque — tau 截断到 cfg torque_limits；blackW_description.xml actuator ctrlrange hip/thigh ±23.7(≤25)、calf ±59.25(≤60) ✓；但 wheel joint ±20 N·m 在规则力矩表中无对应条目（规则只列大腿/髋/小腿）",
        "eval_blackw_part2.py — 策略回路只有 TorchScript policy，无固定动作/状态机 ✓（Part2 仅 RL 满足）；--slow-from-x 用世界 x 切换命令属'真值仅生成速度指令'允许范围 ✓",
        "CONTRACT.json:policy_contract — actor_obs_dim 45/action 12 与实际 blackW 部署（57×6=342 obs、16 action）矛盾，机读契约已过期，且机器人形态（4 主动轮）与'仿生足式'赛事的相容性无主办方口径"
      ],
      "fix": "更新 CONTRACT.json 到 blackW 契约；向主办方书面确认轮式关节与轮腿形态合法性及 wheel 力矩上限"
    },
    {
      "id": "F",
      "item": "范围与泛化（覆盖集/种子/起点/结论措辞）",
      "verdict": "FAIL",
      "evidence": [
        "docs/20-part2-shared/acceptance-eval-protocol.md §6 — 用户已确认的覆盖集验收口径'评测工具改造未实施'（正态初始状态采样、稳定/穿越双子集、held-out 均未实现）",
        "eval_blackw_part2.py:run_attempt — 默认 seed=0、零 jitter、零关节扰动、固定 spawn(0,0,0.5)、恒定命令：无起点/扰动泛化证据",
        "part2_official_levels.json — 全部固定布局、固定 spawn/命令/时长；trials.jsonl 为单次尝试，任何稳定性结论均超证据"
      ],
      "fix": "实现覆盖集采样器与 held-out 划分后再谈鲁棒性；当前所有结论必须限定为'固定布局诊断'"
    }
  ],
  "top_rejection_risks": [
    {
      "reason": "权威 judge v5（JUDGE_VERSION=v5-wheel-terminal-bands-2026-10-25，晚于 10-23 的 C1 标定）没有任何人工标定或对照实验：C1 的 92 条记录全部针对 Part2JudgeV2（records.jsonl 的 detail 字段为 V2 输出 schema），v5 的每个成功谓词都是未经验证的新语义。所有 A 类成功条件对 v5 均为 NOT_RUN。",
      "severity": "FATAL",
      "evidence": [
        "comp/eval/_calibration/records.jsonl（detail 仅含 x/z/max_z/tilt_deg，为 V2 字段；无 wheel 终态字段）",
        "comp/eval/_calibration/LABELS_PROVENANCE.md（'真实成功 rollout 仍缺失…成功侧证据目前是 rulecard + judge 实现'）",
        "@20261024_blackw/scripts/eval_blackw_part2.py:JUDGE_VERSION='v5-wheel-terminal-bands-2026-10-25'"
      ],
      "fix_type": "experiment",
      "resolved": false
    },
    {
      "reason": "双 judge 语义漂移且历史产物用非权威 judge 生成：Part2JudgeV2（base_z≥top+0.38 + tag + 无 ground_feet）与 Part2OfficialJudge v5（四轮终态高度带 + descend/top_seen）对同一规则条件给出不同判罚；样例评测三件套的 judge.version=comp_judge_v2，与验收协议指定的权威 v5 不符，现有分数不可作为 v5 口径依据。",
      "severity": "FATAL",
      "evidence": [
        "comp_part2_judge.py:Part2JudgeV2._cond vs eval_blackw_part2.py:Part2OfficialJudge.update",
        "comp/eval/flat-ft-2500-part2-official-diag/manifest.json:judge.version",
        "docs/20-part2-shared/acceptance-eval-protocol.md §2.3（'判 success 用权威 judge 的终态谓词 eval_blackw_part2.py / judge v5'）"
      ],
      "fix_type": "structural",
      "resolved": false
    },
    {
      "reason": "v5 成功谓词是'高度带'而非'支撑接触'：platform/slope 只验四轮 z∈[top-0.06,top+0.20] 与基座 x 范围，不验轮子在平台/landing 水平投影内。存在 wheelie/边缘悬轮保持 0.3s 骗分路径；若该 judge 进入训练回路即成 reward hacking。",
      "severity": "MAJOR",
      "evidence": [
        "eval_blackw_part2.py:kind=='platform'/'slope' 分支（cond 仅 wheel_z 带 + lateral_ok + x 范围）"
      ],
      "fix_type": "structural",
      "resolved": false
    },
    {
      "reason": "4 次尝试预算未建模：v5 的 total_score 假设对 20 档不限次尝试取最高成功档，不是规则'每种障碍至多 4 次挑战、仅记录最高难度'的得分；以该数字对外报告即构成超口径计分。",
      "severity": "MAJOR",
      "evidence": [
        "eval_blackw_part2.py:main（categories/best_level/total 计算无 attempt 预算）",
        "docs/00-competition/rules-team-race-2026.md §3.1"
      ],
      "fix_type": "analysis",
      "resolved": false
    },
    {
      "reason": "证据链断点：训练仓 commit 未采集、task 仓 dirty、无 uv.lock/依赖锁、成功样本视频为零、v5 输出不落 manifest/trials/summary 契约且不记录 seed——任何 v5 分数目前不可复现、不可审计。",
      "severity": "MAJOR",
      "evidence": [
        "comp/eval/flat-ft-2500-part2-official-diag/manifest.json:repos.training",
        "eval_blackw_part2.py:payload（无 seed/operator/trials 字段）"
      ],
      "fix_type": "structural",
      "resolved": false
    }
  ],
  "missing_controls": [
    {"claim": "v5: 高台成功=四轮达台面终态", "minimal_control": "用 v5 重放 C1 的 12 条 part2 rulecard（成功/失败各半）+ 2 条边缘悬轮/wheelie 合成轨迹，验证判罚", "status": "NOT_RUN"},
    {"claim": "v5: 楼梯成功=登顶+下行至地面终态", "minimal_control": "v5 对'只登顶不下行'与'绕行至终点'两条对照轨迹的判罚（前者应 fail 或经主办方确认为 success，后者应 fail）", "status": "NOT_RUN"},
    {"claim": "v5: 斜坡成功=达顶 landing 保持", "minimal_control": "v5 对'上坡中途折返'与'landing 边缘悬轮保持'对照轨迹判罚", "status": "NOT_RUN"},
    {"claim": "v5: 高墙成功=lane 内越墙+四轮落地+爬升证据", "minimal_control": "v5 对 lane 外绕行后返回、以及贴 y=0.7 边挤过的对照轨迹判罚（应 fail/timeout）", "status": "NOT_RUN"},
    {"claim": "v5: 沟壑成功=越槽+轮不下沉超限", "minimal_control": "v5 对'槽内下沉 0.10m 后爬出'轨迹判罚，并确认该容忍度有规则或主办方依据", "status": "NOT_RUN"},
    {"claim": "v5: 梅花桩成功=全程不触地达出口平台", "minimal_control": "v5 对'桩间落地'与'绕行'轨迹判罚（应 fail）", "status": "NOT_RUN"},
    {"claim": "分数曲线 floor/插值/10cm 端点 0 分", "minimal_control": "comp_part2_judge.py:run_self_test 的断言组（trench 25→225、wall 10→0、platform 35→150 等）", "status": "RUN"},
    {"claim": "最高难度聚合（best_level→score_for_level）", "minimal_control": "代码走查（main 循环取 max level）——正确，但未含 4 次尝试预算语义", "status": "RUN"},
    {"claim": "失败判据 tilt>75°/base_z<0.15 为规则口径", "minimal_control": "规则原文比对：Part2 规则未定义摔倒阈值，属自拟；需主办方确认", "status": "NOT_RUN"},
    {"claim": "V2 判定依赖的 foot_tags/ground_feet 分类正确", "minimal_control": "审 run_part2_judged_eval.py 的接触分类源码", "status": "NOT_RUN"},
    {"claim": "Part1 八障碍 judge 规则忠实", "minimal_control": "审 comp_part1_judge.py + comp_part1_geom_tags.py（材料未提供）", "status": "NOT_RUN"}
  ],
  "ambiguities": [
    "轮腿形态与轮关节力矩：规则力矩表只列大腿/髋≤25、小腿≤60 N·m，未覆盖 wheel joint（±20 N·m）；'仿生足式机器人'赛事是否允许 4 主动轮构型需主办方书面确认，否则 Part2 全部分数有被整体否决的风险。",
    "Part2 成功是否要求终态稳定（v5 的 hold 0.2s+0.1s）与楼梯是否必须下行回地面：规则只写'越过/通过'，v5 的终态语义是自拟加严，可能压低正式得分，也可能与现场裁判口径不一致。",
    "'每种障碍至多 4 次挑战'是否允许 4 次中选不同难度（当前诊断按可以落地：40/30/20/10 各一次）；以及诊断工具的 unlimited-attempt total_score 是否只能作内部参考。",
    "自定义隔离地图 + 无限地板 + 自拟 lane_half_width=0.7 是否满足'必须与提供地图中的障碍同一种类'；评分车道本身是规则没有的概念。",
    "梅花桩几何口径：规则'首块与平台距离 100/400mm、同排间距 400mm'，官方场按 100mm 首距落地，自定义 part2_plum_eval_scene.xml 首距为 200mm、仅 6 桩——训练/评测场与官方几何不一致，需确认以哪个为准。"
  ],
  "unresolved_fatals": [
    "FATAL-1：权威 judge v5 零标定、零对照实验——全部 A 类成功条件对 v5 为 NOT_RUN（OVERCLAIMED），任何 v5 产生的 success 目前无独立证据支撑。",
    "FATAL-2：v5 与 Part2JudgeV2 对同一规则条件语义实质漂移，且唯一存档评测产物由非权威 V2 生成——'规则忠实性'对两套 judge 至多一套成立，且无法判定是哪一套。"
  ]
}
```

**最可能让队伍在正式比赛丢分的 3 个 judge 问题：**

1. **轮腿构型合规性未被任何材料覆盖。** 所有 Part2 判分都建立在 blackW（4 个主动轮、±20 N·m 轮电机）之上，而规则力矩表与“足式”定义均未授权轮关节。如果现场裁判按“足式机器人”字面口径执行，judge 再精确也是零分——这是比分差大得多的系统性风险，应最优先拿到主办方书面确认。

2. **v5 的自拟终态阈值会与现场裁判口径错位。** hold 0.3s、楼梯必须下行回地面、沟壑允许轮下沉 10.3cm、高墙 climb_z_min 接近站立高度——这些在规则原文里都不存在。本地按 v5 训练/选拔出的“能过”策略，到现场可能被判不过（或反向：本地判不过、现场能过，浪费 4 次尝试预算）。且 v5 从未与任何人工判罚对过标。

3. **成功谓词是“高度带”而非“接触”，存在 wheelie/悬轮骗分面。** platform/slope 只验四轮 z 高度与基座 x 范围；如果这套 judge（或其近似版）进入训练 termination/reward，策略很可能学出“上台边抬前轮保持 0.3 秒”这类在规则意图下不成立的成功路径，正式比赛一上裁判的接触判据即翻车。改成“高度带 AND 轮心投影在支撑面内”或直接用接触几何是一行级修复，应在冻结前完成。
