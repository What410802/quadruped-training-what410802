```json
{
  "verdict": "FAIL",
  "decision": "REJECT",
  "checklist": [
    {
      "id": "1",
      "item": "SCOREBOARD 每行 policy_id/总分/分项能否从 summary.json 精确重算（抽 3 行）",
      "verdict": "PASS",
      "evidence": [
        "comp/eval/flat-ft-2500-part2-official-diag/summary.json: part2 六类 best_score 全 0、total 0、grand_total 0 → SCOREBOARD.md 行 `flat-ft-2500-part2-official-diag` Part1=0/Part2=0/总=0，一致",
        "summary.json part1 8 障碍全部 failure_reason=not_run、score=0 → Part1=0，一致",
        "SCOREBOARD.json 与 SCOREBOARD.md 逐行一致（均为 diagnostic、0 分）",
        "注意：其余 6 行引用的 summary.json（part1-diag-v2、course-diag 等）未随材料提供，本审计只能核对 1 行；该行精确重算通过"
      ],
      "fix": "补交其余 6 个 eval 目录的三件套以便全量核对；当前均为 0 分 diagnostic 行，风险低"
    },
    {
      "id": "2",
      "item": "每个 success 是否有对应 trial，seed/起点/attempt 与 manifest 一致（抽 3 条）",
      "verdict": "PASS",
      "evidence": [
        "trials.jsonl 共 24 条（6 类 × 4 次），judge.status 全部 fail、success 全部 false，score 全 0 —— 与 summary.json 的 best_success_value=null/best_score=0 一致；无 success 可核对（无可捏造的成功）",
        "manifest.json protocol.seeds=[]、seed_control='none（runner 未设种子/扰动）'；trials.jsonl 全部 seed:null —— 一致（诚实标注，而非假装跑过种子）",
        "attempt 编号 1–4 连续、entry_seq 1–24 无跳号；起点与 manifest 'parametric level starts' 一致",
        "小瑕疵：trench attempt4（a4-r24）重复 30cm 档而非覆盖新档位（a1 也是 30cm），同 base 终态 [2.475,0.055,0.257] 与 a1 完全相同 —— 判定为重复同一确定性 rollout，不是独立第 4 次"
      ],
      "fix": "trench 第 4 次尝试应使用不同档位或独立初态；确定性重复不能算独立尝试"
    },
    {
      "id": "3",
      "item": "只报最好一次/只报成功种子/漏记失败/训练场冒称正式场/judge 混算/summary 手改",
      "verdict": "FAIL",
      "evidence": [
        "bc-policy-report.md §0/§6.2 与 comp_bc_v5/manifest.json 报告 score_best_case=750、逐类 attempts_4 '4/4'，但全部出自训练仓 judge v5（eval_blackw_part2.py），没有任何一条进入 comp/eval 三件套；SCOREBOARD 无 comp_bc_v5 行，RUN_LEDGER 无对应 run —— 审计链路完全绕开",
        "manifest.json 'attempts_4': {'high_platform':'4/4','high_wall':'3/4',...} 但 bc-policy-report §6.3 写 '高墙 40cm @sched 0.8→0.3 | 1/4'、'高台 40cm @vx0.9 | 3/4' —— 同一权重同一档位的通过率在两处矛盾，4/4 只在选定命令下成立（cherry-picked command profile）",
        "comp_bc_v5/manifest.json evaluation.evidence 指向训练仓 prep.d/results/blackw_official/final_profile/*.json，未入库 comp/eval，无法独立复核",
        "comp/eval 本身无手改迹象：summary 与 trials/manifest 三方一致"
      ],
      "fix": "comp_bc_v5 的所有 judge v5 结果按协议导入 comp/eval 三件套（manifest 带 judge v5 hash），由 comp_score.py 重算；4/4 声明须附逐 attempt 原始 JSON+命令序列"
    },
    {
      "id": "4",
      "item": "结论措辞（'比赛可用/期望743/能拿750'）是否被证据支持",
      "verdict": "FAIL",
      "evidence": [
        "OVERCLAIMED：bc-policy-report §0 '比赛可用策略（每障碍单独 4 次挑战机会）'、'期望 ≈743/1300' 仅有 judge v5 数字支撑；而部署栈原始证据 prep.d/results/ppo_st30/deploy_smoke/comp_bc_v5.json 显示 levels_passed=5/20：high_platform_40cm=timeout（judge 声称 4/4）、slope_20/35deg=fell:tilt≈78（judge 声称 4/4 稳定）、stairs 全 4 档 fail（judge 声称 20cm 2/4）、trench_10/20cm=wheel_in_slot（judge 声称 4/4）—— 按部署栈逐档最好成绩重算 ≈300/1300（platform 30cm 100 + wall 40cm 200），与 750 相差 450 分，报告未披露未解释",
        "数字自相矛盾：§0 '期望 ≈743' vs §6.2 '期望 ≈706' vs manifest 'expected_score_with_4_attempts': 743；三处两个值，均无计算式",
        "高墙通过率三处三个值：§6.2 '3/4'、§6.3 '1/4'、§0 '3/4'",
        "report §0 已声明旧口径（8/8、16/16、<1%）作废，但 §0/§6 仍用自拟的 '期望分' 指标，与 acceptance-eval-protocol.md '不设固定次数门槛、逐 case 报告' 冲突",
        "报告确实诚实披露：audit_status='REVIEW_UNAVAILABLE…executor evidence only'、转向 FAIL、wall40/楼梯20 '最脆弱' —— 这些披露值得肯定，但不改变核心 750/743 数字超出证据的事实"
      ],
      "fix": "把 750/743 全部降级为 'judge v5 executor 证据，未审计'；必须并入 deploy_smoke 5/20 差异的逐 case 解释后才能写 '可用/期望分'"
    },
    {
      "id": "5",
      "item": "证据链完整性：manifest commit/sha256/uv.lock；eval 产物覆盖当前候选",
      "verdict": "FAIL",
      "evidence": [
        "按规则：SCOREBOARD/STATUS/报告引用的当前候选 comp_bc_v5 在 comp/eval 下没有任何 {manifest.json,trials.jsonl,summary.json} 三件套 → 直接 FAIL",
        "comp_bc_v5/manifest.json：有 policy.pt/checkpoint.pt sha256，但无训练仓 commit、无评测代码仓 commit、无 uv.lock/依赖版本；judge v5 版本字符串 'v5-wheel-terminal-bands-2026-10-25' 无 file_hashes，judge 源码未入 HASHES.json",
        "comp/eval/flat-ft-2500-part2-official-diag/manifest.json：training commit='unknown'、task dirty=true、control='not-used' —— 三仓证据链残缺（自己已诚实标注）",
        "两套 judge 并存且版本不同：comp/eval 用 comp_judge_v2（part2 judge sha 733aa34f…），bc-policy 用 judge v5（不同判据：终态谓词/轮底带 vs 事件判据）， trench 计分口径不同（v2 参数化档 vs v5 官方几何 20cm=150），存在 judge 版本混算风险",
        "judge v5 的 G1 审计记录为 REVIEW_UNAVAILABLE（manifest.audit_status、comp/audits/2026-10-25-judge-v5-G1-REVIEW_UNAVAILABLE.md）"
      ],
      "fix": "为 comp_bc_v5 生成 comp/eval 三件套（含 judge v5 file sha256、训练仓 commit、uv.lock）；在 HASHES.json 登记 judge v5；冻结前不得引用其分数"
    },
    {
      "id": "6",
      "item": "泛化覆盖与最终风险：场景/种子/起点覆盖；固定初态风险是否被措辞覆盖",
      "verdict": "FAIL",
      "evidence": [
        "judge v5 评测覆盖：20 关 × 单一固定起点 + 单一推荐命令（±0.1m 横向抖动）× 4 次；无种子记录、无初态分布采样 —— 远低于 acceptance-eval-protocol.md §2 要求（正态初态覆盖集 + 指令包络 [-1.5,1.5] 含倒车/转向 + held-out）",
        "acceptance-eval-protocol.md §6 自认：覆盖集采样器/held-out/部署对拍 '工具改造未实施' —— 即当前验收口径下候选的通过证据为零，全部数字是旧口径",
        "部署栈证据暴露严重泛化缺口：slope_20deg 在部署栈即摔倒（judge 声称 4/4 '稳定'）、stairs_10cm（最低档）都 timeout、plum max_z=0.016（从未站立）、trench_10/20cm last_base z=-1118/-1284（仿真数值爆炸）—— 部署栈与 judge 的差异逐 case 解释（acceptance §3 '部署一致'）完全未做",
        "comp/eval flat-ft-2500-part2-official-diag：0/24，无种子、每档 1 次有效（trench a4 重复），仅 diagnostic"
      ],
      "fix": "按 acceptance-eval-protocol 实现覆盖集评测并跑 held-out；先做 judge v5 ↔ rl_sar 部署栈逐档对拍并解释全部 15 个失败 case，再谈泛化"
    }
  ],
  "top_rejection_risks": [
    {
      "reason": "当前候选 comp_bc_v5 的所有分数（750/1300、逐类 4/4、期望 743）完全没有 comp/eval 三件套支撑，judge v5 未过 G1 审计（REVIEW_UNAVAILABLE），分数不可引用",
      "severity": "FATAL",
      "evidence": [
        "comp/SCOREBOARD.md 无 comp_bc_v5 行",
        "comp_bc_v5/manifest.json: audit_status='REVIEW_UNAVAILABLE (Codex bridge 401…)'",
        "bc-policy-report.md §2 '本文数字仅为 executor 证据…未作 Type-B 声明'"
      ],
      "fix_type": "process：按协议导入 comp/eval 并重跑 G1 审计",
      "resolved": false
    },
    {
      "reason": "部署栈原始证据与 judge 分数严重矛盾且未被披露：deploy_smoke 5/20（折算 ≈300/1300），platform 40/slope 20-35/stairs 全档/trench 10-20 全部失败，与 750 宣称相差 450 分",
      "severity": "FATAL",
      "evidence": [
        "prep.d/results/ppo_st30/deploy_smoke/comp_bc_v5.json: levels_passed=5, levels_failed=15；slope_20deg reason='fell:tilt=77.8'；high_platform_40cm reason='timeout'；stairs_10/15/20/30cm 全 timeout",
        "bc-policy-report.md §0/§6.4 只披露 '前进段 PASS；转向 FAIL'，未披露 20 档逐档结果"
      ],
      "fix_type": "evidence：逐 case 对拍解释（物理/时序/限幅/观测 prefill），修正报告数字",
      "resolved": false
    },
    {
      "reason": "部署栈证据内部存在仿真数值爆炸与'从未站立'异常，部署 smoke 本身有效性存疑，既不能证明也不能证伪部署能力",
      "severity": "MAJOR",
      "evidence": [
        "deploy_smoke/comp_bc_v5.json: trench_10cm last_base=[16.8,-0.869,-1118.482]、trench_20cm last_base z=-1284.019",
        "plum_1bool: max_z=0.016、reason='fell:tilt=180'（初始即倒）"
      ],
      "fix_type": "control：官方权重过同一 deploy smoke 做栈有效性对照",
      "resolved": false
    },
    {
      "reason": "关键宣称数字内部矛盾：期望分 743 vs 706；高墙 3/4 vs 1/4；高台 manifest 4/4 vs §6.3 3/4（不同命令下 cherry-pick）",
      "severity": "MAJOR",
      "evidence": [
        "bc-policy-report.md §0 '期望 ≈743/1300' vs §6.2 '期望 ≈706'",
        "§6.2 高墙 '3/4' vs §6.3 '高墙 40cm @sched 0.8→0.3 | 1/4'",
        "comp_bc_v5/manifest.json 'high_platform.attempts_4':'4/4' vs §6.3 '高台 40cm @vx0.9 | 3/4'"
      ],
      "fix_type": "document：统一口径、给出每个数字的计算式与对应 attempt 原始 JSON",
      "resolved": false
    },
    {
      "reason": "trench a4 与 a1 为同一确定性 rollout 重复计入（同 start/同终态），第 4 次尝试不独立",
      "severity": "MINOR",
      "evidence": [
        "trials.jsonl: r21 (a1, 30cm) 与 r24 (a4, 30cm) 同 base [2.475,0.055,0.257]、同 tilt 27.63"
      ],
      "fix_type": "runner：每次 attempt 独立 reset/扰动并记录",
      "resolved": false
    }
  ],
  "missing_controls": [
    {
      "claim": "comp_bc_v5 judge v5 得 750/1300（平台40/墙40/坡35/梯20/沟20）",
      "minimal_control": "将 eval_blackw_part2.py 逐档原始 JSON+视频导入 comp/eval 三件套，由 comp_score.py 用同一计分曲线重算 750，并经 Type-B 审计 judge v5",
      "status": "NOT_RUN"
    },
    {
      "claim": "'4 次挑战期望 ≈743/1300、比赛可用'",
      "minimal_control": "用推荐命令 profile 对 6 类 × 推荐档 × 4 attempts × ≥5 个初态种子跑 judge，输出逐 attempt 成败矩阵；同口径跑部署栈 smoke 并解释 15 个失败 case",
      "status": "NOT_RUN"
    },
    {
      "claim": "高台 40cm '4/4'、高墙 '3/4'",
      "minimal_control": "固定推荐命令（vx=0.5 / 0.65→0.35）、记录 seed，重复 ≥10 次出通过率及置信区间（当前 3/4 vs 1/4 vs 4/4 互相矛盾）",
      "status": "NOT_RUN"
    },
    {
      "claim": "deploy smoke 5/20 反映策略部署能力（而非部署栈 bug）",
      "minimal_control": "官方三份 blackW 权重过同一 rl_sar smoke 20 档（栈对照）；若官方权重同样崩（如 plum 从未站立、trench z=-1118），则 5/20 归因于栈而非策略",
      "status": "NOT_RUN"
    },
    {
      "claim": "验收协议（覆盖集/零摔倒/held-out）下候选有效",
      "minimal_control": "实现 acceptance-eval-protocol.md §6 的覆盖集采样器+逐 case JSON，在 eval 集跑零摔倒+可行子集全过",
      "status": "NOT_RUN"
    }
  ],
  "unresolved_fatals": [
    "comp_bc_v5 全部分数无 comp/eval 三件套支撑、judge v5 未审计（REVIEW_UNAVAILABLE），750/743/4-of-4 不可引用",
    "部署栈证据 5/20（≈300/1300 折算）与 750 宣称直接矛盾且未披露、未解释；slope 20° 即摔倒、stairs 最低档 timeout 与 '稳定' 宣称冲突"
  ],
  "score_recompute": [
    {
      "row": "SCOREBOARD flat-ft-2500-part2-official-diag",
      "recomputed": "summary.json part1.total=0 + part2.total=0 → grand_total=0；SCOREBOARD 行 0/0/0",
      "match": true
    },
    {
      "row": "trials.jsonl (24 条) vs summary.json",
      "recomputed": "24 fail / score 0；六类各 4 attempts → summary attempts_used=4×6、best_score 全 0",
      "match": true
    },
    {
      "row": "comp_bc_v5 manifest score_best_case=750（算术）",
      "recomputed": "200+200+100+100+150+0=750，算术自洽；但底层 attempts_4 声明与报告 §6.3 矛盾（墙 3/4 vs 1/4、台 4/4 vs 3/4@vx0.9）且无 comp/eval 原始 JSON 可复核 → 数字算术 match、证据链 mismatch",
      "match": false
    },
    {
      "row": "deploy_smoke comp_bc_v5 折算分",
      "recomputed": "通过档最好成绩：platform 30cm=100、wall 40cm=200、stairs 0、slope 0、trench 0、plum 0 → 300/1300，5/20 档；与 manifest 750/1300、attempts_4 声明严重不符",
      "match": false
    }
  ]
}
```

