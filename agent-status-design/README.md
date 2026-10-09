# agent-status-design

**编码实现指导**：教你在代码里把 Agent 状态栏做出来——计数器、TODO 存储、环境感知、错误摘要、注入时机与更新策略。

这不是「生成提示词模板」的 skill。状态栏是**运行时由代码计算并注入**的：系统提示词写「每个商家最多拨打 3 次」（规则，属 `system-prompt-design`），状态栏由代码写出「已拨打 Xfinity 3/3」（事实，本 skill 的产出）。

使用本 skill 时：**先自己把信息找齐，再给方案**——项目代码/配置/日志、官方文档与网页、可跑的实测，能自己确认的就自己确认；只有业务规则、产品取舍、权限边界这类**必须由人拍板**的决策才问用户，且一次不超过 3 个问题、每项带选项与推荐项（见 `references/information-gathering.md` 与 `assets/requirements_intake.md`）。

核心思路：**把分散在轨迹中的隐式状态，提炼成上下文末尾的显式元信息**。提示工程给静态指令，状态栏给运行时状态。

## 解决什么问题

| 症状 | 入口 |
| --- | --- |
| 数不清工具调用次数，反复超上限 | `references/fundamentals.md` + `scripts/status_ledger.py` |
| Agent 陷入无限循环、重复调用同一工具 | 工具调用计数器（在结果中标注第 N 次） |
| 忘记用户原始诉求、遗漏子任务 | TODO 列表 + rewrite/update 工具（`assets/todo_tool_schema.md`） |
| 缺乏时间、工作目录、系统环境感知 | `references/status-content.md` 环境观察摘要 |
| 出错后盲目重试 | 详细错误信息四层结构（`references/techniques.md`） |
| 状态栏该插在哪、用什么角色 | `references/injection-position.md` |
| 每轮替换还是持久追加 | `scripts/cache_cost_estimator.py` + `assets/update_strategy_decision.md` |
| 状态栏被外部内容污染 | `references/maintenance-security.md` |

## 安装

```bash
npx skills add JFeng2048/agent-design-skillls
```

手动安装：把本目录复制到技能目录（建议目录名与 frontmatter 的 `name` 一致，即 `agent-status-design`）。

- 用户级：`~/.codebuddy/skills/agent-status-design/`
- 项目级：`.codebuddy/skills/agent-status-design/`

## 目录结构

```
agent_status_design/
├── SKILL.md                        主流程（10 步）、瞥一眼检验、自检清单、反模式
├── references/
│   ├── information-gathering.md    自主获取信息：项目勘察、文档检索、实测、什么才必须问用户
│   ├── fundamentals.md             理论基础：检索 vs 推理、注意力衰减、提炼层
│   ├── status-content.md           三类信息：任务规划、侧信道、环境观察
│   ├── injection-position.md       末尾 user 角色消息与消息结构
│   ├── update-strategies.md        替换 vs 追加与缓存代价模型
│   ├── techniques.md               五种技术与涌现效应
│   └── maintenance-security.md     代码维护、投毒防护、原始上下文保留
├── assets/
│   ├── requirements_intake.md      设计输入：需求澄清表（分叉点确认 + 假设记录）
│   ├── status_render_spec.md       输出约定：代码渲染格式与字段字典
│   ├── todo_tool_schema.md         TODO 结构与两个专用工具定义
│   └── update_strategy_decision.md 更新策略决策表与实测校准
└── scripts/
    ├── discover_context.py         项目勘察：事实 + 证据 + 默认方案
    ├── status_ledger.py            轨迹统计、约束检查、状态片段生成
    └── cache_cost_estimator.py     替换 vs 追加的成本估算与分界点扫描
```

## 脚本用法

### discover_context.py：项目勘察

先从项目里取事实，再决定要不要问人。输出带 `文件:行` 证据的勘察结果（区分**代码命中**与**仅在文档中提及**），并从轨迹样本估算 S/R/N，最后给出可直接落地的默认方案。

```bash
python scripts/discover_context.py <项目目录>
python scripts/discover_context.py <项目目录> --trace trace.jsonl --alpha 0.1 --state-tokens 60
python scripts/discover_context.py <项目目录> --json
```

### status_ledger.py：状态账本

统计工具调用次数（全局 + 按参数分组）、比对约束上限、生成可直接注入的状态片段。**计数必须由代码完成**——模型无条件相信状态栏，让 LLM 批量统计会引入错误。

```bash
# 统计并生成状态栏片段
python scripts/status_ledger.py trace.jsonl

# 带约束配置（超限给出禁止动作）
python scripts/status_ledger.py trace.jsonl --config limits.json

# 运行时拦截：已达上限则退出码为 1
python scripts/status_ledger.py trace.jsonl --config limits.json --check

# 附带 TODO 与环境信息
python scripts/status_ledger.py trace.jsonl --todo todo.json --cwd /home/u/p --os "ubuntu 22.04"

# 机器可读输出
python scripts/status_ledger.py trace.jsonl --format json
```

约束配置示例：

```json
{
  "phone_call": {
    "max": 3,
    "group_by": ["target"],
    "group_limits": { "Xfinity": 3 }
  }
}
```

支持 OpenAI 形态的 `tool_calls` 与 Anthropic 形态的 `tool_use` 内容块；输入可为 JSON 数组、`{"messages": [...]}` 或 JSONL。

### cache_cost_estimator.py：更新策略估算

```bash
# 单次估算：S 状态大小、R 轮间新增后缀、N 更新次数、alpha 缓存单价倍数
python scripts/cache_cost_estimator.py --s 60 --r 800 --n 12 --alpha 0.1

# 扫描分界点
python scripts/cache_cost_estimator.py --s 60 --r 800 --n 12 --sweep-n 2 40
python scripts/cache_cost_estimator.py --s 60 --n 12 --sweep-r 100 3000 --step 100
```

判定式：`alpha*S*N/2 < (1-alpha)*R` → 倾向**持久追加**，否则倾向**每轮替换**。结果需结合服务商缓存计费与实测命中率校准。

## 一条关键纪律

状态栏由**代码**维护：计数、阈值比对、状态机推进都不交给 LLM。确需语义判断时，让 LLM **逐条抽取**，再由代码汇总——绝不让它一次性批量统计整块状态栏。
