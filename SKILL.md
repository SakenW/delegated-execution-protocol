---
name: delegated-execution-protocol
description: 当独立证据、可并行研究、有界实现或电脑操作委派确有收益时，选择并管理有界子 agent。普通小修改、顺序性任务和仅因任务复杂而委派不触发；不设置主对话模型。
---

# 委派执行协议

## Stage 0：是否值得委派

先比较独立证据、专业分工、隔离和关键路径收益与启动、打包、等待、审查和整合成本。仅“可以并行”不足以派发。小型、单文件、顺序性或直接确定性检查通常留在主对话。优先委派可独立进行的探索、日志分析、测试调查和资料扫描。

优化验收通过前的总 Token，计入上下文、交接、推理与返工；低单价、并行提速和缓存命中不等于 Token 更少。能用脚本或专用工具确定性完成的工作直接执行；已有上下文的小任务留在原处，不固定走逐级模型试错链。

风险和复杂度本身不是执行委派的充分条件。主对话保持当前模型、provider 和 reasoning 配置，不按 Skill 切换。模型差异通过 custom agent/config 绑定，不增加通用提示词补丁。

## 选择与打包

仅对通过价值门的真实候选读取 [路由策略](references/routing-policy.md)，运行其中的 selector。遵守 `delegate=false`、`max_workers`、强制 transport 和拆分要求；字段由证据推断，不变成用户问卷。selector 先选择角色，再从实际 Agent 配置读取模型、effort 与权限；不排斥主会话或已配置角色使用其他 provider。auto 只有在当前原生绑定已核验时使用原生派发，否则选择显式 CLI。

按既定规则逐项提取、分类或核对的低风险批量任务用 `delegated_batch_explorer`。范围明确、证据可核验的低中风险正确性审查用 `delegated_standard_reviewer`。高风险、跨模块或合同敏感的独立审查用 `delegated_reviewer`。普通探索用 `delegated_explorer`，多文件研究用 `delegated_researcher`，实现用 `delegated_worker`，高风险实现用 `delegated_senior_worker`，有界电脑操作用 `delegated_computer_worker`。不通过任务标签声称模型切换。普通派发读 [运行时方式](references/runtime-transports.md)；电脑任务只读 [固定入口](references/computer-tasks.md)，使用内置审批脚本。 selector 只给路由建议，不证明账户/provider 可用；正式派发前必须通过该 transport 的当前检查。普通 CLI 使用 `scripts/preflight_dispatch.py`，电脑入口直接核验运行绑定，原生使用实际 child 的 model/effort/权限证据。失败回主线程，不自动替换角色、模型或 provider。

## 所有权与执行

委派包包括目标、已验证事实、相关路径、may-edit/must-not-edit、安全边界、验收与输出要求。提供完成任务必需的上下文，不复制整套规则或原始日志。只传必要片段和可访问的证据路径；完整日志留工作盘。独立的大材料可隔离处理，避免后续主对话反复携带；完整历史仅在它实际更安全时使用。

同一有界任务尽量由一个执行者完成读取、操作和验证，不默认拆成探索、实现、审查流水线。只并发执行读写范围不相交的工作，依赖链保持顺序。同一应用或标签页由一个执行者持有，避免重复截图与会话交接。写入者须知道其他 agent 也在工作，不得撤回他人修改。读写审查混合任务先只读判断，由主对话接受后再执行；遵守 `requires_main_acceptance=true`，这不是额外的用户审批门。

使用所选 transport 暴露的生命周期动作。`interrupt_agent` 停止过时工作，但不代表 closure。仅在用户明确要求新任务时创建侧栏任务；内部委派使用协作子 agent 或受控 CLI。

## 完成后的对抗审查门

高风险、合同敏感、跨模块冲突或用户需要独立证据时，将只读审查作为新的候选再过价值门。低风险、可确定性验证的工作优先自动检查，无需仪式化 reviewer；复用同一候选仍适用的证据。主对话裁决 findings；等相关子 agent 进入终态并处理结果后，再检查最终完整差异、权限和验证，完成集成或已授权的提交。

## 证据与汇报

子 agent 返回精炼发现、证据位置、建议、异常和未验证项，不倒回原始大日志。请求被接受只证明 assignment 已绑定；实际 model/effort 须由运行时元数据证明。只因客观失败、证据冲突或范围扩大升级，模型自报低信心不足以升级；避免循环重试。

只有委派状态、阻塞、安全边界、长任务状态或差异化路由对用户重要时才发送过程说明，否则静默执行并在最终交付中汇总。有必要解释差异化路由时才读 [汇报细则](references/reporting.md)。

## 维护此协议时的验证

普通使用本 Skill 不运行协议全套测试。仅修改 selector、协议合同或验证兼容性时运行既有检查：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/validate_protocol.py
```

需要核验本机注册 profile 与模型目录时加 `--check-local-profiles`。静态合同检查只证明约束仍在，不等同真实模型行为验证。
