# 委派模型分工

角色配置以 custom agent TOML 为准。selector 按任务风险、歧义和可验证性选择角色，随后读取配置。主对话沿用当前设置。

| 角色 | 当前模型 / 推理 | 适用任务 |
|---|---|---|
| batch_explorer、batch_worker、explorer | GPT-6 Luna / high | 可核验的低风险探索和批量工作 |
| computer_worker | GPT-6.1 Terra / medium | 有界电脑操作，需确认工具及应用访问 |
| researcher、worker | GPT-6.2 Sol / medium | 多文件研究、普通有界实现 |
| deep_researcher、complex_worker、standard_reviewer | GPT-6.2 Sol / high | 复杂有界工作和独立常规审查 |
| senior_worker、reviewer | GPT-6.2 Astra / high | 高风险实现、合同敏感审查 |
| planning_auditor | GPT-6.2 Astra / xhigh | 高影响且高歧义的规划或裁决 |

[GPT-6.2 官方说明](https://learn.chatgpt.com/docs/whats-new/gpt-62-astra-sol)把 Sol 用于日常多步工程工作，把 Astra 用于更难的跨系统任务。[Terra 模型说明](https://developers.openai.com/api/docs/models/gpt-6.1-terra)列出电脑操作支持。Codex 实际可用模型与档位以当前客户端、账户和模型目录为准。[套餐和费用](https://learn.chatgpt.com/docs/pricing)按当前官方口径查询。

升级时核对角色、精确模型 ID、推理档位和沙箱。模型或运行环境发生变化时，按[运行时方式](runtime-transports.md)验证目标路径。用代表任务的验收、返工率与总 Token 判断是否值得调低推理档位，避免仅凭模型代际改变档位或重做全量评测。
