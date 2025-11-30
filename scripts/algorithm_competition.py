#!/usr/bin/env python3
"""
四种 SSD 调度算法竞赛

使用 FLIN 论文的 Slowdown Fairness 指标:
- S_i = RT_i^shared / RT_i^alone
- F = min(S) / max(S)  [越接近1越公平]
"""

import subprocess
import csv
import random
import math
from pathlib import Path
from typing import Dict, List, Tuple
import tempfile


def run_sim(trace: str, scheduler: str, quantum: int = None) -> Dict[int, float]:
    """运行模拟器获取 per-user 延迟"""
    cmd = [".\\build\\Release\\ssd-fairness.exe", 
           "--trace", trace, "--scheduler", scheduler]
    if quantum and scheduler == "drr":
        cmd.extend(["--quantum", str(quantum)])
    
    subprocess.run(cmd, capture_output=True, text=True)
    
    user_latencies = {}
    results_csv = Path("results/results.csv")
    if results_csv.exists():
        with open(results_csv, 'r') as f:
            for row in csv.DictReader(f):
                user_latencies[int(row['user_id'])] = float(row['avg_latency_s'])
    return user_latencies


def split_trace(trace_path: str, temp_dir: Path) -> Dict[int, str]:
    """分割 trace"""
    user_rows = {}
    with open(trace_path, 'r') as f:
        for row in csv.DictReader(f):
            uid = int(row['user_id'])
            if uid not in user_rows:
                user_rows[uid] = []
            user_rows[uid].append(row)
    
    traces = {}
    for uid, rows in user_rows.items():
        out = temp_dir / f"u{uid}.csv"
        with open(out, 'w', newline='') as f:
            w = csv.DictWriter(f, ["timestamp", "process_id", "user_id", "type", "address", "size"])
            w.writeheader()
            for r in rows:
                r2 = dict(r)
                r2['user_id'] = 0
                w.writerow(r2)
        traces[uid] = str(out)
    return traces


def calc_slowdown_fairness(trace: str, algo: str, quantum: int = None) -> Tuple[float, Dict]:
    """计算 slowdown fairness"""
    temp_dir = Path(tempfile.gettempdir()) / "ssd_comp"
    temp_dir.mkdir(exist_ok=True)
    
    # Shared
    shared = run_sim(trace, algo, quantum)
    
    # Alone
    user_traces = split_trace(trace, temp_dir)
    alone = {}
    for uid, ut in user_traces.items():
        lat = run_sim(ut, algo, quantum)
        alone[uid] = lat.get(0, 0)
    
    # Slowdowns
    slowdowns = {}
    for uid in shared:
        if alone.get(uid, 0) > 0:
            slowdowns[uid] = shared[uid] / alone[uid]
        else:
            slowdowns[uid] = 1.0
    
    # F = min/max
    if slowdowns and len(slowdowns) > 1:
        F = min(slowdowns.values()) / max(slowdowns.values())
    else:
        F = 1.0
    
    return F, {"shared": shared, "alone": alone, "slowdowns": slowdowns}


