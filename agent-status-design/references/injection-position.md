# 状态栏在上下文中的插入位置

## 1. 消息结构总览

```text
messages: [
  { role: "system",    content: "你是电信客服..." }              ← 固定不变（KV Cache 缓存）
  tools: [cancel_plan, query_records, ...]                       ← 固定不变（KV Cache 缓存）

  { role: "user",      content: "帮我取消套餐" }
  { role: "assistant", tool_calls: [cancel_plan(...)] }
  { role: "tool",      content: "该套餐有合约期..." }
  { role: "assistant", content: "您的套餐在合约期内..." }
  ... 更多对话轮次 ...
  { role: "user",      content: "那帮我查一下通话记录" }          ← 用户追问
  { role: "user",      content: "<agent_status>
                                  已呼叫 3/3 次 · TODO: 取消套餐(进行中)
                                </agent_status>" }               ← 框架插入的状态栏
]
                                                                 ↑ 模型从此处开始生成
```

## 2. 为什么是 user 角色 + 末尾

**关键实现细节**：状态栏在 API 层面实际上作为**一条 `user` 角色的消息插入到上下文末尾**，而不是修改开头的 system 消息。

原因正是 KV Cache 约束：修改 system 消息会破坏**整个前缀**的缓存。

需要澄清一个易混淆点：这里的 `user` 角色只是 **API 协议层面的技术选择**，并不等同于「来自终端用户的输入」。换句话说，Harness 是在**借用 user 角色这个消息槽位**，向模型注入由 Agent 框架自动生成的系统状态信息——内容并非来自真实用户，只是复用了 user 角色的消息格式来挂到上下文末尾。

## 3. 为什么放末尾

- **注意力**：末尾信息在空间上最接近即将生成的新 token，获得最高注意力权重。这是对「注意力衰减」的强制性纠正。
- **缓存**：追加而非修改，前面所有已缓存内容都不受影响。

这正是「**动态信息追加末尾、静态信息保持不动**」原则在状态栏场景的应用。

## 4. 第 N 次 API 调用时的完整消息列表示例

```text
messages: [
  { role: "system",    content: "You are a customer service assistant..." }  ← Fixed（KV Cache 命中）
  { role: "user",      content: "Help me cancel my Xfinity plan" }           ← 原始用户请求
  { role: "assistant", content: null, tool_calls: [...] }                    ← 第 1 轮：决定调用
  { role: "tool",      content: "Call log..." }                              ← 第 1 轮：调用结果
  { role: "assistant", content: null, tool_calls: [...] }                    ← 第 2 轮：再次调用
  { role: "tool",      content: "Call log..." }                              ← 第 2 轮：调用结果
  ...(more rounds)
  { role: "user",      content: "Can you call them again to follow up?" }    ← 用户追问
  { role: "user",      content: "<agent_status>
                                  Current State:
                                  - phone_call invoked 3 times (Xfinity: 3/3 max)
                                  - Current time: 2025-09-14 10:30:45
                                  - TODO: [1] Cancel plan (in_progress)
                                 </agent_status>" }                          ← 框架注入的状态栏
]
```

要点：最后一条消息 `role` 是 `user`，但内容是**框架自动生成的元信息**，用 `<agent_status>` 标签包裹以便模型识别其特殊性质。它位于上下文最末尾，紧邻模型即将生成的新 token，因此获得最高注意力权重；同时因为它是**追加**而非修改，前面所有已缓存内容都不受影响。

## 5. 与系统提示词的分工

| 维度 | 系统提示词 | 状态栏 |
| --- | --- | --- |
| 内容性质 | 静态指令（身份、规则、流程） | 动态元信息（进度、计数、环境） |
| 位置 | 上下文开头 | 上下文末尾 |
| 更新频率 | 随版本发布 | 每轮或每事件 |
| 缓存角色 | 静态前缀，必须字节级稳定 | 动态后缀，追加不破坏前缀 |
| 典型内容 | 「拨打每个商家不超过 3 次」的**规则** | 「已拨打 Xfinity 3/3 次」的**事实** |

两者是互补关系：规则说「上限是 3」，状态栏说「现在是 3」。只有规则没有状态，模型得自己数；只有状态没有规则，模型不知道 3 意味着什么。

## 6. 实现清单

- [ ] 状态栏作为**独立消息**追加，不与其他消息合并（合并会破坏缓存语义）
- [ ] role 使用 `user`，并在内容中用 `<agent_status>` 明确标注来源为框架
- [ ] 不修改 system 消息、不修改 tools 字段
- [ ] 不修改任何已注入的历史消息
- [ ] 状态栏消息位于消息列表**最后一项**
- [ ] 系统提示词中写明「末尾 `<agent_status>` 中的计数与约束以状态栏为准」

## 7. 常见错误

| 错误做法 | 后果 |
| --- | --- |
| 把状态栏写进 system 消息 | 每轮改写前缀，KV Cache 全面失效 |
| 把状态栏塞进用户消息内容里 | 无法区分真实用户输入与框架元信息，影响来源判断 |
| 把状态栏放在上下文中部 | 落入注意力衰减区，效果大幅下降 |
| 每轮重新生成整段消息列表 | 破坏所有已缓存内容 |
| 用 assistant 角色注入状态 | 污染模型自身输出历史，破坏对话交替结构 |
