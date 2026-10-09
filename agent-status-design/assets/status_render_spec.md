# 状态渲染规范（代码输出格式约定）

使用说明：
1. 本文件定义**代码渲染状态栏后输出的文本格式**，是 `render_status_bar(state)` 的输出约定，**不是提示词模板，不要把它写进 system prompt**。
2. 状态栏是运行时由代码计算并注入的，格式稳定的意义在于让模型形成模式识别（字段名稳定比措辞重要）。
3. 字段取舍：每个字段都要能回答「模型缺了它会做错什么决定」，答不出就删掉。
4. 语言由需求澄清表确认（中文 / 英文 / 双语），一旦确定不再变动。

---

## 1. 输出契约

```python
def render_status_bar(state) -> str:
    """返回用 <agent_status> 包裹的状态栏文本。state 由代码维护。"""
    return "<agent_status>\n" + "\n".join(render_lines(state)) + "\n</agent_status>"
```

注入方式（伪代码）：

```python
messages.append({
    "role": "user",                # 借用 user 槽位挂到末尾，内容由框架生成
    "content": render_status_bar(state)
})
```

## 2. 字段字典

| 字段 | 类型 | 数据来源 | 更新时机 | 是否必选 |
| --- | --- | --- | --- | --- |
| tool_calls | dict[tool_name, count] | 框架计数器 | 每次调用后 | 是（若存在约束） |
| groups | dict[tool(target), count] | 框架计数器（分组） | 每次调用后 | 按需（需求确认） |
| constraints | list[已用/上限/是否超限] | 计数器 + 配置阈值 | 每次调用后 | 是（若存在约束） |
| todo | list[id, content, status, updated_at] | TODO 存储 | 状态变更时 | 按需 |
| progress | done/total | TODO 存储派生 | 状态变更时 | 随 todo |
| current_time | timestamp | 系统时钟 | 每轮 | 是 |
| working_directory | path | 运行时跟踪（cd 后立即更新） | 变更时 | 是 |
| environment | os · shell · runtime | 运行时探测 | 会话开始 + 变更 | 按需 |
| last_error | 四层结构 | 错误处理器 | 出错后 | 是 |
| anomaly | 重复调用提醒 | 重复调用检测 | 触发阈值时 | 按需 |
| original_request | text | 首轮用户消息（只读快照） | 会话开始追加一次 | 长会话建议 |

约束：所有字段值只来自受控数据源（计数器、环境变量、内部存储），**禁止外部自由文本直接透传**（投毒防护）。

## 3. 渲染示例

### 3.1 完整版（多步骤任务，英文）

```text
<agent_status>
Current State:
- Tool call summary: 'phone_call' has been invoked 3 times (Xfinity: 3)
- Constraint check: Maximum calls to Xfinity reached (3/3) ✗
- TODO: [✓] Contact Xfinity  [✓] Confirm discount  [·] Wait for user confirmation
- Current time: 2025-09-14 10:30:45
- Working directory: /home/user/project
- Environment: ubuntu 22.04 · bash · python 3.11
- Last error: none
</agent_status>
```

### 3.2 完整版（中文）

```text
<agent_status>
- 工具调用统计：phone_call 已调用 3 次（Xfinity: 3）
- 约束检查：Xfinity 呼叫已达上限（3/3），禁止再次调用
- TODO：[✓] 联系 Xfinity [✓] 确认降价 [·] 等待用户确认  进度：2/3 完成
- 当前时间：2025-09-14 10:30:45
- 工作目录：/home/user/project
- 环境：ubuntu 22.04 · bash · python 3.11
- 最近错误：无
</agent_status>
```

### 3.3 精简版（轮次多、状态小）

```text
<agent_status>
3/3 calls · TODO 2/3 done · 10:30 · /home/user/project
</agent_status>
```

## 4. 工具返回结果中的计数标注（与状态栏配套）

状态栏给总计，工具返回值给本次序号，两者配合效果最好：

```text
[2025-09-14 10:30:45] Tool call #3 for 'phone_call' (target: Xfinity)
Result: 接通，报价 $65/月
Remaining budget: 0/3
```

模型看到「第 3 次」与「剩余 0」会直接触发模式识别，不再尝试第 4 次。

## 5. 错误字段的四层结构

```text
- Last error: FileNotFoundError
  - 描述：目标文件不存在
  - 参数：{"path": "src/config.yaml"}
  - 调用栈：tool_executor.py:142 → file_ops.py:58
  - 修复建议：验证路径拼写；确认工作目录是否为 /home/user/project；改用绝对路径
```

## 6. 参考实现

统计、分组、约束检查与渲染可直接复用 `../scripts/status_ledger.py`（命令行版，可改造为库函数）：

```bash
python ../scripts/status_ledger.py trace.jsonl --config limits.json --todo todo.json --check
```

改造要点：
- `build_ledger()` 对应「计数器 + 约束检查」，接入真实调用钩子而非离线轨迹。
- `render_text()` / `render_xml()` 对应本规范的渲染层。
- `--check` 的退出码 1 可直接作为运行时的超限拦截信号。
