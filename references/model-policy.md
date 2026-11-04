# GPT-6 委派设计依据

任务分工核对日期：2026-10-30。原价格快照日期：2026-09-30；本次未重核价格，不作为当前计费依据。本文是迁移依据与推荐初始配置，不是 selector 的模型注册表；实际绑定来自 custom agent TOML。Skill 不修改主对话模型/provider。

## 官方依据与价格

- [模型选择与推理档位](https://learn.chatgpt.com/docs/models)：Sol 适合常规与复杂编码、研究和多步工作；Luna 适合清晰、重复、聚焦任务。推荐起点是 Sol/medium、Luna/high、Astra/low；档位不跨代等价。
- [Sol 模型文档](https://developers.openai.com/api/docs/models/gpt-6.1-sol)、[Luna 模型文档](https://developers.openai.com/api/docs/models/gpt-6-luna)：支持推理、结构化输出与工具；带推理的工具调用应使用 Responses。两者上下文 1,050,000、最大输出 128,000 token；GPT-6.1 Sol 支持 low/medium/high/xhigh/max，不支持 none/minimal；Luna 还支持 none。Codex 可用档位以当前目录为准。
- [API 定价](https://developers.openai.com/api/docs/pricing)、[Codex credit 费率](https://learn.chatgpt.com/docs/pricing)：下表为 Standard、每百万 token；API 是美元，Codex 是 credits。

| 模型 | API 输入 / 缓存读取 / 输出 | Codex 输入 / 缓存读取 / 输出 |
|---|---|---|
| GPT-6 Luna | $0.10 / $0.01 / $0.50 | 2.5 / 0.25 / 12.5 |
| GPT-6.1 Sol | $2.00 / $0.10 / $10.00 | 50 / 2.5 / 250 |
| GPT-6 Astra | $10.00 / $1.00 / $50.00 | 250 / 25 / 1250 |
| GPT-5.6 Luna | $0.20 / $0.02 / $1.20 | 5 / 0.5 / 30 |
| GPT-5.6 Terra | $2.00 / $0.20 / $12.00 | 50 / 5 / 300 |
| GPT-5.6 Sol | $4.00 / $0.40 / $20.00 | 100 / 10 / 500 |

API 表为输入不超过 272K 的费率；GPT-6 超过该阈值时全请求输入/缓存费率乘 2、输出乘 1.5；缓存写入为输入费率的 1.25 倍。Codex credit 无单独缓存写入费，且 credit 单价不能直接推算套餐剩余额度。相同 token 数下，6.1 Sol 输入/输出单价是 Luna 的 20 倍、缓存读取为 10 倍；Astra 输入/输出是 6.1 Sol 的 5 倍、缓存读取为 10 倍；实际成本还取决于推理量、上下文、重试与验收。

## 本机推荐初始绑定

| 角色 | 配置 model / effort | 采用条件 |
|---|---|---|
| batch_explorer、batch_worker、explorer | gpt-6-luna / high | 清晰低风险、有证据的探索；写入限强验证 batch |
| computer_worker | gpt-6.1-terra / medium | 低/中风险、可回读结果的有界界面操作；须实测工具和应用访问 |
| researcher、worker | gpt-6.1-sol / medium | 多文件研究、普通有界实现 |
| deep_researcher、complex_worker、standard_reviewer | gpt-6.1-sol / high | 有界复杂工作、独立普通审查 |
| senior_worker、reviewer | gpt-6-astra / high | 保留既有高风险、合同敏感与跨模块门禁 |
| planning_auditor | gpt-6-astra / xhigh | 同时高影响和高歧义的规划/裁决 |

角色名均带 delegated_ 前缀。保留既有 Astra 的高风险绑定，不将官方通用 Astra/low 起点机械套用到这些特殊任务。Luna/high 是官方推荐起点，不使用旧协议“Luna 禁止 high”规则；以后只有代表任务证明同样合格时，才降低其推理档位。原 gpt-6-sol 绑定已迁为 gpt-6.1-sol；官方仍列旧型号，不等于当前账户或客户端仍可选。5.6 从本机默认委派绑定退出，但不禁止用户明确配置旧模型或其他 provider。

## 验证与验收边界

1. 规则验证：小任务不派发；Luna 不处理高风险/审查/弱验证写入；medium 风险探索走 Sol；缺模型、权限和 transport 时失败关闭；读取回退不获得写入权限。
2. 配置验证：精确 model ID、effort、sandbox 来自 TOML 并存在于当前目录；原生绑定必须有当前 model/effort/权限证据。旧工具 schema 未刷新不算新模型已生效。
3. 运行时验证：每个新模型各做一个带工具、确定答案的只读短任务，检查结果与 rollout 元数据；若经代理，还应区分请求模型、解析模型与上游回执。探针只证明所测调用链与任务，不证明所有任务质量。
4. 后续质量比较：在真实的探索、批量改写、普通实现、合同敏感审查中记录验收结果、返工/升级次数、延迟与 token；没有同任务对照，不声称总体节省比例或质量全面超过 5.6。该长期比较不阻塞规则与配置迁移，也不自动批量发起昂贵测试。

## Terra 与总消耗

[官方 Terra 模型页](https://developers.openai.com/api/docs/models/gpt-6.1-terra)明确支持 computer_use，推荐 medium 起步；[电脑操作指南](https://learn.chatgpt.com/docs/computer-use)要求对应工具、应用访问和系统权限。困难视觉任务仍可选 Astra。官方定位不证明本机子 agent 工具已连通。

主对话建议一般工程工作使用 Sol/medium，困难裁决再选 Astra；Skill 不修改主对话设置。以真实任务验收通过前的总用量评价分工，连同返工记录，区分输入、输出和接口报告的推理用量，避免重复计数；无可比基线不报节省比例，不默认四模型横评。
