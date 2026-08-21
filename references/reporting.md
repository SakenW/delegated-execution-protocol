# 汇报与委派包

只有委派路由、运行时 profile 或生命周期状态对用户重要时才读取本参考。

## 紧凑路由表

存在多个 profile 时，报告 task、实际 model/effort、transport 和 steering trigger。若所有 child 都继承 Sol/high，不得称为差异化路由。

## 中文措辞

原生 steerable 协作：

```text
已成功指派 2 个协作任务，分别负责 A、B；A 请求 gpt-5.6-terra / medium，B 请求 gpt-5.6-sol / high，本轮保留 follow-up/interrupt 是因为需要动态纠偏。实际配置以运行时元数据为准。
```

差异化 isolated worker：

```text
已成功指派 2 个隔离任务：A 使用 gpt-5.6-terra / low，B 使用 gpt-5.6-luna / medium；两项均通过 rollout 元数据验证实际配置。
```

Stage 0 拒绝：

```text
该任务留在主对话执行：工作量不足以抵消独立 worker 的冷启动成本，也不需要独立证据或隔离。
```

## 紧凑委派包

```text
Task: <单一目标>
Context: <已验证事实与相关路径>
Ownership: <may edit / must not edit>
Profile: <agent, model/effort, transport, required evidence>
Constraints: <context mode, commands, safety boundary>
Output: <changed files, validation, evidence, residual risk>
Outcome: <accepted | escalate-one-tier | main-reclaim>
Prior profile: <none or previous profile>
Escalation trigger: <objective failure, evidence gap, risk/scope/contract change, or none>
Observed verification: <command/result or explicit unverified gap>
```

不要粘贴完整规则文件、Skill 正文、Brain 页面或主对话推理。
