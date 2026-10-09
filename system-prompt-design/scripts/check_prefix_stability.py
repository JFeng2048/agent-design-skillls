#!/usr/bin/env python3
"""静态前缀字节级稳定性校验。

原理：系统提示词与工具定义共同构成 KV Cache 前缀。只有内容逐字节一致，前缀缓存才会命中。
任何按请求变化的内容（时间戳、用户 ID、动态检索的 few-shot、动态排序的工具列表）都会让缓存持续失效。

用法：
    python check_prefix_stability.py prompt.md
    python check_prefix_stability.py prompt.md --section persona --section billing_policy
    python check_prefix_stability.py requests.jsonl --from-logs
    python check_prefix_stability.py logs/ --from-logs --print-diffs

退出码：0 = 前缀稳定；1 = 存在不稳定；2 = 参数或读取错误。
"""

import argparse
import hashlib
import json
import os
import re
import sys
from collections import OrderedDict


def sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_sections(text):
    """提取 XML 区块内容，返回 name 到内容的映射。"""
    sections = OrderedDict()
    for match in re.finditer(r"<([a-z_][a-z0-9_]*)>(.*?)</\1>", text, re.DOTALL):
        sections.setdefault(match.group(1), match.group(2))
    return sections


def extract_system(record):
    """从一条请求记录中提取静态前缀：system 提示词加 tools 声明。"""
    if not isinstance(record, dict):
        return None
    system = record.get("system")
    if system is None:
        for message in record.get("messages", []) or []:
            if isinstance(message, dict) and message.get("role") == "system":
                system = message.get("content")
                break
    if system is None:
        return None
    if isinstance(system, list):
        system = "\n".join(
            part.get("text", "") if isinstance(part, dict) else str(part) for part in system
        )
    tools = record.get("tools")
    tools_text = json.dumps(tools, ensure_ascii=False, sort_keys=True) if tools else ""
    return str(system) + "\n@@TOOLS@@\n" + tools_text


def read_records(path):
    """读取 JSON 数组、含 requests 字段的对象，或逐行 JSON。"""
    with open(path, "r", encoding="utf-8") as handle:
        content = handle.read()
    stripped = content.lstrip()
    if stripped.startswith("["):
        try:
            for item in json.loads(content):
                yield item
            return
        except json.JSONDecodeError:
            pass
    elif stripped.startswith("{"):
        try:
            data = json.loads(content)
            if isinstance(data, dict):
                if "requests" in data:
                    for item in data["requests"]:
                        yield item
                else:
                    yield data
                return
        except json.JSONDecodeError:
            pass
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def iter_records(path):
    if os.path.isdir(path):
        for name in sorted(os.listdir(path)):
            if name.endswith((".jsonl", ".json", ".log")):
                for record in read_records(os.path.join(path, name)):
                    yield record
    else:
        for record in read_records(path):
            yield record


def report_file_mode(path, sections):
    with open(path, "r", encoding="utf-8") as handle:
        text = handle.read()
    print("=" * 62)
    print("静态前缀指纹（单文件模式）：" + path)
    print("=" * 62)
    print("整文件 sha256：" + sha256_file(path))
    print("字符数：" + str(len(text)))
    print("字节数：" + str(len(text.encode("utf-8"))))
    if sections:
        print("-" * 62)
        found = extract_sections(text)
        for name in sections:
            if name in found:
                body = found[name]
                print("区块 " + name.ljust(22) + " sha256 " + sha256(body)[:16] + "  长度 " + str(len(body)))
            else:
                print("区块 " + name.ljust(22) + " 未找到")
        print("-" * 62)
        print("以上指纹用于版本对比：发布新版本时指纹变化属预期，")
        print("但同一版本内多次请求的指纹必须完全一致。")
    print("结论：已生成基线指纹，请配合 --from-logs 校验线上请求是否一致。")
    return 0


def report_log_mode(path, print_diffs):
    fingerprints = OrderedDict()
    total = 0
    missing = 0
    for record in iter_records(path):
        system = extract_system(record)
        if system is None:
            missing += 1
            continue
        total += 1
        fingerprints.setdefault(sha256(system), []).append(system)

    print("=" * 62)
    print("静态前缀稳定性校验（请求日志模式）：" + path)
    print("=" * 62)
    print("有效请求数：" + str(total))
    if missing:
        print("无法提取 system 的记录数：" + str(missing))
    print("唯一前缀指纹数：" + str(len(fingerprints)))
    if total == 0:
        print("[ERROR] 未解析到任何含 system 字段的请求记录")
        print("结论：不通过")
        return 1
    if len(fingerprints) > 1:
        print()
        print("[ERROR] 前缀不稳定，缓存将持续失效。常见原因：")
        print("  1) few-shot 示例按请求动态检索")
        print("  2) 提示词或工具定义中注入时间戳、用户 ID 等动态字段")
        print("  3) 工具列表顺序随请求变化（未做稳定排序）")
        print("  4) 同一提示词存在多个版本在灰度")
        if print_diffs:
            print()
            for index, item in enumerate(fingerprints.items(), start=1):
                digest, samples = item
                print("--- 变体 " + str(index) + " sha256 " + digest[:16] + " 请求数 " + str(len(samples)) + " ---")
                print(samples[0][:600])
                print()
        print("结论：不通过")
        return 1
    print("结论：通过，所有请求的静态前缀逐字节一致")
    return 0


def main():
    parser = argparse.ArgumentParser(description="静态前缀字节级稳定性校验")
    parser.add_argument("target", help="提示词文件，或 --from-logs 时的请求日志文件/目录")
    parser.add_argument("--from-logs", action="store_true", help="按请求日志模式校验")
    parser.add_argument("--section", action="append", default=[], help="仅输出指定区块指纹（可重复）")
    parser.add_argument("--print-diffs", action="store_true", help="打印差异变体的前缀内容")
    args = parser.parse_args()

    if not os.path.exists(args.target):
        print("路径不存在：" + args.target)
        return 2
    try:
        if args.from_logs:
            return report_log_mode(args.target, args.print_diffs)
        return report_file_mode(args.target, args.section)
    except (OSError, UnicodeDecodeError) as error:
        print("读取失败：" + str(error))
        return 2


if __name__ == "__main__":
    sys.exit(main())
