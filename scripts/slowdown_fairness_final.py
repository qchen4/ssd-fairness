#!/usr/bin/env python3
"""
FLIN Paper Slowdown-based Fairness - 最终版本

公式 (来自 FLIN 论文):
- S_i = RT_i^shared / RT_i^alone  (每用户 slowdown)
- F = min(S_i) / max(S_i)         (fairness, 越接近 1 越公平)
"""

import subprocess
import csv
import os
from pathlib import Path
from typing import Dict
import tempfile
import shutil


def run_sim_get_per_user_latency(trace: str, scheduler: str, quantum: int = None) -> Dict[int, float]:
    """运行模拟器并获取 per-user 延迟"""
    cmd = [".\\build\\Release\\ssd-fairness.exe", 
           "--trace", trace, 
           "--scheduler", scheduler]
    if quantum and scheduler == "drr":
        cmd.extend(["--quantum", str(quantum)])
    
    subprocess.run(cmd, capture_output=True, text=True)
    
    # 读取结果 CSV
    user_latencies = {}
    results_csv = Path("results/results.csv")
    if results_csv.exists():
        with open(results_csv, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                uid = int(row['user_id'])
                lat = float(row['avg_latency_s'])
                user_latencies[uid] = lat
    
    return user_latencies


def split_trace_by_user(trace_path: str, temp_dir: Path) -> Dict[int, str]:
    """将 trace 按用户分割成单独的 trace"""
    user_rows = {}
    
    with open(trace_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            uid = int(row['user_id'])
            if uid not in user_rows:
                user_rows[uid] = []
            user_rows[uid].append(row)
    
    user_traces = {}
    for uid, rows in user_rows.items():
        trace_out = temp_dir / f"user_{uid}_alone.csv"
        with open(trace_out, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=["timestamp", "process_id", "user_id", "type", "address", "size"])
            writer.writeheader()
            for row in rows:
                new_row = dict(row)
                new_row['user_id'] = 0  # 单用户
                writer.writerow(new_row)
        user_traces[uid] = str(trace_out)
    
    return user_traces


def calculate_slowdown_fairness(trace_path: str, scheduler: str, quantum: int = None) -> Dict:
    """
    计算 FLIN paper 的 slowdown-based fairness
    """
    temp_dir = Path(tempfile.gettempdir()) / "ssd_fairness_slowdown"
    temp_dir.mkdir(exist_ok=True)
    
    # Step 1: 运行完整 trace (shared)
    shared_latencies = run_sim_get_per_user_latency(trace_path, scheduler, quantum)
    
    # Step 2: 运行每个用户单独的 trace (alone)
    user_traces = split_trace_by_user(trace_path, temp_dir)
    
    alone_latencies = {}
    for uid, user_trace in user_traces.items():
        user_lat = run_sim_get_per_user_latency(user_trace, scheduler, quantum)
        if 0 in user_lat:
            alone_latencies[uid] = user_lat[0]
        else:
            alone_latencies[uid] = 0.0
    
    # Step 3: 计算每用户 slowdown
    slowdowns = {}
    for uid in shared_latencies.keys():
        shared_lat = shared_latencies.get(uid, 0)
        alone_lat = alone_latencies.get(uid, 0)
        if alone_lat > 0:
            slowdowns[uid] = shared_lat / alone_lat
        else:
            slowdowns[uid] = 1.0
    
    # Step 4: 计算 F = min/max
    if slowdowns and len(slowdowns) > 1:
        s_values = list(slowdowns.values())
        min_s = min(s_values)
        max_s = max(s_values)
        fairness_F = min_s / max_s if max_s > 0 else 1.0
    else:
        fairness_F = 1.0
    
    return {
        "shared_latencies": shared_latencies,
        "alone_latencies": alone_latencies,
        "slowdowns": slowdowns,
        "fairness_F": fairness_F
    }


def analyze_scenario(trace_path: str, desc: str, quantum: int = None):
    """分析场景"""
    print(f"\n{'='*80}")
    print(f"场景: {desc}")
    print(f"{'='*80}")
    
    results = {}
    for algo in ["rr", "drr", "qfq", "flin"]:
        q = quantum if algo == "drr" else None
        print(f"  测试 {algo.upper()}...", end=" ", flush=True)
        results[algo] = calculate_slowdown_fairness(trace_path, algo, q)
        print(f"F={results[algo]['fairness_F']:.4f}")
    
    # 获取所有用户
    all_users = set()
    for r in results.values():
        all_users.update(r['slowdowns'].keys())
    
    # 打印详细表格
    print(f"\n{'User':<6} | {'Alone Lat':<12} | {'RR':<14} | {'DRR':<14} | {'QFQ':<14} | {'FLIN':<14}")
    print("-" * 90)
    
    for uid in sorted(all_users):
        alone_lat = results['rr']['alone_latencies'].get(uid, 0)
        print(f"U{uid:<5} | {alone_lat:<12.6f}", end="")
        for algo in ["rr", "drr", "qfq", "flin"]:
            r = results[algo]
            shared = r['shared_latencies'].get(uid, 0)
            slowdown = r['slowdowns'].get(uid, 0)
            print(f" | {shared:.4f}s {slowdown:>5.2f}x", end="")
        print()
    
    print("-" * 90)
    print(f"{'F':<6} | {'(min/max)':<12}", end="")
    for algo in ["rr", "drr", "qfq", "flin"]:
        F = results[algo]['fairness_F']
        marker = " ***" if F == max(r['fairness_F'] for r in results.values()) else ""
        print(f" | {F:>14.4f}{marker}", end="")
    print()
    
    # 最佳算法
    best = max(results.keys(), key=lambda a: results[a]['fairness_F'])
    print(f"\n最公平算法 (F 最高): {best.upper()} (F = {results[best]['fairness_F']:.4f})")
    
    # 最低延迟算法
    avg_shared = {a: sum(r['shared_latencies'].values())/len(r['shared_latencies']) if r['shared_latencies'] else 0 
                  for a, r in results.items()}
    best_lat = min(avg_shared.keys(), key=lambda a: avg_shared[a])
    print(f"最低延迟算法: {best_lat.upper()} (avg={avg_shared[best_lat]:.6f}s)")
    
    return results


def main():
    print("=" * 80)
    print("       FLIN Slowdown-based Fairness 评估 (ISCA 2018)")
    print("=" * 80)
    print()
    print("公式 (来自 FLIN 论文):")
    print("  S_i = RT_i^shared / RT_i^alone  (每用户 slowdown)")
    print("  F = min(S_i) / max(S_i)         (fairness, 1 = 完全公平)")
    print()
    print("解释:")
    print("  - F=1.0: 所有用户减速相同 (完全公平)")
    print("  - F→0:   某些用户减速远大于其他用户 (极不公平)")
    
    scenarios = [
        ("traces/contention/contention_drr_size_gap.csv", "大小差异 (4KB vs 256KB)", 32768),
        ("traces/contention/contention_flin_write_storm.csv", "写风暴攻击", None),
        ("traces/contention/contention_flin_read_protect.csv", "读保护场景", None),
    ]
    
    for trace_path, desc, quantum in scenarios:
        if Path(trace_path).exists():
            analyze_scenario(trace_path, desc, quantum)
        else:
            print(f"\n跳过 {desc}: trace 不存在")
    
    print("\n" + "=" * 80)
    print("                          结论")
    print("=" * 80)
    print("""
使用 FLIN 论文的 Slowdown Fairness 指标可以更准确评估:
1. 每个用户因共享资源而产生的相对性能损失
2. 调度器是否公平对待所有用户
3. FLIN 在读写不对称场景下的保护效果

与 Jain's Fairness Index 的区别:
- Jain's: 衡量绝对值的方差 (throughput/latency)
- Slowdown: 衡量相对于"单独运行"的性能损失
""")


if __name__ == "__main__":
    main()

