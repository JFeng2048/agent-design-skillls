#!/usr/bin/env python3
"""Agent 状态栏账本：从轨迹中统计工具调用、检查约束、生成状态栏片段。

设计要点（见 references/maintenance-security.md）：
状态栏必须由代码维护。模型几乎无条件相信状态栏——写「打了 3 次」它就当真是 3 次，
不会自己重算。因此计数与阈值比对必须在这里完成，绝不让 LLM 批量统计。

用法：
    # 统计轨迹并输出状态栏片段
    python status_ledger.py trace.jsonl

    # 带约束配置（超限会给出禁止动作，并可用 --check 让退出码为 1）
    python status_ledger.py trace.jsonl --config limits.json --check

    # 附带 TODO 与环境信息
    python status_ledger.py trace.jsonl --todo todo.json --cwd /home/u/p --os "ubuntu 22.04"

    # 输出机器可读格式
    python status_ledger.py trace.jsonl --format json

轨迹格式：JSON 数组、{"messages": [...]}、或 JSONL 逐行消息。
支持 assistant 消息的 tool_calls（OpenAI 形态）与 content 中的 tool_use 块（Anthropic 形态）。

退出码：0 正常；1 存在已达上限或超限的约束（仅 --check）；2 读取或参数错误。
"""

import argparse
import json
import os
import re
import sys
from collections import OrderedDict
from datetime import datetime

STATUS_MARK = {
    "pending": "[ ]",
    "in_progress": "[·]",
    "completed": "[✓]",
    "cancelled": "[x]",
}


def load_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        content = handle.read()
    stripped = content.lstrip()
    if stripped.startswith("["):
        return json.loads(content)
    if stripped.startswith("{"):
        data = json.loads(content)
        if isinstance(data, dict):
            for key in ("messages", "requests", "events", "records"):
                if key in data:
                    return data[key]
            return [data]
    rows = []
    for line in content.splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def parse_arguments(raw):
    """工具参数可能是 JSON 字符串、已解析对象或缺失。"""
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return {}


def extract_calls(messages):
    """从消息列表中提取工具调用序列。返回 [(tool_name, args_dict, timestamp)]。"""
    calls = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        stamp = message.get("timestamp") or message.get("time")
        role = message.get("role")

        for call in message.get("tool_calls") or []:
            if not isinstance(call, dict):
                continue
            function = call.get("function", {}) if isinstance(call.get("function"), dict) else call
            name = function.get("name") or call.get("name")
            if not name:
                continue
            calls.append((name, parse_arguments(function.get("arguments", call.get("input"))), stamp))

        if role == "assistant":
            content = message.get("content")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        calls.append(
                            (block.get("name", ""), parse_arguments(block.get("input")), stamp)
                        )
    return calls


def build_ledger(calls, config):
    """统计全局次数、分组次数，并比对约束。"""
    total = OrderedDict()
    groups = OrderedDict()
    for name, args, _ in calls:
        total[name] = total.get(name, 0) + 1
        group_by = (config.get(name) or {}).get("group_by") or []
        for field in group_by:
            value = args.get(field)
            if value is None:
                continue
            key = "%s(%s)" % (name, value)
            groups[key] = groups.get(key, 0) + 1

    checks = []
    for name, count in total.items():
        spec = config.get(name) or {}
        limit = spec.get("max")
        if limit is None:
            continue
        checks.append(
            {
                "scope": name,
                "used": count,
                "max": limit,
                "ok": count < limit,
                "exceeded": count > limit,
            }
        )
    for key, count in groups.items():
        tool = key.split("(", 1)[0]
        spec = config.get(tool) or {}
        value = key[len(tool) + 1 : -1]
        limit = (spec.get("group_limits") or {}).get(value, spec.get("max"))
        if limit is None:
            continue
        checks.append(
            {
                "scope": key,
                "used": count,
                "max": limit,
                "ok": count < limit,
                "exceeded": count > limit,
            }
        )
    return total, groups, checks


def render_text(total, groups, checks, todo, environment):
    lines = []
    if total:
        parts = []
        for name, count in total.items():
            related = ["%s: %d" % (key.split("(", 1)[1][:-1], num) for key, num in groups.items()
                       if key.split("(", 1)[0] == name]
            parts.append("%s 已调用 %d 次%s" % (name, count, " (" + "，".join(related) + ")" if related else ""))
        lines.append("- 工具调用统计：" + "；".join(parts))
    for check in checks:
        if check["exceeded"]:
            lines.append("- 约束检查：%s %d/%d 已超限，禁止继续调用" % (check["scope"], check["used"], check["max"]))
        elif not check["ok"]:
            lines.append("- 约束检查：%s 已达上限 %d/%d，禁止再次调用" % (check["scope"], check["used"], check["max"]))
        else:
            lines.append("- 约束检查：%s %d/%d，剩余 %d 次" % (check["scope"], check["used"], check["max"], check["max"] - check["used"]))
    if todo:
        done = sum(1 for item in todo if item.get("status") == "completed")
        rendered = []
        for item in todo:
            mark = STATUS_MARK.get(item.get("status"), "[ ]")
            rendered.append("%s %s %s" % (mark, item.get("id", "?"), item.get("content", "")))
        lines.append("- TODO：" + " ".join(rendered) + "  进度：%d/%d 完成" % (done, len(todo)))
    for key, value in environment.items():
        lines.append("- %s：%s" % (key, value))
    return "\n".join(lines)


def render_xml(body):
    return "<agent_status>\n%s\n</agent_status>" % body


def main():
    parser = argparse.ArgumentParser(description="Agent 状态栏账本：统计、约束检查与状态片段生成")
    parser.add_argument("trace", help="轨迹文件（JSON / JSONL）")
    parser.add_argument("--config", help="约束配置 JSON：{工具名: {max: N, group_by: [字段], group_limits: {值: N}}}")
    parser.add_argument("--todo", help="TODO 列表 JSON 文件（数组）")
    parser.add_argument("--format", choices=["xml", "text", "json"], default="xml", help="输出格式")
    parser.add_argument("--cwd", help="注入工作目录")
    parser.add_argument("--os", dest="os_name", help="注入操作系统信息")
    parser.add_argument("--no-time", action="store_true", help="不注入当前时间")
    parser.add_argument("--check", action="store_true", help="存在已达上限或超限时退出码为 1")
    args = parser.parse_args()

    try:
        messages = load_json(args.trace)
        config = json.load(open(args.config, "r", encoding="utf-8")) if args.config else {}
        todo = json.load(open(args.todo, "r", encoding="utf-8")) if args.todo else []
    except (OSError, json.JSONDecodeError) as error:
        print("读取失败：" + str(error))
        return 2

    calls = extract_calls(messages)
    total, groups, checks = build_ledger(calls, config)

    environment = OrderedDict()
    if not args.no_time:
        environment["当前时间"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if args.cwd:
        environment["工作目录"] = args.cwd
    if args.os_name:
        environment["环境"] = args.os_name

    body = render_text(total, groups, checks, todo, environment)

    if args.format == "json":
        print(json.dumps(
            {"tool_calls": total, "groups": groups, "constraints": checks,
             "todo": todo, "environment": environment},
            ensure_ascii=False, indent=2))
    elif args.format == "text":
        print(body if body else "（无状态字段）")
    else:
        print(render_xml(body if body else "（无状态字段）"))

    blocked = [item for item in checks if not item["ok"] or item["exceeded"]]
    if args.check and blocked:
        for item in blocked:
            print("[BLOCKED] %s %d/%d" % (item["scope"], item["used"], item["max"]), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
