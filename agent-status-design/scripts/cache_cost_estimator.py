#!/usr/bin/env python3
"""状态更新策略的缓存成本估算：每轮替换 vs 持久追加。

模型（见 references/update-strategies.md）：
    S = 每条状态消息的 token 数
    R = 两次更新之间新增后缀的 token 数
    N = 预计更新次数
    alpha = 缓存输入单价相对普通输入的倍数（缓存更便宜，alpha < 1）

    C_replace ≈ (N - 1) * (1 - alpha) * R
    C_append  ≈ alpha * S * N * (N - 1) / 2

判定：当 alpha * S * N / 2 < (1 - alpha) * R 时倾向持久追加，否则倾向每轮替换。

用法：
    python cache_cost_estimator.py --s 60 --r 800 --n 12 --alpha 0.1
    python cache_cost_estimator.py --s 60 --r 800 --n 12 --json
    python cache_cost_estimator.py --s 60 --r 800 --n 12 --sweep-n 2 40
    python cache_cost_estimator.py --s 60 --n 12 --sweep-r 100 3000 --step 100

退出码始终为 0（纯计算工具）。
"""

import argparse
import json
import sys


def replace_cost(s, r, n, alpha):
    """每轮替换：移除旧状态使上次注入后的后缀失效。"""
    return max(n - 1, 0) * (1.0 - alpha) * r


def append_cost(s, r, n, alpha):
    """持久追加：陈旧状态累积，每轮都要为已累积的状态付缓存读取费。"""
    return alpha * s * n * (n - 1) / 2.0


def recommend(s, r, n, alpha):
    """当 alpha*S*N/2 < (1-alpha)*R 时倾向追加。"""
    left = alpha * s * n / 2.0
    right = (1.0 - alpha) * r
    return "持久追加" if left < right else "每轮替换", left, right


def human(value):
    if value >= 1_000_000:
        return "%.2fM" % (value / 1_000_000.0)
    if value >= 1000:
        return "%.2fK" % (value / 1000.0)
    return "%.1f" % value


def report(s, r, n, alpha, as_json):
    c_replace = replace_cost(s, r, n, alpha)
    c_append = append_cost(s, r, n, alpha)
    choice, left, right = recommend(s, r, n, alpha)

    if as_json:
        print(json.dumps({
            "S": s, "R": r, "N": n, "alpha": alpha,
            "C_replace": c_replace, "C_append": c_append,
            "left": left, "right": right, "recommend": choice,
        }, ensure_ascii=False))
        return

    print("=" * 62)
    print("状态更新策略成本估算")
    print("=" * 62)
    print("输入：S=%d token（单条状态）  R=%d token（轮间新增后缀）" % (s, r))
    print("      N=%d 次（预计更新）      alpha=%.2f（缓存单价倍数）" % (n, alpha))
    print("-" * 62)
    print("C_replace ≈ (N-1)(1-alpha)R      = %s token 等价成本" % human(c_replace))
    print("C_append  ≈ alpha*S*N(N-1)/2     = %s token 等价成本" % human(c_append))
    print("-" * 62)
    print("判定式：alpha*S*N/2 = %s   vs   (1-alpha)*R = %s" % (human(left), human(right)))
    print("结论：倾向「%s」" % choice)
    if choice == "持久追加":
        print("说明：状态很小或轮间新增很多，保留旧状态比反复重算长后缀便宜。")
        print("注意：需在系统提示词中写明「以最后一条状态栏为准」，并要求模型忽略陈旧状态。")
    else:
        print("说明：状态较大或更新频繁，替换只使上次注入后的短后缀失效，且避免陈旧状态累积。")
    print("提示：本模型未计上下文占用与陈旧状态歧义，请以实测命中率校准。")


def sweep(flag, start, end, step, s, r, n, alpha):
    print("=" * 62)
    print("扫描 %s：%d → %d（步长 %d），其余参数 S=%d R=%d N=%d alpha=%.2f"
          % (flag, start, end, step, s, r, n, alpha))
    print("=" * 62)
    print(flag.ljust(8) + "C_replace".rjust(12) + "C_append".rjust(12) + "  建议")
    crossover = None
    previous = None
    for value in range(start, end + 1, step):
        cur_s, cur_r, cur_n = s, r, n
        if flag == "N":
            cur_n = value
        elif flag == "R":
            cur_r = value
        else:
            cur_s = value
        choice, _, _ = recommend(cur_s, cur_r, cur_n, alpha)
        print(str(value).ljust(8)
              + human(replace_cost(cur_s, cur_r, cur_n, alpha)).rjust(12)
              + human(append_cost(cur_s, cur_r, cur_n, alpha)).rjust(12)
              + "  " + choice)
        if previous and previous != choice:
            crossover = value
        previous = choice
    if crossover:
        print("-" * 62)
        print("分界点约在 %s = %d 附近，需结合实测校准。" % (flag, crossover))


def main():
    parser = argparse.ArgumentParser(description="状态更新策略的缓存成本估算")
    parser.add_argument("--s", type=int, default=60, help="单条状态消息 token 数 S（默认 60）")
    parser.add_argument("--r", type=int, default=800, help="两次更新间新增后缀 token 数 R（默认 800）")
    parser.add_argument("--n", type=int, default=12, help="预计更新次数 N（默认 12）")
    parser.add_argument("--alpha", type=float, default=0.1, help="缓存输入单价倍数 alpha（默认 0.1）")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出")
    parser.add_argument("--sweep-n", nargs=2, type=int, metavar=("START", "END"), help="扫描 N 区间")
    parser.add_argument("--sweep-r", nargs=2, type=int, metavar=("START", "END"), help="扫描 R 区间")
    parser.add_argument("--sweep-s", nargs=2, type=int, metavar=("START", "END"), help="扫描 S 区间")
    parser.add_argument("--step", type=int, default=1, help="扫描步长（默认 1）")
    args = parser.parse_args()

    if args.sweep_n:
        sweep("N", args.sweep_n[0], args.sweep_n[1], args.step, args.s, args.r, args.n, args.alpha)
    elif args.sweep_r:
        sweep("R", args.sweep_r[0], args.sweep_r[1], args.step, args.s, args.r, args.n, args.alpha)
    elif args.sweep_s:
        sweep("S", args.sweep_s[0], args.sweep_s[1], args.step, args.s, args.r, args.n, args.alpha)
    else:
        report(args.s, args.r, args.n, args.alpha, args.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
