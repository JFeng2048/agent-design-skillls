# TODO 列表的工具定义与 Schema

设计依据：借鉴 Manus 的「通过复述操纵注意力」理念，用两个专用工具让 Agent 反复复述任务目标。启用 TODO 后平均 15 次迭代完成任务，禁用时需 21 次且经常遗漏子任务。

---

## 1. TODO 项 Schema

```json
{
  "id": "t1",
  "content": "联系 Xfinity 协商降价",
  "status": "in_progress",
  "created_at": "2025-09-14 10:00:12",
  "updated_at": "2025-09-14 10:22:40",
  "depends_on": []
}
```

| 字段 | 说明 |
| --- | --- |
| id | 唯一标识符，必须使用稳定 ID 而非序号，避免引用错位 |
| content | 一句话可验证的目标，动词开头 |
| status | pending / in_progress / completed / cancelled |
| created_at / updated_at | 时间戳，用于判断某项停留时长 |
| depends_on | 依赖的 TODO ID（可选，用于排序与阻塞判断） |

状态枚举语义：
- `pending`：未开始
- `in_progress`：正在进行（同一时刻建议最多 1 项）
- `completed`：已完成
- `cancelled`：已放弃（必须写明替代方案，不要让模型默默丢弃）

## 2. rewrite_todo_list

用于整体重写列表（任务分解变更时使用）。

```json
{
  "name": "rewrite_todo_list",
  "description": "整体重写 TODO 列表，用于任务分解发生变更时。使用边界：NEVER 用它只更新单项状态（改用 update_todo_status）；NEVER 删除已完成项，历史项保留 completed 状态以便模型看到已完成的工作。每项必须包含 id（稳定标识符）、content、status。示例：items 为 [{id: t1, content: 联系 Xfinity 协商降价, status: in_progress}]。协作关系：重写后须在下一次状态栏中体现新列表。",
  "parameters": {
    "type": "object",
    "properties": {
      "items": {
        "type": "array",
        "description": "完整的新 TODO 列表，按执行顺序排列。示例：[{id: t1, content: 联系 Xfinity, status: completed}]",
        "items": {
          "type": "object",
          "properties": {
            "id": { "type": "string", "description": "稳定标识符，已有项沿用原 id，新增项用新 id。示例：t1" },
            "content": { "type": "string", "description": "一句话可验证的目标，动词开头。示例：确认降价到 $59" },
            "status": { "type": "string", "enum": ["pending", "in_progress", "completed", "cancelled"], "description": "项状态" },
            "depends_on": { "type": "array", "items": { "type": "string" }, "description": "依赖的 TODO id 列表，可为空" }
          },
          "required": ["id", "content", "status"]
        }
      }
    },
    "required": ["items"]
  }
}
```

## 3. update_todo_status

用于更新单项状态（高频操作）。

```json
{
  "name": "update_todo_status",
  "description": "更新单个 TODO 项的状态。使用边界：NEVER 用它调整任务分解（改用 rewrite_todo_list）；NEVER 把唯一进行中的项标记为 completed 而不先推进下一项。示例：id 为 t1，status 为 completed。性能提示：同一轮的多个状态更新应合并为一次调用。错误语义：id_not_found → 先调用 rewrite_todo_list 同步列表，禁止猜测 id。",
  "parameters": {
    "type": "object",
    "properties": {
      "id": { "type": "string", "description": "TODO 项稳定标识符。示例：t1" },
      "status": { "type": "string", "enum": ["pending", "in_progress", "completed", "cancelled"], "description": "目标状态" },
      "note": { "type": "string", "description": "状态变更原因，cancelled 时必填替代方案。示例：商家拒绝降价，改为申请优惠券" }
    },
    "required": ["id", "status"]
  }
}
```

## 4. 状态栏中的 TODO 呈现

```text
<agent_status>
TODO:
- [✓] t1 联系 Xfinity 协商降价        (completed 10:22)
- [✓] t2 确认降价到 $59/月            (completed 10:28)
- [·] t3 等待用户确认是否接受          (in_progress 10:30)
进度：2/3 完成
</agent_status>
```

呈现要点：
- 保留已完成项，让模型看到已完成的工作（避免重复劳动）。
- 显示进度计数（`2/3`），不要求模型自己数。
- 进行中项放最后，靠近生成位置。

## 5. 实现注意事项

- 状态存储放在框架侧（内存 / 数据库），不要依赖模型复述来维护唯一真相。
- 每次 `rewrite_todo_list` / `update_todo_status` 后，立刻刷新下一次注入的状态栏。
- TODO 状态变更写入审计日志，便于回放「模型当时看到了什么」。
- 任务结束条件：全部项为 `completed` 或 `cancelled`，且无 `in_progress` 残留。
