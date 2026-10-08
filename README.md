# agent-design-skills

仓库地址：https://github.com/JFeng2048/agent-design-skillls

一组用于 **LLM Agent 设计** 的 Skill 包，把书籍与工程实践中的设计方法沉淀为可复用的操作流程。

当前收录：

| Skill | 解决的问题 |
| --- | --- |
| system_prompt_design | 系统提示词与工具定义的设计、重构、注入加固与消融验收 |

## 为什么做这个

本仓库记录的不是「提示词技巧」，而是**作者在 Agent 系统提示词设计这份工作里的做事方式**——把每次设计系统提示词时反复用到的判断、取舍和检查项，固化成一套可重复执行的流程：先澄清业务决策，再定人格与结构，接着把规则写成 SOP，最后用脚本体检、用消融实验验收。

之所以做这件事，是因为 Agent 的行为差异大部分不来自模型能力，而来自**系统提示词与工具定义的设计质量**；而这类工作高度依赖个人经验，很难在团队里复制。流程化之后，设计过程可以被评审、被交接、被迭代。

## 使用方式

一键安装（[skills CLI](https://skills.sh)，支持 Claude Code / Cursor / Codex / CodeBuddy 等）：

```bash
npx skills add JFeng2048/agent-design-skillls
```

也可以手动安装：把 skill 目录复制到技能目录后即可被自动加载。

- 用户级：`~/.codebuddy/skills/技能名/`
- 项目级：`.codebuddy/skills/技能名/`

详细用法、脚本与模板说明见 [system_prompt_design/README.md](system_prompt_design/README.md)。

## 参考来源

本仓库内容是作者在以下书籍与自身工程实践基础上**独立整理、重新组织**而成的，**未复制任何原书文字内容，也未按原书章节结构编排**。方法层面的思路受下列著作启发，在此致以诚挚谢意，感谢先驱，感谢知识分享：

| 书籍 / 项目 | GitHub 地址 | 作者 / 维护者 | 许可证 | 使用方式 |
| --- | --- | --- | --- | --- |
| 《深入理解 AI Agent：设计原理与工程实践》 | https://github.com/bojieli/ai-agent-book | 李博杰（Bojie Li） | Apache License 2.0 | 主要方法论来源：提示工程、上下文与 KV Cache、Skills、安全分层 |
| 《从零开始构建智能体》 | https://github.com/datawhalechina/hello-agents | 陈思州、孙韬、姜舒凡、黄佩林、曾鑫民、胡昊、朱信忠及全体贡献者 | CC BY-NC-SA 4.0 | 延伸参考，仅借鉴概念框架 |
| 《Agentic Design Patterns》中文翻译项目 | https://github.com/xindoo/agentic-design-patterns | xindoo | 仓库未声明明确许可证，README 声明仅供学习交流 | 仅作延伸阅读指引，未作为内容来源 |

若后续版本从上述书籍中直接摘录文字、图表或示例，必须按对应许可证处理，如若侵权可联系作者(JFeng2048@outlook.com)进行删除：

- **Apache-2.0**：允许商业使用与衍生，但需保留版权与许可声明、标注修改、以 Apache-2.0 传递被授权部分。
- **CC BY-NC-SA 4.0**：允许衍生，但**禁止商业用途**且必须以相同协议发布；若摘录，该部分不适用本仓库的 MIT 许可，需单独标注并以 CC BY-NC-SA 4.0 发布。
- **许可证不明确的来源**：在取得明确授权前不摘录、不改编，仅提供书名与链接。

## 推荐阅读

如果你觉得本仓库的流程有用，强烈建议去读原著——它们比这里的内容更完整、更严谨，也覆盖了本 skill 之外的整个 Agent 工程体系。

### 1. 《深入理解 AI Agent：设计原理与工程实践》 — 李博杰（Bojie Li）

- 地址：https://github.com/bojieli/ai-agent-book
- 许可：Apache License 2.0
- 推荐理由：把 Agent 当成**系统**来讲的一本书。上下文工程、KV Cache 前缀与缓存命中、Skills 与渐进式披露、工具定义的描述设计、提示注入与分层防御、以及配套的按章实验代码，都有工程级拆解。本 skill 中「系统提示词属于静态前缀」「工具定义应渐进式披露」「上下文层防御只是第一道防线」等判断，都来自这本书的方法论。
- 适合：已经在写 Agent、想把「能跑」变成「稳定跑」的工程与产品同学。

### 2. 《从零开始构建智能体》 — Hello-Agents 社区（Datawhale）

- 地址：https://github.com/datawhalechina/hello-agents
- 许可：CC BY-NC-SA 4.0（**非商业用途**，衍生需以相同协议发布）
- 推荐理由：从零搭建智能体的完整教程，智能体历史、经典范式（ReAct、Plan-and-Solve、Reflection）、上下文工程、记忆机制、通信协议与真实案例都有覆盖，配套代码可直接跑。想系统补齐 Agent 全景知识，这本最合适入门。
- 适合：刚接触 Agent、希望边读边写代码的读者。注意许可限制，请勿用于商业场景。

### 3. 《Agentic Design Patterns》中文翻译项目 — xindoo

- 地址：https://github.com/xindoo/agentic-design-patterns
- 许可：仓库未声明明确许可证，README 声明内容仅供学习交流并遵循原书条款
- 推荐理由：把 Agent 的常用设计（提示链、路由、并行化、反思、工具使用、规划、多智能体协作等）整理成可检索的**模式清单**，中文翻译质量高，支持在线阅读与 PDF/epub 下载。遇到「这个需求该用什么结构」时，按模式查比从头设计更快。
- 适合：想要一份 Agent 设计速查手册的读者。本仓库仅提供链接指引，未摘录其任何内容。

> 以上推荐均为个人阅读体验，与各作者 / 社区无商业关联。

## 侵权与下架

若上述书籍或项目的作者 / 维护者认为本仓库的引用、链接或整理方式不妥，请直接联系我删除，无需任何流程：

- 邮箱：JFeng2048@outlook.com
- 或在本仓库提 issue：https://github.com/JFeng2048/agent-design-skillls/issues

收到后我会第一时间处理并回复。

## 本仓库许可

本仓库自有内容（Skill 文档、脚本、模板）以 [MIT License](LICENSE) 发布。

## 免责声明

本仓库为个人学习与工程实践整理，非官方出版物；方法有效性取决于具体业务场景，请结合自身数据做消融验证后再用于生产环境。