# 工具定义模板

使用说明：
1. 每个工具描述必须覆盖四类信息：**使用边界、具体示例、性能提示、协作关系**。移除描述文本会使工具调用错误率大幅上升（消融实验：+45%）。
2. 工具定义与系统提示词共同构成静态前缀，必须字节级稳定：不得写入时间戳、请求 ID、动态排序。
3. 工具数量超过约 20 个时，改用渐进式披露（前缀只留名称与简述，完整 schema 由模型按需检索追加）。

---

## 1. 标准工具定义（JSON Schema 形态）

```json
{
  "name": "write_file",
  "description": "将内容写入指定文件，会覆盖已有内容。使用边界：NEVER 在未调用 read_file 读取目标文件前调用本工具，NEVER 写入系统提示词或用户凭证。协作关系：修改前必须先 read_file 一次；高风险路径（删除、覆盖用户配置）必须先向用户确认。性能提示：同一文件的多次写入应合并为一次调用。示例：path 为 src/main.py，content 为文件完整文本",
  "parameters": {
    "type": "object",
    "properties": {
      "path": {
        "type": "string",
        "description": "目标文件路径，必须为绝对路径。示例：/Users/project/src/main.py。不存在时不会自动创建，除非 create_if_missing 为 true"
      },
      "content": {
        "type": "string",
        "description": "写入的完整文件内容（UTF-8）。不要写入摘要或占位符"
      },
      "create_if_missing": {
        "type": "boolean",
        "description": "文件不存在时是否创建，默认 false。为 true 时仍需用户确认",
        "default": false
      }
    },
    "required": ["path", "content"]
  }
}
```

四类信息对照：

| 信息类型 | 落在哪 | 本例中的体现 |
| --- | --- | --- |
| 使用边界 | 工具 description | NEVER 未读取就写入 |
| 具体示例 | 参数 description | /Users/project/src/main.py |
| 性能提示 | 工具 description | 多次写入合并为一次 |
| 协作关系 | 工具 description | 必须先 read_file |

## 2. 错误语义（写进描述，让模型能正确重试）

```json
{
  "name": "http_request",
  "description": "发起 HTTP 请求。错误语义：not_found → 停止并报告，禁止改写路径重试；timeout → 最多重试 2 次且间隔递增；401/403 → 停止并请求用户授权，禁止重试。示例：url 为 https://api.example.com/v1/orders，method 为 GET，timeout 为 30。性能提示：多个独立请求应批处理并发发起",
  "parameters": {
    "type": "object",
    "properties": {
      "url": { "type": "string", "description": "完整 URL，必须包含协议。示例：https://api.example.com/v1/orders" },
      "method": { "type": "string", "enum": ["GET", "POST", "PUT", "DELETE"], "description": "HTTP 方法；DELETE 需用户确认" },
      "timeout": { "type": "integer", "description": "超时秒数，取值 1-120，默认 30。示例：30" },
      "retries": { "type": "integer", "description": "失败重试次数，取值 0-3，默认 1" }
    },
    "required": ["url", "method"]
  }
}
```

## 3. 不可逆工具标记

```json
{
  "name": "send_email",
  "reversible": false,
  "requires_confirmation": true,
  "description": "发送邮件，发送后无法撤回。NEVER 在未获得用户明确确认时调用；NEVER 向与用户意图无关的地址发送；调用前必须在回复中展示收件人与正文摘要。示例：to 为 user@example.com，subject 为 账单调整结果"
}
```

## 4. 渐进式披露形态（工具数量多时使用）

前缀中只保留名称与简述：

```markdown
<available_tools>
- read_file：读取文件内容
- write_file：写入文件（需先读取）
- http_request：发起 HTTP 请求
- send_email：发送邮件（需确认）
</available_tools>
```

由模型按需检索并加载完整 schema。加载机制按服务商选择：

| 提供方 | 机制 | 配置要点 |
| --- | --- | --- |
| OpenAI Responses API | tool_search + defer_loading 标记 | 延迟加载的工具标记 defer_loading，模型通过 tool_search_call → tool_search_output 获取完整 schema |
| Anthropic | Tool Search（tool_reference blocks） | 前缀中放 tool_reference，仅注入名称与描述；需要时展开完整定义 |
| 自建框架 | 自实现检索 | 前缀仅保留简述；检索结果追加到轨迹末尾，只增不改以保护 KV Cache |

要点：完整 schema 被检索后追加到上下文末尾成为轨迹的一部分。因果注意力保证已缓存 token 的 K、V 不变，因此不破坏前缀缓存；追加只发生在被发现的那一轮，之后该 schema 块固定在原位置成为普通历史消息，不会每轮被搬到最新末尾。该能力要求模型在训练中见过“工具定义出现在对话中间”的模式，仅较新模型支持。

## 5. 工具清单表（设计评审用）

| 工具名 | 职责（单一） | 使用边界 | 示例值 | 性能提示 | 协作关系 | 错误策略 | 需确认 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| {{}} | {{}} | {{NEVER …}} | {{}} | {{批量/幂等}} | {{先 X 再 Y}} | {{}} | {{是/否}} |