**最可能丢分的 3 条路径（按严重度）**

1. **部署栈与 judge 脱节（最致命）**：750 分建立在训练仓 judge v5（0.002s 物理、固定起点、单一命令）上，而 rl_sar 部署栈同一权重只有 5/20 档（折算 ≈300/1300），且出现仿真数值爆炸（trench z≈-1200）与"从未站立"（plum max_z=0.016）。若现场按部署链路验收，实际得分最可能在 0–300 区间；且 smoke 本身有效性未做官方权重对照，连"策略不行"还是"栈不行"都无法裁决。

2. **高价值档位是 cherry-picked 脆弱通过**：高墙 40cm 通过率三处口径 3/4 / 1/4，斜坡 35° 在部署栈直接摔倒（judge 声称 4/4 "稳定"），楼梯 20cm 2/4 且部署栈连 10cm 都 timeout。"期望 743"在 4 次挑战规则下没有任何一次可复现的统计支撑，比赛日单个命令偏移或初态抖动就可能让 200+150+100 的档位集体归零。

3. **验收口径真空 + 审计链断裂**：现行验收协议（覆盖集初态、指令包络、held-out、部署对拍）工具"未实施"，旧指标作废但新证据为零；judge v5 无 file hash、未入 HASHES.json、G1 未冻结，comp_bc_v5 没有 comp/eval 三件套。任何"能拿 X 分"的对外引用都过不了 G4，且一旦 judge 判据被质疑（此前已修过砂砾坑 L 形、限高杆 under-bar 等语义 bug），750 分中没有任何一条可回放审计的 attempt 记录来自保。