def write_trace(rows: List[Dict], path: Path):
    """写入 trace"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, ["timestamp", "process_id", "user_id", "type", "address", "size"])
        w.writeheader()
        for r in sorted(rows, key=lambda x: (x["timestamp"], x["user_id"])):
            w.writerow(r)


def gen_requests(uid, count, ts_start, gap, size, read_ratio, rng):
    """生成请求"""
    rows = []
    ts = ts_start
    addr = uid * (1 << 40)
    for _ in range(count):
        ts += rng.randint(gap[0], gap[1])
        sz = size if isinstance(size, int) else rng.choice(size)
        rows.append({
            "timestamp": ts,
            "process_id": f"u{uid}",
            "user_id": uid,
            "type": "READ" if rng.random() < read_ratio else "WRITE",
            "address": hex(addr),
            "size": sz,
        })
        addr += sz
    return rows


def create_test_scenarios(out_dir: Path, rng: random.Random) -> List[Tuple[str, str, int]]:
    """创建测试场景"""
    scenarios = []
    
    # 1. 均匀场景 (RR 预期胜出)
    rows = []
    for uid in range(4):
        rows.extend(gen_requests(uid, 2000, 0, (10, 20), 4096, 0.5, rng))
    p = out_dir / "s01_uniform.csv"
    write_trace(rows, p)
    scenarios.append((str(p), "均匀请求 (4KB)", None))
    
    # 2. 大小差异 8x (DRR 预期胜出)
    rows = []
    for uid in range(2):
        rows.extend(gen_requests(uid, 4000, 0, (10, 20), 4096, 0.5, rng))
    for uid in range(2, 4):
        rows.extend(gen_requests(uid, 1000, 0, (40, 60), 32768, 0.5, rng))
    p = out_dir / "s02_size_8x.csv"
    write_trace(rows, p)
    scenarios.append((str(p), "大小差异 8x (4KB vs 32KB)", 11585))
    
    # 3. 大小差异 64x (DRR 预期胜出)
    rows = []
    for uid in range(2):
        rows.extend(gen_requests(uid, 5000, 0, (8, 15), 4096, 0.5, rng))
    for uid in range(2, 4):
        rows.extend(gen_requests(uid, 500, 0, (80, 120), 262144, 0.5, rng))
    p = out_dir / "s03_size_64x.csv"
    write_trace(rows, p)
    scenarios.append((str(p), "大小差异 64x (4KB vs 256KB)", 32768))
    
    # 4. 读 vs 写 (FLIN 预期胜出)
    rows = []
    for uid in range(2):
        rows.extend(gen_requests(uid, 3000, 0, (15, 30), 4096, 1.0, rng))  # 纯读
    for uid in range(2, 4):
        rows.extend(gen_requests(uid, 2000, 0, (20, 40), 32768, 0.0, rng))  # 纯写
    p = out_dir / "s04_read_vs_write.csv"
    write_trace(rows, p)
    scenarios.append((str(p), "读 vs 写", None))
    
    # 5. 写风暴 (FLIN 预期胜出)
    rows = []
    for uid in range(3):
        rows.extend(gen_requests(uid, 2000, 0, (20, 40), 4096, 0.95, rng))
    rows.extend(gen_requests(3, 5000, 0, (5, 10), 131072, 0.0, rng))
    p = out_dir / "s05_write_storm.csv"
    write_trace(rows, p)
    scenarios.append((str(p), "写风暴攻击", None))
    
    # 6. 同时突发 (QFQ 预期胜出)
    rows = []
    for uid in range(4):
        for i in range(2000):
            rows.append({
                "timestamp": 0,
                "process_id": f"burst{uid}",
                "user_id": uid,
                "type": "READ",
                "address": hex(uid * (1 << 40) + i * 4096),
                "size": 4096,
            })
    p = out_dir / "s06_simultaneous.csv"
    write_trace(rows, p)
    scenarios.append((str(p), "同时突发", None))
    
    # 7. 高竞争混合大小
    rows = []
    sizes = [4096, 8192, 16384, 32768]
    for uid in range(4):
        rows.extend(gen_requests(uid, 3000, 0, (5, 15), sizes[uid], 0.6, rng))
    p = out_dir / "s07_mixed_sizes.csv"
    write_trace(rows, p)
    scenarios.append((str(p), "混合大小竞争", 16384))
    
    # 8. 频率差异
    rows = []
    rows.extend(gen_requests(0, 6000, 0, (5, 10), 4096, 0.5, rng))  # 高频
    for uid in range(1, 4):
        rows.extend(gen_requests(uid, 1500, 0, (30, 50), 4096, 0.5, rng))  # 低频
    p = out_dir / "s08_frequency_diff.csv"
    write_trace(rows, p)
    scenarios.append((str(p), "频率差异 (高频 vs 低频)", None))
    
    # 9. 读密集
    rows = []
    for uid in range(4):
        rows.extend(gen_requests(uid, 3000, 0, (10, 25), 4096, 0.95, rng))
    p = out_dir / "s09_read_heavy.csv"
    write_trace(rows, p)
    scenarios.append((str(p), "读密集 (95% 读)", None))
    
    # 10. 写密集
    rows = []
    for uid in range(4):
        rows.extend(gen_requests(uid, 2000, 0, (15, 30), 16384, 0.1, rng))
    p = out_dir / "s10_write_heavy.csv"
    write_trace(rows, p)
    scenarios.append((str(p), "写密集 (90% 写)", None))
    
    return scenarios


def run_competition():
    """运行竞赛"""
    print("=" * 80)
    print("          四种 SSD 调度算法竞赛")
    print("          (FLIN Slowdown Fairness 指标)")
    print("=" * 80)
    print()
    print("评分规则: F = min(slowdown) / max(slowdown)")
    print("         F 越接近 1 越公平，获胜")
    print()
    
    rng = random.Random(42)
    out_dir = Path("traces/competition")
    scenarios = create_test_scenarios(out_dir, rng)
    
    algos = ["rr", "drr", "qfq", "flin"]
    wins = {a: 0 for a in algos}
    total_F = {a: 0.0 for a in algos}
    
    results_table = []
    
    for i, (trace, desc, quantum) in enumerate(scenarios, 1):
        print(f"\n{'='*80}")
        print(f"场景 {i}: {desc}")
        print(f"{'='*80}")
        
        F_scores = {}
        details = {}
        for algo in algos:
            q = quantum if algo == "drr" else None
            F, info = calc_slowdown_fairness(trace, algo, q)
            F_scores[algo] = F
            details[algo] = info
            total_F[algo] += F
        
        # 找胜者
        best_F = max(F_scores.values())
        winners = [a for a, f in F_scores.items() if abs(f - best_F) < 0.0001]
        
        # 打印详情
        print(f"\n{'算法':<6} | {'F (fairness)':<14} | slowdowns")
        print("-" * 70)
        for algo in algos:
            slowdowns = details[algo]['slowdowns']
            sd_str = ", ".join([f"u{k}:{v:.1f}x" for k, v in sorted(slowdowns.items())])
            marker = " ★" if algo in winners else ""
            print(f"{algo.upper():<6} | {F_scores[algo]:<14.4f} | {sd_str}{marker}")
        
        # 记录胜者
        for w in winners:
            wins[w] += 1
        
        results_table.append({
            "场景": desc,
            "RR": F_scores["rr"],
            "DRR": F_scores["drr"],
            "QFQ": F_scores["qfq"],
            "FLIN": F_scores["flin"],
            "Winner": "/".join([w.upper() for w in winners])
        })
        
        print(f"\n胜者: {'/'.join([w.upper() for w in winners])} (F = {best_F:.4f})")
    
    # 总结
    print("\n" + "=" * 80)
    print("                      竞赛总结")
    print("=" * 80)
    
    print("\n场景胜出统计:")
    print("-" * 40)
    for algo in sorted(algos, key=lambda a: wins[a], reverse=True):
        bar = "█" * wins[algo]
        print(f"  {algo.upper():<6}: {wins[algo]:>2} 场胜出  {bar}")
    
    print(f"\n平均 F 值:")
    print("-" * 40)
    n = len(scenarios)
    for algo in sorted(algos, key=lambda a: total_F[a], reverse=True):
        avg_F = total_F[algo] / n
        print(f"  {algo.upper():<6}: {avg_F:.4f}")
    
    # 最终排名
    print("\n" + "=" * 80)
    print("                      最终排名")
    print("=" * 80)
    
    # 综合得分: 胜场数 * 10 + 平均F * 100
    scores = {a: wins[a] * 10 + (total_F[a] / n) * 100 for a in algos}
    ranked = sorted(algos, key=lambda a: scores[a], reverse=True)
    
    medals = ["🥇", "🥈", "🥉", "  "]
    for i, algo in enumerate(ranked):
        medal = medals[min(i, 3)]
        print(f"  {medal} {algo.upper():<6}: {wins[algo]} 胜, 平均F={total_F[algo]/n:.4f}, 综合分={scores[algo]:.1f}")
    
    print("\n详细结果表:")
    print("-" * 90)
    print(f"{'场景':<25} | {'RR':>8} | {'DRR':>8} | {'QFQ':>8} | {'FLIN':>8} | {'Winner':<12}")
    print("-" * 90)
    for r in results_table:
        print(f"{r['场景']:<25} | {r['RR']:>8.4f} | {r['DRR']:>8.4f} | {r['QFQ']:>8.4f} | {r['FLIN']:>8.4f} | {r['Winner']:<12}")
    print("-" * 90)


if __name__ == "__main__":
    run_competition()

