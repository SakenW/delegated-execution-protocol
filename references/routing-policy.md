# 委派路由

先完成 SKILL.md 的价值判断，再运行 selector。任务属性决定角色；模型、reasoning、sandbox 和 developer instructions 只由实际 Codex agent TOML 定义，不在本参考复制模型矩阵。

## 紧凑记录

把已有信息组织为以下记录即可；不向用户逐项提问，也不为字段填写制造工作：

```text
Task: 目标与边界
Ownership: may-edit/must-not-edit、只读或有界写入
Delegation value: 独立证据或可并行收益
Acceptance: 验证方式与返回证据
Assignment: 角色、config_file、请求的model/effort/权限/transport、运行时证据
Outcome: accepted / escalate-one-tier / main-reclaim；结果与未验证项
```

CLI 分类参数由主线程按证据推断。`--help` 是参数清单，不复制为常驻问卷。微型/小型任务通常不派发；模糊权限和关键验收不能靠猜测补齐。

## 角色责任

| 角色 | 用途 |
|---|---|
| `delegated_batch_explorer` | 低风险、确定性批量读取 |
| `delegated_batch_worker` | 强验证保护的有界批量修改 |
| `delegated_explorer` | 低风险、低歧义、isolated 且证据可核验的聚焦只读探索 |
| `delegated_researcher` | 多文件/中等歧义研究 |
| `delegated_deep_researcher` | 有界、可验证的高歧义研究 |
| `delegated_standard_reviewer` | 低/中风险、有界普通审查 |
| `delegated_worker` | 普通有界实现 |
| `delegated_computer_worker` | 有界电脑操作，持有同一应用/标签页并回读结果 |
| `delegated_complex_worker` | 强验证保护的有界复杂实现 |
| `delegated_senior_worker` | 高风险/跨模块实现 |
| `delegated_reviewer` | 高风险/合同敏感独立审查 |
| `delegated_planning_auditor` | 同时高影响与高歧义的规划/仲裁 |

配置源是所选 CODEX_HOME 的 config.toml 中注册的 config_file，未注册时读取 agents/<role>.toml。其中 sandbox_mode 表示协议所需权限；原生子 agent 继承父会话权限，须先使父会话满足该约束，角色文件本身不会创建独立沙箱。只有本协议角色要求显式 model/effort/sandbox，以避免意外继承权限；这不是 Codex 平台对所有 custom agent 的要求。生产实现不包含默认模型名表。

当前安装按任务专长分配：Luna 用于清晰可验证的批量处理和聚焦探索，Terra 处理有界电脑操作，Sol 承担工程实现与技术研究，Astra 负责高影响与困难裁决。具体 model/effort 仍以所选角色 TOML 为准。定价依据、推荐初始绑定和验证限制见 [GPT-6 设计依据](model-policy.md)，普通派发无需加载该参考。5.6 不再属于本机默认绑定或自动回退；显式配置其他模型/provider 的能力保留。

## 使用 selector

```bash
python3 <skill-dir>/scripts/select_agent_profile.py \
  --kind review --writes none --scope cross-module \
  --task-size medium --risk high --ambiguity high \
  --independent-evidence required --parallel-value none \
  --verification strong --sensitivity contract-sensitive
```

默认从 CODEX_HOME（未设置时 ~/.codex）读取角色与 model_catalog_json，未指定模型目录时再用 models_cache.json。可用 `--codex-home`、`--catalog` 明确指定来源。它检查精确模型 ID/effort，不按模型代际或 provider 前缀过滤；没有目录、模型、effort 或角色权限证据就失败关闭。

原生调用需要通过 `--native-binding` 传入当前实际观测的角色、model、model_reasoning_effort 与 sandbox_mode JSON，可按角色重复；仅有角色名或 TOML 声明不算生效证据。selector 逐项与所选配置比较。不能把读取的配置直接复制成观测值；它是调用方提供的运行时证据，不是 selector 自行探测，也不证明下一次调用已经执行。配置、工具或父级权限变化后重新核对。

