#!/usr/bin/env python3
"""从项目里勘察状态栏设计所需的事实，并给出默认方案。

目的：设计参数尽量从代码/配置/日志里读到，而不是抛一堆问题给用户。
本脚本输出「事实 + 证据（文件:行）」与「推断的默认方案」，供填写
assets/requirements_intake.md 使用。

用法：
    python discover_context.py <项目目录>
    python discover_context.py <项目目录> --trace trace.jsonl
    python discover_context.py <项目目录> --json

退出码：0 正常；2 路径或读取错误。
"""

import argparse
import json
import os
import re
import sys
from collections import Counter

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".idea", ".vscode"}
SOURCE_EXT = {".py", ".ts", ".js", ".go", ".java", ".json", ".yaml", ".yml", ".toml", ".md"}

PATTERNS = {
    "state_injection": (r"agent_status|system-reminder|system_reminder|status_bar|statusbar", "已有状态栏相关代码"),
    "counter": (r"call_count|counter|invoked_count|tool_calls_count|调用次数", "已有计数器相关代码"),
    "todo": (r"todo_list|todos|rewrite_todo|update_todo", "已有 TODO 相关代码"),
    "message_assembly": (r"messages\.append|messages\.push|role.*=.*[\"']system[\"']|client\.messages\.create|chat\.completions", "消息拼装位置"),
    "constraints": (r"max_calls|max_retries|max_|limit|budget|timeout", "约束与阈值配置"),
    "model": (r"model\s*=|claude-|gpt-|model_name|MODEL\s*=", "模型配置"),
    "cache": (r"cache_control|ephemeral|prompt_caching|defer_loading|tool_search", "缓存相关配置"),
}


