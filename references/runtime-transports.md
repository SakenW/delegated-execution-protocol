# 运行时 Transport

只在派发 worker、升级后探测能力或声明实际 model/effort 配置时读取本参考。这里描述的是校验方法，不是对任何特定 Codex 版本或安装环境的能力声明。

## 自定义 agent

自定义 agent 位于 `~/.codex/agents/*.toml` 或项目 `.codex/agents/*.toml`。每个 profile 需要 `name`、`description`、`developer_instructions`、`model` 和 `model_reasoning_effort`，并在 `~/.codex/config.toml` 的 `[agents.<name>]` 下注册。

先对当前运行时执行最小探测，再记录 wrapper 实际暴露的字段和 child rollout 的 `turn_context`。若无法证明 child 的 role/model/effort，不能把 task label 当作配置生效的证据；只能报告已验证的实际继承配置。

## 用户自有 Desktop 任务

Desktop task creation 可以设置 model/thinking，follow-up 也可以覆盖它们。只有用户明确要求独立、后台或侧栏可见任务时才使用；声称配置已生效前核验 rollout 元数据。

## 显式 Codex CLI 派发

隔离且需要差异化配置的内部工作可使用支持显式模型和推理级别的 Codex CLI：

```bash
codex exec \
  --model <model> \
  -c 'model_reasoning_effort="<effort>"' \
  --cd <absolute-cwd> \
  --sandbox <read-only-or-workspace-write> \
  --json -
```

通过 stdin 发送紧凑委派包，并保留 JSONL/rollout 证据。该进程不是 collaboration-tree child，应通过其执行会话管理。

## 继承式协作

steerable 只允许 `verified-inherited-collaboration`。仅在存在具体 steering trigger，或所选 profile 已是 Sol/high 且协作生命周期控制具有实质价值时使用 `spawn_agent`。不得根据 prompt 标签声称其他 profile；报告 child profile 前必须读取当前 rollout 的 `turn_context`。

Codex 升级、配置变化、模型变化或协作功能变化后，运行一个最小 child probe，并检查 child rollout `turn_context`，再更新能力状态。
