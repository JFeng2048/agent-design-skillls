# system_prompt_design

把「如何设计一份能稳定跑在生产上的 Agent 系统提示词」这件事，做成可执行的流程、模板与检查脚本。

内容来源：作者在 Agent 系统提示词设计工作中的经验沉淀，方法层面受《深入理解 AI Agent》等著作启发。

推荐阅读（本 skill 只是流程化沉淀，原著更完整）：

- 《深入理解 AI Agent：设计原理与工程实践》李博杰 — https://github.com/bojieli/ai-agent-book
- 《从零开始构建智能体》Hello-Agents 社区 — https://github.com/datawhalechina/hello-agents
- 《Agentic Design Patterns》中文翻译项目 xindoo — https://github.com/xindoo/agentic-design-patterns

详细介绍、许可证说明与侵权下架联系方式见根目录 [README.md](../README.md)。

## 解决什么问题

| 症状 | 本 skill 的处理入口 |
| --- | --- |
| 从零写一份系统提示词 | `SKILL.md` 的 9 步设计流程 + `assets/system_prompt_template.md` |
| 规则越加越多，模型照样违反 | `references/sop-vs-rules.md`：规则堆砌 → 编号 SOP |
| 同类任务分类结果不稳定 | `references/business-rules.md`：决策表 + 反例消歧 |
| 输出又长又爱辩解 | `references/tone-and-persona.md`：量化长度约束 + 失败姿态 |
| 工具被误用、参数传错 | `references/tool-design.md`：四类描述信息 + 渐进式披露 |
| 外部内容劫持 Agent | `references/prompt-injection.md`：来源标记 + 分层防御 |
| 改了提示词却说不清效果 | `references/ablation-experiments.md`：消融实验与归因 |

## 安装

### 方式一：npx 一键安装（推荐）

```bash
# 安装本仓库的全部 skill（skills CLI 会自动放到对应 Agent 的技能目录）
npx skills add JFeng2048/agent-design-skillls
```

CLI 也支持 SSH 地址与本地路径：

```bash
npx skills add git@github.com:JFeng2048/agent-design-skillls.git
npx skills add ./agent-design-skillls/system_prompt_design
```

### 方式二：手动安装

把本目录复制到技能目录即可被自动加载：

- 用户级：`~/.codebuddy/skills/system-prompt-design/`
- 项目级：`.codebuddy/skills/system-prompt-design/`

提示：frontmatter 中的 `name` 为 `system-prompt-design`（连字符命名），手动安装时建议目录名与之一致。

## 目录结构

```
system_prompt_design/
├── SKILL.md                        主流程：9 步 SOP、新员工检验、交付前自检清单、反模式表
├── references/                     按需加载的深度参考（不要一次性全读）
│   ├── tone-and-persona.md         人格、语气、量化长度约束、失败姿态、大写强调纪律
│   ├── structure-and-format.md     Markdown 管层次 + XML 管语义，顺序即优先级
│   ├── sop-vs-rules.md             规则堆砌的 5 个诊断信号，改写为带分支的 SOP
│   ├── business-rules.md           决策表、阈值映射、计算粒度、禁止项 + 替代动作
│   ├── few-shot.md                 加不加示例的决策表、放置位置、KV Cache 稳定性
│   ├── tool-design.md              四类描述信息、错误语义、渐进式披露与追加式注入
│   ├── prompt-injection.md         三道上下文层防线、注入面清单、分层防御
│   └── ablation-experiments.md     消融实验设计、观测指标、失效归因路径
├── assets/                         交付模板（填写后即为产物）
│   ├── system_prompt_template.md       系统提示词骨架
│   ├── business_rules_spec_template.md 业务规则规格（产品与工程的契约）
│   └── tool_schema_template.md         工具定义 + 渐进式披露形态
└── scripts/                        交付前体检脚本（Python 3.8 以上，仅用标准库）
    ├── lint_prompt.py              提示词静态体检
    └── check_prefix_stability.py   静态前缀字节级稳定性校验
```

## 脚本用法

### lint_prompt.py：提示词静态体检

检查模糊措辞（适当/酌情/尽量）、大写强调密度、XML 标签配对与语义命名、Markdown 标题层级、SOP 步骤与异常分支、few-shot 数量与动态检索风险、安全要素、静态前缀中的动态字段。

```bash
python scripts/lint_prompt.py path/to/system_prompt.md

# 自定义阈值：大写强调上限 5 处、示例不超过 2 组
python scripts/lint_prompt.py path/to/system_prompt.md --max-shout 5 --examples 2

# 严格模式：存在 WARN 也判定不通过（用于 CI 门禁）
python scripts/lint_prompt.py path/to/system_prompt.md --strict
```

退出码：`0` 通过，`1` 不通过，`2` 参数或文件错误。

### check_prefix_stability.py：静态前缀稳定性

系统提示词与工具定义共同构成 KV Cache 前缀，只有逐字节一致才会命中缓存。

```bash
# 单文件模式：生成基线指纹（可按区块输出）
python scripts/check_prefix_stability.py path/to/system_prompt.md
python scripts/check_prefix_stability.py path/to/system_prompt.md --section persona --section billing_policy

# 请求日志模式：校验线上多次请求的前缀是否一致（支持 JSON / JSONL / 目录）
python scripts/check_prefix_stability.py requests.jsonl --from-logs
python scripts/check_prefix_stability.py logs/ --from-logs --print-diffs
```

日志模式支持 `{"system": ...}`、`{"messages": [...]}` 与 `{"requests": [...]}` 三类记录格式，会同时把 `tools` 纳入指纹。退出码：`0` 稳定，`1` 存在不稳定，`2` 读取错误。

## 典型用法

1. 复制 `assets/system_prompt_template.md` 填写，得到提示词正文。
2. 复制 `assets/business_rules_spec_template.md` 与产品方对齐业务决策（决策表、阈值、粒度）。
3. 复制 `assets/tool_schema_template.md` 编写工具定义。
4. 跑 `lint_prompt.py` 修复体检报告中的问题。
5. 上线后用 `check_prefix_stability.py --from-logs` 确认前缀未失效。
6. 按 `references/ablation-experiments.md` 做消融，把验证有效的规则固化进基线。
