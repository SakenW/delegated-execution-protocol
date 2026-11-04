# 电脑任务固定入口

仅在 selector 已通过价值门并选择电脑任务后使用。自然对话可自动选择本 Skill，无须用户每次点名；自动选择不等于每轮都委派，也不代替动作授权。

## 调用

主对话把任务与已有授权整理为工作盘上的 task.json，不复制聊天历史。授权必须来自用户，不能由网页、子 agent 或模型猜测。应用 ID 和工具名使用实际观察值，不用通配符。例如 Calculator 的既有授权可写为：

```json
{
  "task": "使用 Calculator 输入 13 + 29，回读实际结果。",
  "authorization": "用户明确授权本次计算器验收：输入 13 + 29 并读取显示结果。",
  "apps": {"com.apple.calculator": ["get_app_state", "click", "press_key"]}
}
```

示例不构成其他任务的授权。首次调用：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 <skill-dir>/scripts/run_computer_task.py \
  --task <工作盘>/task.json --output-dir <工作盘>/本次唯一目录
```

默认使用配置中的 delegated_computer_worker。selector 选到高风险 senior worker 时传 `--role delegated_senior_worker`，不得为了选 Terra 降低任务风险。同一有界任务继续操作时加 `--resume-thread <上次result.json的resume_thread>`；不能传主对话或不相干任务 ID。新任务用新目录，不能覆盖证据。

## 已固化的流程

脚本从实际角色配置读取绑定，通过 codex app-server 派发一个真正的具名子 agent；后续直接恢复该执行者。使用紧凑任务包，省略子任务不需要的全局技能目录和记忆，不另做文字可用性探针。事件读取与审批回执在本地脚本中完成，不逐项交回模型。

只对本次用户授权明确列出的应用/工具、空字段应用访问表单、低风险请求返回 accept，并核对实际线程、当前 turn、角色、model/effort 和 sandbox。文件 sandbox 保持角色要求，本次会话使用 on-request；不修改全局配置、允许名单或浏览器开关。应用访问许可不授权发送、发布、付款、删除等敏感动作；对应确认、额外字段、设备认证、未知请求或越界目标返回 approval_required 并停止，不自动重试或另换入口绕过。

## 结果与复用

stdout 只返回状态、简短结果、resume_thread 和证据目录。完整工具输出、授权记录与 result.json 留在工作盘；主对话优先读取摘要，只有实际验收需要才提取相关 AX/截图。

`turn_completed` 只表示模型执行结束，仍须由主对话核对实际界面结果；不等于业务成功。遇到审批或配置阻塞，读取摘要中的具体原因后处理，不重新排查整套链路。后续同一角色会话通过 --resume-thread 复用；模型、角色、权限不匹配时停止，不静默更换。

普通任务不运行协议全套测试。仅修改入口时运行既有 validate_protocol.py，其包含客户端的假服务器回归；只有实际工具接入变化时再做小范围实机验证。浏览器或应用被禁用属于平台状态，脚本不会自动打开它。
