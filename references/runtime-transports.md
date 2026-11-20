# 运行时派发与配置绑定

verified_at: 2026-11-19
verification_surface: CLI 0.169.0 read-only smoke requests verified GPT-6.2 Sol/medium and GPT-6.2 Astra/xhigh with rollout metadata. The Terra app-server Calculator run passed on CLI 0.166.0 on 2026-10-30. On 2026-11-19 its helper sources were restored by SHA256 and passed the client regression suite.

## 配置与原生能力

Codex 可从 ~/.codex/agents 或项目 .codex/agents 读取 standalone custom agent。平台必需字段为 name、description、developer_instructions；model/effort 等可继承。本协议额外要求显式 model、model_reasoning_effort、sandbox_mode。这里的 sandbox_mode 是派发所需权限约束，并由显式 CLI 使用；原生 custom agent 不能通过该字段覆盖父会话权限。

原生派发时，按当前工具定义选择不继承完整历史的参数和值，只传完成任务所需的上下文。工具没有提供这种方式时，在派发前报告限制。完整历史 fork 不允许覆盖时，不要传 override。模型与角色清单以当前工具定义为准，不在手册保存会过期的允许模型列表。

仅在实际有效权限与配置匹配时，按 agent_type 选择角色。[官方子 agent 权限说明](https://learn.chatgpt.com/docs/agent-configuration/subagents#approvals-and-sandbox-controls)明确：原生子 agent 继承父会话 sandbox 和审批设置，custom agent 文件不能替换它们。先在父会话选用任务所需权限，再派发并核对实际值；更新 CLI 或重新加载角色不会自动解决父子权限不匹配。2026-09-05 的只读角色继承 workspace-write 正符合该机制，不能把声明当成生效权限。请求被接受是 assignment evidence，不是实际执行证明；检查 child rollout 的 turn_context / 有效权限与模型元数据后，才能报告实际 model/effort。模型名写在 prompt/task name 中不构成绑定。

## 显式 Codex CLI（explicit-codex-cli）

当前协作面缺少所需模型、角色或可核验绑定时，isolated 内部工作可通过当前已验证 CLI 执行。使用 selector 返回的 config_file 读取并传入角色 model、effort、sandbox_mode 和 developer_instructions；若角色还配置 provider/工具/权限项，也须按当前 CLI 支持的配置机制完整应用，不能只传 --model 就冒称完整角色已绑定。无法安全传递所需配置时由主线程收回。

显式 CLI 用 --sandbox 设置所需权限，启动后仍核对 turn_context 的实际权限；不得通过 CLI 绕过父任务的只读授权或平台限制。用结构化 argv / stdin 传入任务和多行指令，不进行危险的 shell 字符串插值；CLI 不是用户自有侧栏任务。保留 JSONL/rollout 证据、退出状态与执行会话，必要时由主线程终止过时进程。

## 派发前检查（正式任务之前）

先核对当前工具定义、实际 CLI 路径/版本和所选 CODEX_HOME；Desktop 原生角色、CLI 登录与模型目录分别取证，不能互相代替。目录列出模型只证明静态支持，不能证明当前账户/provider 能调用。selector 的 `preflight_required` 不是派发许可。

CLI 先运行以下静态检查；未执行探针时返回 `probe_required`、`dispatchable=false`、退出码 2，这不是模型失败。按本次授权做一次最小探针（会消耗少量额度），证据目录必须是工作盘上尚不存在的任务目录：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 <skill-dir>/scripts/preflight_dispatch.py \
  --role delegated_researcher --codex-home <current-codex-home>
PYTHONDONTWRITEBYTECODE=1 python3 <skill-dir>/scripts/preflight_dispatch.py \
  --role delegated_researcher --codex-home <current-codex-home> \
  --probe --output-dir <work-volume>/<task>/researcher-probe --timeout 60
```

该脚本检查精确角色配置和 CLI 必需参数，不猜测模型别名或 provider；只接受能完整应用的角色字段，额外 provider/工具/权限配置无法传递时停止，不部分套用。沿用所选 CODEX_HOME 的登录和全局配置，角色显式 provider 原样传入。不要把 `--profile` 当成 standalone agent TOML 加载器。正式任务须沿用检查过的二进制、CODEX_HOME、绑定与配置来源；项目/profile/环境覆盖也必须核对，不能把探针目录的配置冒充项目运行配置。

探针只有在退出码为 0、结构化 turn 完成、返回约定标记且 rollout `turn_context` 的 model/effort/权限匹配、显式 provider 与 session_meta 一致时才返回 `verified`/`dispatchable=true`。缺元数据或权限不匹配仍阻止正式派发。模型、provider、身份、CLI 版本、角色/全局/项目配置或权限变化后重新检查；同一批精确绑定共用本批结果，不为每个任务重复探针，不跨会话复用历史成功。脚本指纹只绑定本机配置与身份文件，不证明服务端状态长期不变。正式请求仍可能失败，须按相同分类处理，不自动重试或切换。

原生探针使用当前具名角色且不覆盖模型/provider，做一个有界读取。从实际 child rollout 核对 model/effort/有效权限。若角色或全局配置显式指定 provider，还须核对 session_meta.model_provider，角色配置优先；观测值缺失或不同都视为不匹配。父任务 workspace-write 下子任务同样可写时，不得把 read-only 角色判为匹配。原生不匹配时，`native-verified` 和需要中途接收指令的任务停止派发。`auto` 下的独立任务保持原角色绑定，电脑操作检查显式 app-server，其他任务检查显式 CLI。

失败分类：`cli_argument_unsupported` 只用于参数解析拒绝；`model_unavailable` 用于服务端拒绝模型；`effort_unavailable` 用于推理档位被拒绝；`authentication_failed`、`network_failed`、`rate_limited`、`timeout`、`configuration_failed`、`runtime_binding_unverified` 和 `execution_failed` 分别保留边界。输出简短结论及证据目录，完整 JSONL/stderr 留在工作盘；未知错误不概括为“CLI 不支持配置模型”。不自动换模型、provider 或角色，不扫描凭据内容到输出。原生/CLI 固定运行状态仍由应用原生管理，不在运行中迁移数据库或登录文件。

## 原生生命周期

native-named-agent 的 steerable 工作仅在存在具体 partial-results/user-steering/shared-session-state/risk-cancellation 需求时使用，并需核对当前角色绑定及 follow-up/interrupt 生命周期。缺少这些能力时不假称可实时纠偏；主线程收回或重新拆分。

sandbox_mode 描述本地执行的文件系统边界，不代表 MCP/API 获得外部写入授权。只读任务不调用写入型工具，仍遵守项目和平台的外部操作限制。只读角色保持只读，有界写入者不越过所有权。相关 agent 进入终态且结果处理完毕后，主线程复查最终 diff 与验证，再执行已授权提交。interrupt_agent 停止工作，不代表 closure，也不虚构不存在的关闭操作。

## 用户自有 Desktop 任务

只有用户明确要求独立、后台或侧栏可见任务时才使用创建任务工具。确认所选任务工具能保留本次需要的模型/权限边界，再实际创建；不为实现内部委派另建用户任务。




## 电脑操作与应用审批

显式 app-server 电脑任务使用[固定入口](computer-tasks.md)，不临时重写 app-server 客户端、不重复做无工具文字探针。`Computer Use was not approved` 只表示请求没有收到 accept，不能直接归因为安全模型或用户拒绝。文字授权要通过正式 MCP elicitation 回执落到工具层。

固定入口保留具名角色、model/effort/sandbox 核验，仅在本次明确授权覆盖的低风险应用访问请求上返回 accept；其他请求停止交主对话。它不创建永久授权，不替代具体任务的界面验收。2026-10-30 在 CLI 0.166.0 的具名 Terra/medium、workspace-write、Calculator 13+29=42 已有实机证据；当前任务仍按实际工具和应用状态验证。
