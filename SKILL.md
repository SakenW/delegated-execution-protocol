---
name: delegated-execution-protocol
description: 用于可能受益于有界委派、并行执行、独立审查或显式 agent 生命周期管理的非平凡 plan-then-execute 工作；在模型路由前先执行冷启动价值门。
---

# 委派执行协议

## 核心契约

主对话负责规划、集成、最终验证、分歧裁决和汇报。只有 worker 提供的独立证据、隔离价值或关键路径吞吐量明确高于冷启动成本时才委派。把 worker 输出视为证据，不视为权威结论。

## 主对话配置

推荐主对话使用 `gpt-5.6-sol` / high。xhigh 只用于有界、高影响且高歧义的规划审计。不要路由 `max`。

## Stage 0：委派价值门

选择模型前先按科斯式交易成本执行价值门：委派净收益 = 独立证据、专业分工、隔离或关键路径收益 - 冷启动、上下文打包、沟通、等待、审查与集成成本。只有净收益明确为正且至少满足一项时才委派：

- 需要独立证据；high/critical 风险通常使独立只读 reviewer 候选成立，但不自动证明应把执行交给 worker。
- batch 至少包含 10 个同质项目，足以摊薄一个 worker 的启动成本。
- medium/large 工作具有有用或关键路径并行价值。
- medium/large 跨模块工作可形成有界所有权单元。
- large 有界工作能够明确摊薄启动成本。
- 具体 steering trigger 需要实时 worker 会话。

micro/small 工作在独立证据仅为 useful 或不需要时留在主对话。仅有 `parallel-value=useful` 永远不足以证明值得启动 worker；单文件检查、单命令验证、措辞修改、确定性修复和仪式化 reviewer 均属此类。

风险和复杂度本身不是执行委派的充分条件。实现工作仍需专业分工、所有权隔离、关键路径吞吐量或能摊薄成本的工作量；否则由主对话实现，再按“完成后的对抗审查门”判断是否需要独立 reviewer。

即使 Stage 0 拒绝委派，也要在主对话中保持 review -> acceptance -> write 的质量顺序。

## 完成后的对抗审查门

相对复杂不等于自动多 Agent。完成实现与聚焦验证后，若满足以下任一条件，把独立只读审查作为新的候选再次运行 Stage 0：

- high/critical 风险，或安全、权限、迁移、计费、生产、回滚等合同敏感边界。
- medium/large 工作同时具有 high 歧义、cross-module 范围或明确冲突证据。
- 用户明确要求独立证据或对抗式审查。

审查者主动攻击主方案的假设、遗漏、失败路径和证据强度，不重复实现过程。主对话裁决 findings、决定是否修复并完成最终验收。低风险、低歧义、边界清楚且验证确定的任务留在主对话，不启动仪式化 reviewer。

## 路由记录

以下字段由当前证据推断，不得转化为用户问卷。只有缺失信息会实质改变委派决定、写权限、安全边界或验收标准时，才询问一个高信息量问题；其余字段采用保守默认并继续。

```text
Task:
Kind: scan | documentation | implementation | review | planning-audit | arbitration
Writes: none | bounded | broad
Scope: small | medium | cross-module
Task size: micro | small | medium | large
Risk: low | medium | high | critical
Ambiguity: low | medium | high
Independent evidence: none | useful | required
Parallel value: none | useful | critical-path
Priority: economy | balanced | quality
Workload: one-off | batch
Batch size:
Verification: weak | normal | strong
Coordination: isolated | steerable
Steering trigger: none | partial-results | user-steering | shared-session-state | risk-cancellation
Requested workers:
Sharding evidence: none | measured-throughput | critical-path
Transport preference: auto | native-verified | user-owned-desktop-task | explicit-cli
Selected profile / transport:
Assignment evidence:
```

只对通过 Stage 0 的真实委派候选运行确定性 selector：

```bash
python3 <skill-dir>/scripts/select_agent_profile.py \
  --kind implementation --writes bounded --scope medium \
  --task-size medium --risk low --ambiguity low \
  --independent-evidence none --parallel-value useful \
  --priority balanced --workload one-off --batch-size 1 \
  --verification strong --coordination isolated \
  --steering-trigger none --requested-workers 1 \
  --sharding-evidence none --transport-preference auto
```

遵守 `delegate=false`。当 `transport_enforced=true` 时必须使用返回的 transport，不得为了方便替换成 selector 未返回的 transport。

## 智能配置选择

| Profile | 工作 | Model / effort |
|---|---|---|
| `delegated_batch_explorer` | 确定性、低风险、只读 batch | `gpt-5.6-luna` / low |
| `delegated_batch_worker` | 强验证保护的确定性有界 batch 写入 | `gpt-5.6-luna` / medium |
| `delegated_explorer` | 聚焦的只读证据收集 | `gpt-5.6-terra` / low |
| `delegated_researcher` | 多文件或中歧义研究 | `gpt-5.6-terra` / medium |
| `delegated_deep_researcher` | 高歧义、有界风险研究 | `gpt-5.6-terra` / high |
| `delegated_worker` | 普通有界实现或文档工作 | `gpt-5.6-terra` / medium |
| `delegated_complex_worker` | 强验证保护的高歧义有界工作 | `gpt-5.6-terra` / high |
| `delegated_senior_worker` | 跨模块或高风险实现 | `gpt-5.6-sol` / high |
| `delegated_reviewer` | 正确性、安全、迁移、计费或生产审查 | `gpt-5.6-sol` / high |
| `delegated_planning_auditor` | 高影响且高歧义的规划审计或仲裁 | `gpt-5.6-sol` / xhigh |