2026-09-05 实测：新原生角色正确使用 Astra/high，但从 workspace-write 父任务派发的 reviewer 仍继承 workspace-write，未落实 TOML 的 read-only。这样的证据必须判为不匹配并改走显式只读 CLI；不伪称原生角色已只读。
- `auto`：当前观测的模型/effort/权限均匹配角色配置时使用 native-named-agent；否则电脑任务走 explicit-codex-app-server，其他任务走 explicit-codex-cli。
- `native-verified`：缺少匹配的当前原生证据就拒绝，不静默替换。
- `explicit-cli`：电脑任务使用显式 app-server 审批入口，其他任务使用显式 CLI。
- `user-owned-desktop-task`：仅在用户明确要求独立、后台或侧栏任务时使用，不能用于内部委派捷径。
- steerable 的 `Transport preference` 必须为 `auto`，且角色须有当前原生绑定；并行执行和状态可见性不是 steering trigger。

实际派发前读 [runtime-transports.md](runtime-transports.md)。若项目/profile 覆盖使本次原生角色不同于 selector 读取的配置，不得宣称相同绑定；先对齐配置来源或由主线程收回。

## 保留的安全与成本策略

- 审查/规划/仲裁与写入混合时，selector 顶层返回 `delegate=false`、`dispatchable=false`、`split_required=true`；先只读判断，由主线程接受后才执行 `requires_main_acceptance=true` 的有界步骤。
- 批量经济角色仅用于 batch_size>=10、低风险/低歧义、isolated、无合同敏感或审查判断的任务；读取至少 normal verification，写入须 bounded、非跨模块、strong verification。当前数字是既有成本护栏，不是模型能力定律，不凑数命中。
- 普通有界审查可选 standard reviewer；高风险、跨模块、合同敏感、quality 或关键证据缺口选高能力角色。weak verification 必须明示缺口，升级模型不能替代验证。
- 配置模型/effort 不可用、目录缺失或账户/provider 拒绝时停止派发，报告原绑定与失败类别，由主线程收回。不得自动换角色、模型、effort 或 provider；另换绑定须有覆盖该改变的用户授权。
- one-off 默认最多 2 个并发 worker；batch 默认 1 个，只有实测吞吐或关键路径证据才到 2 个。遵守 max_workers / bundle_required，不把上限当配额；依赖和重叠写集不并发。
- 服从 selector 的 delegate=false 与强制 transport，不为绕过限制改任务标签。它证明规则选择结果，不证明模型质量、委派净收益或当前账户可调用性；`preflight_required=true` 的路由必须先完成运行时检查。

聚焦探索也可使用 Luna：仅 low 风险、low 歧义、非跨模块、isolated、normal/strong verification、无合同敏感且不含审查判断。小任务先由 Stage 0 拒绝；已通过价值门的 one-off 不需凑成 batch。中风险、跨模块综合、steerable 或证据弱的探索使用 researcher。Luna 写入仍限制为强验证保护的同质 batch；普通或复杂实现由 Sol 角色承担。

执行失败不自动重跑原任务。先区分外部环境/授权缺口与推理失误：补齐前者或由主线程收回；后者才按事实重新分类、选下一角色并交接已有证据。最多升级一次；再失败回主线程。敏感任务可直接进入 Astra，无须为了逐级升级先经过较低档。

## 电脑操作

`--kind computer-use --writes bounded` 表示图形界面的有界操作；导航也会改变应用状态，不能因未写文件就声明 writes=none。优先专用连接器，确需视觉操作时才选择此任务类型。通过价值门后，低/中风险、低/中歧义、正常或强验证的独立任务走 computer worker；高风险、合同敏感、跨模块、弱验证或高歧义仍走 senior worker。质量优先门不变。

同一任务最多一个 worker，不按 batch 扩大并发；仅分工相关的任务需要交接。selector 的 required_capabilities 要求实际电脑工具和目标应用访问，角色或模型目录不能代替。操作后的状态须由同一执行者回读。技术文档继续按代码事实走原工程路由，不新增写作角色。

电脑任务的非原生派发直接使用 [run_computer_task.py 固定入口](computer-tasks.md)，不再先用普通 codex exec 碰应用审批。已有执行者用 result.json 的 resume_thread 继续；首次才需要协调者启动具名角色。