def iter_source_files(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if os.path.splitext(name)[1].lower() in SOURCE_EXT:
                yield os.path.join(dirpath, name)


def scan(root):
    """返回 {类别: {'code': [(文件:行, 内容)], 'doc': [...]}}。

    文档（.md）中的提及只能说明「被讨论过」，不能证明「已实现」，因此分开统计。
    """
    hits = {key: {"code": [], "doc": []} for key in PATTERNS}
    for path in iter_source_files(root):
        is_doc = os.path.splitext(path)[1].lower() == ".md"
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                lines = handle.readlines()
        except OSError:
            continue
        if len(lines) > 4000:
            continue
        for no, line in enumerate(lines, start=1):
            for key, (pattern, _) in PATTERNS.items():
                if re.search(pattern, line, re.I):
                    rel = os.path.relpath(path, root)
                    bucket = "doc" if is_doc else "code"
                    hits[key][bucket].append(("%s:%d" % (rel, no), line.strip()[:120]))
    return hits


def load_trace(path):
    """读取轨迹：JSON 数组、含 messages 的对象，或 JSONL。"""
    with open(path, "r", encoding="utf-8") as handle:
        content = handle.read()
    stripped = content.lstrip()
    if stripped.startswith("["):
        return json.loads(content)
    if stripped.startswith("{"):
        data = json.loads(content)
        if isinstance(data, dict):
            for key in ("messages", "requests", "records"):
                if key in data:
                    return data[key]
            return [data]
    rows = []
    for line in content.splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def estimate_tokens(text):
    """粗略估算：中文按 1 字 ≈ 1 token，其余按 4 字符 ≈ 1 token。"""
    text = str(text)
    cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
    other = len(text) - cjk
    return int(cjk + other / 4.0)


def analyze_trace(messages):
    """从轨迹样本估算 N（更新次数）与 R（轮间新增后缀 token）。"""
    user_turns = 0
    tool_calls = 0
    arg_keys = Counter()
    total_tokens = 0
    for message in messages:
        if not isinstance(message, dict):
            continue
        total_tokens += estimate_tokens(message.get("content") or "")
        role = message.get("role")
        if role == "user":
            user_turns += 1
        for call in message.get("tool_calls") or []:
            if not isinstance(call, dict):
                continue
            function = call.get("function", {}) if isinstance(call.get("function"), dict) else call
            tool_calls += 1
            raw = function.get("arguments", call.get("input"))
            if isinstance(raw, str):
                try:
                    raw = json.loads(raw)
                except json.JSONDecodeError:
                    raw = {}
            if isinstance(raw, dict):
                for key in raw:
                    arg_keys[key] += 1
    rounds = max(1, user_turns + tool_calls)
    return {
        "user_turns": user_turns,
        "tool_calls": tool_calls,
        "rounds": rounds,
        "total_tokens": total_tokens,
        "R": max(1, int(total_tokens / rounds)),
        "N": rounds,
        "arg_keys": arg_keys.most_common(5),
    }


def best_evidence(hits, key):
    """优先取代码证据；只有文档提及时返回 (None, 文档位置)。"""
    code = hits[key]["code"]
    if code:
        return code[0][0], False
    doc = hits[key]["doc"]
    if doc:
        return doc[0][0], True
    return None, False


def recommend(hits, trace_stats, alpha, state_tokens):
    """基于勘察事实推断默认方案。"""
    plan = []
    injection, from_doc = best_evidence(hits, "state_injection")
    if injection and not from_doc:
        plan.append(("注入点", "沿用现有状态栏注入点（%s），只改渲染内容" % injection))
    else:
        assembly, assembly_doc = best_evidence(hits, "message_assembly")
        if assembly and not assembly_doc:
            plan.append(("注入点", "在消息拼装处末尾追加（%s）" % assembly))
        else:
            plan.append(("注入点", "代码中未找到注入/拼装位置，需人工定位后再实现"))

    counter, counter_doc = best_evidence(hits, "counter")
    if counter and not counter_doc:
        plan.append(("计数器", "已有计数器实现（%s），复用并扩展分组计数" % counter))
    todo_hit, todo_doc = best_evidence(hits, "todo")
    if todo_hit and not todo_doc:
        plan.append(("TODO", "已有 TODO 相关实现（%s），复用现有存储" % todo_hit))

    if trace_stats and trace_stats["arg_keys"]:
        top_key, top_count = trace_stats["arg_keys"][0]
        plan.append(("计数维度", "默认按参数 `%s` 分组计数（样本中出现 %d 次），同时保留全局计数" % (top_key, top_count)))
    else:
        plan.append(("计数维度", "默认全局计数（未提供轨迹样本，未能推断分组字段）"))

    if trace_stats:
        s = state_tokens
        r = trace_stats["R"]
        n = trace_stats["N"]
        c_replace = max(n - 1, 0) * (1 - alpha) * r
        c_append = alpha * s * n * (n - 1) / 2.0
        choice = "持久追加" if alpha * s * n / 2.0 < (1 - alpha) * r else "每轮替换"
        plan.append(("更新策略", "%s（S=%d R=%d N=%d α=%.2f；C_replace=%.0f，C_append=%.0f）"
                     % (choice, s, r, n, alpha, c_replace, c_append)))
    else:
        plan.append(("更新策略", "未提供轨迹样本，无法测算；建议先采集 5-10 条轨迹再定"))

    plan.append(("TODO", "启用（若任务平均超过 3 步）" if (trace_stats and trace_stats["rounds"] > 3) else "暂不启用"))
    return plan


def report(root, hits, trace_stats, plan, as_json, alpha, state_tokens):
    if as_json:
        print(json.dumps({
            "root": root,
            "hits": {k: {"code": v["code"][:5], "doc": v["doc"][:5]} for k, v in hits.items()},
            "trace": trace_stats,
            "recommended_plan": [{"item": k, "value": v} for k, v in plan],
        }, ensure_ascii=False, indent=2))
        return
    print("=" * 62)
    print("项目勘察：" + root)
    print("=" * 62)
    for key, (_, label) in PATTERNS.items():
        code_hits = hits[key]["code"]
        doc_hits = hits[key]["doc"]
        print("-" * 62)
        if code_hits:
            print("%s：代码中 %d 处" % (label, len(code_hits)))
            for where, line in code_hits[:3]:
                print("  [代码] %s  %s" % (where, line))
        elif doc_hits:
            print("%s：仅在文档中提及 %d 处（不构成实现证据）" % (label, len(doc_hits)))
            for where, line in doc_hits[:2]:
                print("  [文档] %s  %s" % (where, line))
        else:
            print("%s：未发现" % label)
    if trace_stats:
        print("-" * 62)
        print("轨迹样本统计：用户轮次 %d · 工具调用 %d · 估算轮数 N=%d"
              % (trace_stats["user_turns"], trace_stats["tool_calls"], trace_stats["N"]))
        print("轮间新增后缀 R≈%d token · 样本总 token≈%d"
              % (trace_stats["R"], trace_stats["total_tokens"]))
        if trace_stats["arg_keys"]:
            keys = "，".join("%s(%d)" % (k, c) for k, c in trace_stats["arg_keys"])
            print("高频调用参数：" + keys)
    print("-" * 62)
    print("推断的默认方案（α=%.2f，单条状态 S=%d token）：" % (alpha, state_tokens))
    for item, value in plan:
        print("  · %s：%s" % (item, value))
    print("-" * 62)
    print("下一步：把以上事实填入 assets/requirements_intake.md 第 1、2 部分，")
    print("        只有业务决策类分叉点才列入第 3 部分找用户确认。")


def main():
    parser = argparse.ArgumentParser(description="从项目里勘察状态栏设计所需事实并给出默认方案")
    parser.add_argument("project", help="项目目录")
    parser.add_argument("--trace", help="轨迹样本文件（JSON / JSONL），用于估算 N 与 R")
    parser.add_argument("--alpha", type=float, default=0.1, help="缓存单价倍数（默认 0.1，可用文档查到的实际值覆盖）")
    parser.add_argument("--state-tokens", type=int, default=60, help="单条状态消息 token 数 S（默认 60）")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出")
    args = parser.parse_args()

    if not os.path.isdir(args.project):
        print("目录不存在：" + args.project)
        return 2
    try:
        hits = scan(args.project)
        trace_stats = analyze_trace(load_trace(args.trace)) if args.trace else None
    except (OSError, json.JSONDecodeError) as error:
        print("读取失败：" + str(error))
        return 2

    plan = recommend(hits, trace_stats, args.alpha, args.state_tokens)
    report(args.project, hits, trace_stats, plan, args.json, args.alpha, args.state_tokens)
    return 0


if __name__ == "__main__":
    sys.exit(main())