Luna 仅允许 batch、isolated、低风险、低歧义且不需要审查判断的工作。Luna 只读要求 normal/strong verification；Luna 写入还必须是有界、非跨模块并具备 strong verification。禁止用 Luna high/xhigh 补偿风险。

Terra/high 仅允许 isolated、低/中风险、高歧义且证据可验证的研究，或 strong verification 保护的有界非跨模块实现。high/critical 风险、weak verification、broad/cross-module 写入、公开合同、quality 优先和审查判断使用 Sol/high。

review/planning-audit/arbitration 与写入组合时，selector 顶层返回 `delegate=false`、`dispatchable=false` 和 `split_required=true`，不得直接派发顶层结果。按只读判断、主线程接受、再有界执行拆分；每个可委派 step 都返回 `delegate=true`，写入 step 还必须返回 `requires_main_acceptance=true`。xhigh 只用于规划影响和歧义都为 high 的情况。

## 打包与 worker 预算

- one-off 默认最多 2 个并发 worker。
- batch 默认 1 个 worker；只有显式 `Sharding evidence` 为 `measured-throughput` 或 `critical-path` 时才允许最多 2 个。
- 任何超过 `max_workers` 的请求都必须先打包；不得通过分片证据突破 2-worker 上限。
- 把仓库、profile、权限、证据来源和验证路径相同的工作打包。
- 不要仅为了减少主线程注意力而委派。

selector 返回 `max_workers`、`bundle_required`、`sharding_evidence` 和 `sharding_justified`。重新分类或打包，不得忽略这些输出。

## 派发 transport 门

默认使用 isolated。只有指令依赖部分结果、预期用户实时纠偏、共享实时会话状态或基于风险需要立即取消时才使用 steerable；并行执行和状态可见性不是 steering trigger。当前原生 transport 同时支持 profile override 与 follow-up/interrupt 生命周期，steerable 不再等同于继承 Sol/high。

isolated 使用 `Transport preference`：

- `auto`：按当前已验证能力选择；当前协作面支持原生 `agent_type`、`model` 和 `reasoning_effort` 覆盖，使用 `native-named-agent`。优先通过注册的 `agent_type` 绑定完整 profile；只有使用 `default` agent 且确有需要时才显式覆盖当前 surface 允许的 model/effort。
- `native-verified`：仅在当前工具 schema 接受 profile/model/effort，且派发证据能证明请求已绑定时使用原生 named-agent。
- `user-owned-desktop-task`：仅在用户明确要求独立、后台或侧栏任务时使用。
- `explicit-cli`：使用显式 Codex CLI 完成隔离且差异化的内部工作。

steerable 的 `Transport preference` 必须为 `auto`，并使用 selector 选择的 `native-named-agent` profile；派发包必须写出具体 steering trigger。派发或核验运行时配置时才读取 [references/runtime-transports.md](references/runtime-transports.md)。任务标签不是 assignment evidence；工具接受 override 只能证明请求已绑定，声称实际 profile 前仍需运行时元数据。

## 上下文与所有权

- 使用紧凑委派包，不要复制 `AGENTS.md`、本 Skill、Brain 页面或已确定的推理。
- 包含目标、已验证事实、相关路径、may-edit/must-not-edit、安全边界、验证和输出契约。
- 可行时控制在约 1,500 字符，只增加任务关键上下文。
- `fork_turns` 优先使用 `none`；确需近期对话时用较小正数，只有完整历史明显更安全时才用 `all`。旧 runtime 若暴露 `fork_context`，不得同时发送两种控制字段。
- `workspace-write` 是仓库级能力，不是机械所有权隔离；边界不可违反时审查完整 diff 或使用 worktree。

## 调度与生命周期

只并发执行读写范围不相交的工作，依赖链保持顺序。使用所选 transport 暴露的生命周期动作。`interrupt_agent` 会停止过时的协作工作，但不代表 closure；显式 CLI worker 通过执行会话跟踪。

## 主线程审查

主对话检查证据、所有权、完整 diff、测试和升级触发条件。风险扩大、验证变弱、合同跨模块、证据冲突或信心不足时，升级模型或把工作收回主对话。

## 派发汇报规则

只有委派状态、阻塞、安全边界、长任务状态或差异化路由对用户重要时才发送过程说明；否则静默执行并在最终交付中汇总。需要汇报派发时，先说明工作留在主对话或实际已指派的任务数。只有 runtime 证据确认后才报告实际 model/effort；模型覆盖不可用不等于任务无法指派。

只有差异化路由或生命周期状态对用户重要时才读取 [references/reporting.md](references/reporting.md)。

## 主验证命令

该命令会运行 selector 行为测试、结构与配置安全检查，并要求 Skill 源目录不存在 Python cache，且验证过程不得生成新缓存：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/validate_protocol.py
```
