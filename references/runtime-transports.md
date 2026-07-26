# 运行时 Transport

verified_at: 2026-07-26
verification_surface: active Codex Desktop `spawn_agent` schema and accepted delegated dispatch

只在派发 worker、升级后探测能力或声明实际 model/effort 配置时读取本参考。

## 自定义 agent

自定义 agent 位于 `~/.codex/agents/*.toml` 或项目 `.codex/agents/*.toml`。每个 profile 需要 `name`、`description`、`developer_instructions`、`model` 和 `model_reasoning_effort`，并在 `~/.codex/config.toml` 的 `[agents.<name>]` 下注册。

当前已验证边界：Desktop 协作 wrapper 暴露 `agent_type`、`model`、`reasoning_effort`、task name、message 和 `fork_turns`。设置 model 或 effort override 时，`fork_turns` 必须为 `none` 或较小正数；完整历史 fork 不接受 override。优先使用已注册的 `delegated_*` agent type 绑定完整 profile；Luna 只能通过固定的 batch agent type 使用。只有 `default` agent 确需覆盖时才传 model/effort，当前可覆盖模型为 `gpt-5.6-sol` 与 `gpt-5.6-terra`。不得把 task name 或 prompt 标签当作 profile 绑定。

原生派发调用被工具接受可作为 assignment evidence；只有 child rollout 的 `turn_context` 等运行时元数据才能证明实际 model/effort。工具 schema、Codex 版本或模型目录变化后重新做最小 probe。

## 用户自有 Desktop 任务

Desktop task creation 可以设置 model/thinking，follow-up 也可以覆盖它们。只有用户明确要求独立、后台或侧栏可见任务时才使用；声称配置已生效前核验 rollout 元数据。

## 显式 Codex CLI 派发（`explicit-codex-cli`）

当前协作面缺少所需模型、推理级别或可验证 override 时，隔离且需要差异化配置的内部工作回退到 Desktop 内置 CLI：

```bash
/Applications/ChatGPT.app/Contents/Resources/codex exec \
  --model <model> \
  -c 'model_reasoning_effort="<effort>"' \
  --cd <absolute-cwd> \
  --sandbox <read-only-or-workspace-write> \
  --json -
```

通过 stdin 发送紧凑委派包，并保留 JSONL/rollout 证据。该进程不是 collaboration-tree child，应通过其执行会话管理。

## 继承式协作

steerable 使用原生 named-agent 的 follow-up/interrupt 生命周期，同时保留 selector 选择的显式 profile override；它仍只在存在具体 steering trigger 时使用。若当前 runtime 不再支持 override，应重新探测并更新 selector，不得静默把所有任务退化为继承的 Sol/high，也不得根据 prompt 标签声称其他 profile。

Codex 升级、配置变化、模型变化或协作功能变化后，运行一个最小 child probe，并检查 child rollout `turn_context`，再更新能力状态。
