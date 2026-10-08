#!/usr/bin/env python3
"""系统提示词静态体检工具。

检查维度对应 references/ 下的设计方法：
1. 模糊措辞（业务规则不可执行的信号）
2. 大写强调密度（过度使用会稀释注意力）
3. XML 标签配对与语义化命名
4. Markdown 标题层级
5. SOP 步骤结构与异常分支
6. few-shot 示例数量与动态检索风险
7. 上下文安全要素
8. 静态前缀中的动态字段

用法：
    python lint_prompt.py <提示词文件> [--strict] [--max-shout 8] [--examples 3]

退出码：0 = 通过；1 = 不通过；2 = 参数或文件错误。
"""

import argparse
import re
import sys
from collections import Counter

SHOUT_WORDS = ("NEVER", "MUST", "ALWAYS", "CRITICAL", "FORBIDDEN", "IMPORTANT")

VAGUE_WORDS = (
    "适当", "酌情", "酌量", "尽量", "尽可能", "视情况", "看情况", "自行判断",
    "必要时", "适当处理", "酌情处理", "合理地",
    "as appropriate", "if needed", "as necessary", "generally", "usually", "try to",
)

PLACEHOLDER_PATTERNS = (
    (re.compile(r"\{\{[^}]+\}\}"), "存在未替换的占位符"),
    (re.compile(r"<[A-Z_]{3,}>"), "存在未替换的占位符"),
    (re.compile(r"TODO|TBD|待补充|待定"), "存在 TODO/待补充 标记"),
)

