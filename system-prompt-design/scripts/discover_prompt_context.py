#!/usr/bin/env python3
"""从项目里勘察系统提示词设计所需的事实，并给出默认方案。

目的：设计所需的信息尽量从项目里读到，而不是抛一堆问题给用户。
输出「事实 + 证据（文件:行）」与「推断的默认方案」，供填写
assets/requirements_intake.md 使用。区分代码/提示词命中与文档提及，
避免把文档里的讨论误判为已实现。

用法：
    python discover_prompt_context.py <项目目录>
    python discover_prompt_context.py <项目目录> --json

退出码：0 正常；2 路径或读取错误。
"""

import argparse
import json
import os
import re
import sys
from collections import Counter

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".idea", ".vscode"}
SOURCE_EXT = {".py", ".ts", ".js", ".go", ".java", ".json", ".yaml", ".yml", ".toml", ".md", ".txt", ".prompt"}

PATTERNS = {
    "system_prompt": (r"SYSTEM_PROMPT|system_prompt|system prompt|你是一个|你是.*助手|You are a", "系统提示词定义"),
    "tools": (r"tools\s*=|\"tools\"|tool_schema|function_call|tool_calls", "工具定义"),
    "business_rules": (r"policy|业务规则|NEVER |MUST |上限|阈值|不得超过|计费|退款规则", "业务规则"),
    "constraints": (r"max_calls|max_retries|max_|limit|budget|timeout", "约束与阈值"),
    "few_shot": (r"示例\s*\d|Example\s*\d|few_shot|few-shot|示例：|Examples?:", "few-shot 示例"),
    "dynamic_fields": (r"datetime\.now|time\.time|Date\(\)|当前时间|current_date|user_id", "动态字段（提示词中出现即为缓存风险）"),
    "model": (r"model\s*=|claude-|gpt-|model_name", "模型配置"),
    "injection_defense": (r"external_content|untrusted|提示注入|prompt injection", "注入防御"),
}

CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def iter_source_files(root, excludes=()):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            path = os.path.join(dirpath, name)
            if any(token in path for token in excludes):
                continue
            if os.path.splitext(name)[1].lower() in SOURCE_EXT:
                yield path


def scan(root, excludes=()):
    """返回 {类别: {'code': [(文件:行, 内容)], 'doc': [...]}}。"""
    hits = {key: {"code": [], "doc": []} for key in PATTERNS}
    cjk_total = 0
    ascii_total = 0
    for path in iter_source_files(root, excludes):
        is_doc = os.path.splitext(path)[1].lower() in (".md", ".txt")
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                lines = handle.readlines()
        except OSError:
            continue
        if len(lines) > 4000:
            continue
        for no, line in enumerate(lines, start=1):
            if is_doc:
                cjk_total += len(CJK_RE.findall(line))
                ascii_total += len(line)
            for key, (pattern, _) in PATTERNS.items():
                if re.search(pattern, line, re.I):
                    rel = os.path.relpath(path, root)
                    hits[key]["doc" if is_doc else "code"].append(("%s:%d" % (rel, no), line.strip()[:120]))
    language = "中文为主" if cjk_total > 0 and cjk_total / max(1, ascii_total) > 0.15 else "英文为主"
    return hits, language


def best_evidence(hits, key):
    """优先取代码/提示词命中；只有文档提及时标记出来。"""
    if hits[key]["code"]:
        return hits[key]["code"][0][0], False
    if hits[key]["doc"]:
        return hits[key]["doc"][0][0], True
    return None, False


def count_prompt_lines(hits):
    """粗略估计提示词规模（命中行数）。"""
    return len(hits["system_prompt"]["code"]) + len(hits["system_prompt"]["doc"])


def recommend(hits, language):
    """基于调研事实推断默认方案。"""
    plan = []

    prompt, prompt_doc = best_evidence(hits, "system_prompt")
    if prompt and not prompt_doc:
        plan.append(("现有提示词", "已存在（%s），沿用现有块命名与顺序，只补缺失部分" % prompt))
    elif prompt:
        plan.append(("现有提示词", "仅在文档中提及（%s），需确认运行时实际提示词位置" % prompt))
    else:
        plan.append(("现有提示词", "未发现，按 assets/system_prompt_template.md 新建"))

    tools_code = len(hits["tools"]["code"])
    if tools_code >= 20:
        plan.append(("工具治理", "工具数量约 %d（超过 20），默认采用渐进式披露（tool_search / defer_loading）" % tools_code))
    elif tools_code:
        plan.append(("工具治理", "工具数量约 %d，可全量放入静态前缀；按 tool-design.md 补齐四类描述信息" % tools_code))
    else:
        plan.append(("工具治理", "未发现工具定义，需确认工具清单"))

    dynamic, dynamic_doc = best_evidence(hits, "dynamic_fields")
    if dynamic and not dynamic_doc:
        plan.append(("静态前缀风险", "提示词中疑似存在动态字段（%s），需移到 user 消息，否则 KV Cache 前缀失效" % dynamic))
    else:
        plan.append(("静态前缀风险", "未发现明显动态字段，交付前用 check_prefix_stability.py 复核"))

    few, few_doc = best_evidence(hits, "few_shot")
    if few and not few_doc:
        plan.append(("few-shot", "已存在（%s），检查是否超过 3 组、是否有边界覆盖，重复度高的应精简" % few))
    else:
        plan.append(("few-shot", "未发现；仅在风格/格式难以用规则描述时才补 2-3 组"))

    defense, defense_doc = best_evidence(hits, "injection_defense")
    if defense and not defense_doc:
        plan.append(("注入防御", "已有来源标记相关实现（%s），沿用并补齐高风险确认环节" % defense))
    else:
        plan.append(("注入防御", "未发现来源标记，需补 external_content 包裹与高风险操作确认"))

    rules_code = len(hits["business_rules"]["code"])
    plan.append(("业务规则", "代码中命中 %d 处规则实现，优先从这里提取可判定条件与阈值" % rules_code if rules_code
                 else "代码中未发现规则实现，需从产品文档或线上失败案例中提取"))
    plan.append(("语言", "跟随项目现有语言：%s" % language))
    return plan


def report(root, hits, language, plan, as_json):
    if as_json:
        print(json.dumps({
            "root": root,
            "language": language,
            "hits": {k: {"code": v["code"][:5], "doc": v["doc"][:5]} for k, v in hits.items()},
            "recommended_plan": [{"item": k, "value": v} for k, v in plan],
        }, ensure_ascii=False, indent=2))
        return

    print("=" * 62)
    print("提示词项目调研：" + root)
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
    print("-" * 62)
    print("项目语言：" + language)
    print("推断的默认方案：")
    for item, value in plan:
        print("  · %s：%s" % (item, value))
    print("-" * 62)
    print("下一步：把以上事实填入 assets/requirements_intake.md 第 1、2 部分，")
    print("        只有业务判定口径、产品取舍、权限边界类问题才列入第 3 部分找用户确认。")


def main():
    parser = argparse.ArgumentParser(description="从项目里勘察系统提示词设计所需事实并给出默认方案")
    parser.add_argument("project", help="项目目录")
    parser.add_argument("--exclude", action="append", default=[],
                        help="排除路径子串（可重复），用于跳过工具自身或非业务代码")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出")
    args = parser.parse_args()

    if not os.path.isdir(args.project):
        print("目录不存在：" + args.project)
        return 2
    try:
        hits, language = scan(args.project, args.exclude)
    except OSError as error:
        print("读取失败：" + str(error))
        return 2

    plan = recommend(hits, language)
    report(args.project, hits, language, plan, args.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