DYNAMIC_PATTERNS = (
    (re.compile(r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}"), "疑似写入具体时间戳，应放入 user 消息"),
    (re.compile(r"\{\{\s*(date|time|user_id|request_id|today)\s*\}\}", re.I), "疑似动态字段，应放入 user 消息"),
    (re.compile(r"当前时间[:：]\s*\d"), "疑似运行时动态字段"),
)

REQUIRED_BLOCKS = (
    ("persona", "缺少身份与人格定义区块 persona"),
    ("hard_constraints", "缺少硬约束区块 hard_constraints（生死条款）"),
    ("priority", "缺少规则优先级与冲突裁决区块 priority"),
    ("output_spec", "缺少输出规范区块 output_spec"),
    ("failure_response", "缺少失败姿态区块 failure_response"),
    ("security_policy", "缺少上下文安全区块 security_policy"),
    ("fallback", "缺少兜底区块 fallback（未覆盖情况如何处理）"),
)

LAYOUT_TAGS = ("div", "span", "info", "section", "box", "text", "content", "item", "row", "sec")


class Report:
    def __init__(self):
        self.items = []

    def error(self, code, message, line=None):
        self.items.append(("ERROR", code, message, line))

    def warn(self, code, message, line=None):
        self.items.append(("WARN", code, message, line))

    def info(self, code, message, line=None):
        self.items.append(("INFO", code, message, line))


def strip_code_blocks(text):
    """返回 (正文行列表, 代码块行号集合)。代码块内的示例不参与检查。"""
    lines = text.splitlines()
    body, in_block, fence = [], set(), False
    for idx, line in enumerate(lines, start=1):
        if line.lstrip().startswith("```"):
            fence = not fence
            in_block.add(idx)
            continue
        if fence:
            in_block.add(idx)
            continue
        body.append((idx, line))
    return body, in_block


def line_of(text, pos):
    return text[:pos].count("\n") + 1


def check_placeholders(report, text, in_block):
    for pattern, message in PLACEHOLDER_PATTERNS:
        for match in pattern.finditer(text):
            no = line_of(text, match.start())
            if no not in in_block:
                report.error("PLACEHOLDER", message, no)


def check_dynamic(report, body):
    for no, line in body:
        for pattern, message in DYNAMIC_PATTERNS:
            if pattern.search(line):
                report.warn("DYNAMIC", message, no)


def check_vague(report, body):
    hits = Counter()
    for no, line in body:
        low = line.lower()
        for word in VAGUE_WORDS:
            if word.lower() in low:
                hits[word] += 1
                report.error(
                    "VAGUE",
                    "模糊措辞「" + word + "」使规则不可判定，应改为枚举条件 + 数值阈值 + 唯一动作",
                    no,
                )
    if hits:
        detail = "，".join(w + " x" + str(c) for w, c in hits.items())
        report.info("VAGUE_SUM", "模糊措辞统计：" + detail)


def check_shout(report, body, max_shout):
    total = 0
    for no, line in body:
        count = sum(len(re.findall(r"\b" + w + r"\b", line)) for w in SHOUT_WORDS)
        if count:
            total += count
            if count >= 3:
                report.warn("SHOUT_LINE", "单行出现 " + str(count) + " 处大写强调，建议只保留红线", no)
    if total > max_shout:
        report.error(
            "SHOUT_TOTAL",
            "大写强调共 " + str(total) + " 处，超过上限 " + str(max_shout) + "；其余改普通表述",
        )
    else:
        report.info("SHOUT_TOTAL", "大写强调共 " + str(total) + " 处（上限 " + str(max_shout) + "）")


def check_xml(report, text, body):
    tags = re.findall(r"<([a-zA-Z_][a-zA-Z0-9_.-]*)>", text)
    counts = Counter(tags)
    for tag, count in counts.items():
        close = text.count("</" + tag + ">")
        if close != count:
            report.error("XML_PAIR", "标签 <" + tag + "> 出现 " + str(count) + " 次但闭合 " + str(close) + " 次")
    for tag in counts:
        if tag.lower() in LAYOUT_TAGS:
            report.warn("XML_NAME", "标签 <" + tag + "> 无业务语义，应改为 snake_case 语义名")
    if not tags:
        report.warn("XML_NONE", "未发现 XML 语义块；建议 Markdown 管层次、XML 管语义的双层结构")
    for name, message in REQUIRED_BLOCKS:
        if ("<" + name + ">") not in text:
            report.error("BLOCK_MISSING", message)
    for no, line in body:
        if len(re.findall(r"<[a-z_]+>", line)) > 6:
            report.warn("XML_DEPTH", "单行标签过多，嵌套过深会提高模型定位成本", no)


def check_headings(report, body):
    levels = []
    for no, line in body:
        match = re.match(r"^(#{1,6})\s+\S", line)
        if match:
            levels.append((no, len(match.group(1)), line.strip()))
    if not levels:
        report.warn("MD_NONE", "未发现 Markdown 标题；标题承担人读的组织逻辑")
        return
    h1 = [item for item in levels if item[1] == 1]
    if len(h1) > 1:
        report.error("MD_H1", "存在 " + str(len(h1)) + " 个一级标题，全文应只保留一个 H1", h1[1][0])
    for prev, cur in zip(levels, levels[1:]):
        if cur[1] - prev[1] > 1:
            report.error("MD_JUMP", "标题层级跳级：H" + str(prev[1]) + " 到 H" + str(cur[1]) + "（" + cur[2] + "）", cur[0])


def check_sop(report, body):
    step_lines = [(no, line) for no, line in body if re.search(r"\bStep\s*\d+", line)]
    if not step_lines:
        report.warn("SOP_NONE", "未发现编号步骤；规则堆砌应改写为带分支的 SOP")
        return
    report.info("SOP_STEPS", "检测到 " + str(len(step_lines)) + " 处步骤标记")
    start = step_lines[0][0]
    block = [(no, line) for no, line in body if no >= start]
    joined = "\n".join(line for _, line in block)
    if not re.search(r"失败分支|否则|若未|未找到|出错|异常|降级|停止|回滚", joined):
        report.error("SOP_BRANCH", "流程缺少异常分支（失败 / 否则 / 降级 / 停止 / 回滚）", start)
    missing = [k for k in ("触发", "动作", "产出", "条件") if k not in joined]
    if missing:
        report.warn("SOP_FIELDS", "流程步骤建议补齐要素：" + "、".join(missing), start)
    if not re.search(r"↓|→", joined):
        report.warn("SOP_FLOW", "步骤之间缺少流转标记，模型难以判断当前处于哪一步", start)


def check_examples(report, body, expected):
    count = 0
    for no, line in body:
        if re.search(r"示例\s*\d+|Example\s*\d+", line):
            count += 1
    if count == 0:
        report.info("FEWSHOT", "未发现 few-shot 示例；若风格或格式难以用规则描述，应补 2-3 组")
    elif count > expected:
        report.warn("FEWSHOT_MANY", "示例 " + str(count) + " 组超过建议上限 " + str(expected) + "，过多示例会稀释规则注意力")
    else:
        report.info("FEWSHOT", "示例 " + str(count) + " 组（建议 " + str(expected) + " 组以内，覆盖典型/边界/拒绝）")
    for no, line in body:
        low = line.lower()
        if ("示例" in line or "example" in low) and re.search(r"检索|最相关|similar|retrieve", low):
            report.error("FEWSHOT_DYNAMIC", "示例按请求动态检索会击穿 KV Cache 前缀，应准备固定示例集", no)


def check_security(report, text, body):
    joined = "\n".join(line for _, line in body)
    if "external_content" not in text:
        report.warn("SEC_SOURCE", "未见 external_content 来源标记规范（外部内容需包裹并标注不可信）")
    if "untrusted" not in text:
        report.warn("SEC_TRUST", "external_content 未标注 trust 属性（如 trust=untrusted）")
    if not re.search(r"确认|confirm", joined, re.I):
        report.error("SEC_CONFIRM", "未见高风险操作的用户确认要求")
    if not re.search(r"(泄露|输出)[^。\n]{0,20}(系统提示词|system prompt)", joined, re.I):
        report.warn("SEC_LEAK", "建议显式禁止泄露系统提示词内容")


def lint(path, max_shout, expected_examples, strict):
    with open(path, "r", encoding="utf-8") as handle:
        text = handle.read()

    body, in_block = strip_code_blocks(text)
    report = Report()

    if not body:
        report.error("EMPTY", "提示词正文为空（仅含代码块）")
    check_placeholders(report, text, in_block)
    check_dynamic(report, body)
    check_vague(report, body)
    check_shout(report, body, max_shout)
    check_xml(report, text, body)
    check_headings(report, body)
    check_sop(report, body)
    check_examples(report, body, expected_examples)
    check_security(report, text, body)

    order = {"ERROR": 0, "WARN": 1, "INFO": 2}
    report.items.sort(key=lambda item: (order[item[0]], item[1]))

    print("=" * 62)
    print("系统提示词体检：" + path)
    print("=" * 62)
    counts = Counter(item[0] for item in report.items)
    for level, code, message, no in report.items:
        location = "（第 " + str(no) + " 行）" if no else ""
        print("[" + level + "] " + code.ljust(20) + " " + message + location)
    print("-" * 62)
    print("合计：ERROR " + str(counts["ERROR"]) + "，WARN " + str(counts["WARN"]) + "，INFO " + str(counts["INFO"]))

    failed = counts["ERROR"] > 0 or (strict and counts["WARN"] > 0)
    print("结论：" + ("不通过，需修复后复检" if failed else "通过"))
    return 1 if failed else 0


def main():
    parser = argparse.ArgumentParser(description="系统提示词静态体检")
    parser.add_argument("prompt", help="提示词文件路径")
    parser.add_argument("--max-shout", type=int, default=8, help="大写强调条数上限（默认 8）")
    parser.add_argument("--examples", type=int, default=3, help="few-shot 示例组数建议上限（默认 3）")
    parser.add_argument("--strict", action="store_true", help="存在 WARN 也判定不通过")
    args = parser.parse_args()

    try:
        sys.exit(lint(args.prompt, args.max_shout, args.examples, args.strict))
    except FileNotFoundError:
        print("文件不存在：" + args.prompt)
        sys.exit(2)
    except UnicodeDecodeError:
        print("文件编码非 UTF-8，无法解析：" + args.prompt)
        sys.exit(2)


if __name__ == "__main__":
    main()
