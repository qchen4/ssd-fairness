#!/usr/bin/env python3
"""
FLIN Paper Slowdown-based Fairness Metric V2

使用 --output 参数获取 per-user 延迟数据

公式:
- S_i = RT_i^shared / RT_i^alone  (slowdown per user)
- F = min(S_i) / max(S_i)         (fairness, 1 = perfectly fair)
"""

import subprocess
import csv
import os
from pathlib import Path
from typing import Dict, List, Tuple
import tempfile


def run_sim_with_csv(trace: str, scheduler: str, output_csv: str, quantum: int = None) -> Dict:
    """运行模拟器并保存 per-user CSV"""
    cmd = [".\\build\\Release\\ssd-fairness.exe", 
           "--trace", trace, 
           "--scheduler", scheduler,
           "--output", output_csv]
    if quantum and scheduler == "drr":
        cmd.extend(["--quantum", str(quantum)])
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    # 读取 per-user CSV
    user_latencies = {}
    if os.path.exists(output_csv):
        with open(output_csv, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                uid = int(row['user_id'])
                lat = float(row['avg_latency_s'])
                user_latencies[uid] = lat
    
    # 解析 stdout 获取整体指标
    output = result.stdout + result.stderr
    metrics = {}
    for line in output.split('\n'):
        if ':' in line:
            parts = line.split(':')
            key = parts[0].strip()
            try:
                metrics[key] = float(parts[1].strip())
            except:
                pass
    metrics['user_latencies'] = user_latencies
    return metrics


def split_trace_by_user(trace_path: str, temp_dir: Path) -> Dict[int, str]:
    """将 trace 按用户分割"""
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
                new_row['user_id'] = 0
                writer.writerow(new_row)
        user_traces[uid] = str(trace_out)
    
    return user_traces


def calculate_slowdown_fairness_v2(trace_path: str, scheduler: str, quantum: int = None) -> Dict:
    """
    计算 FLIN paper 的 slowdown-based fairness (正确版本)
    
    使用真正的 per-user latency
    """
    temp_dir = Path(tempfile.gettempdir()) / "ssd_fairness_v2"
    temp_dir.mkdir(exist_ok=True)
    
    # Step 1: 运行完整 trace (shared) 获取 per-user latency
    shared_csv = temp_dir / f"shared_{scheduler}.csv"
    shared_metrics = run_sim_with_csv(trace_path, scheduler, str(shared_csv), quantum)
    shared_user_lat = shared_metrics.get('user_latencies', {})
    
    # Step 2: 运行每个用户单独的 trace (alone)
    user_traces = split_trace_by_user(trace_path, temp_dir)
    
    alone_user_lat = {}
    for uid, user_trace in user_traces.items():
        alone_csv = temp_dir / f"alone_{scheduler}_u{uid}.csv"
        metrics = run_sim_with_csv(user_trace, scheduler, str(alone_csv), quantum)
        user_lats = metrics.get('user_latencies', {})
        if 0 in user_lats:  # user_id 被映射为 0
            alone_user_lat[uid] = user_lats[0]
        else:
            alone_user_lat[uid] = 0.0
    
    # Step 3: 计算每用户的 slowdown
    slowdowns = {}
    for uid in shared_user_lat.keys():
        shared_lat = shared_user_lat.get(uid, 0)
        alone_lat = alone_user_lat.get(uid, 0)
        if alone_lat > 0:
            slowdowns[uid] = shared_lat / alone_lat
        else:
            slowdowns[uid] = 1.0
    
    # Step 4: 计算 F = min/max
    if slowdowns:
        s_values = [s for s in slowdowns.values() if s > 0]
        if len(s_values) >= 2:
            min_s = min(s_values)
            max_s = max(s_values)
            fairness_F = min_s / max_s if max_s > 0 else 1.0
        else:
            fairness_F = 1.0
    else:
        fairness_F = 1.0
    
    return {
        "shared_user_latencies": shared_user_lat,
        "alone_user_latencies": alone_user_lat,
        "slowdowns": slowdowns,
        "fairness_F": fairness_F,
        "shared_avg_latency": shared_metrics.get("Average latency (s)", 0)
    }


def analyze_scenario(trace_path: str, desc: str, quantum: int = None):
    """分析一个场景"""
    print(f"\n{'='*70}")
    print(f"场景: {desc}")
    print(f"{'='*70}")
    
    results = {}
    for algo in ["rr", "drr", "qfq", "flin"]:
        q = quantum if algo == "drr" else None
        print(f"  测试 {algo.upper()}...", end=" ", flush=True)
        results[algo] = calculate_slowdown_fairness_v2(trace_path, algo, q)
        print(f"F={results[algo]['fairness_F']:.4f}")
    
    # 打印详细表格
    print(f"\n{'用户':<6}", end="")
    for algo in ["rr", "drr", "qfq", "flin"]:
        print(f" | {algo.upper():^22}", end="")
    print("\n" + "-" * 110)
    
    # 获取所有用户
    all_users = set()
    for r in results.values():
        all_users.update(r['slowdowns'].keys())
    
    for uid in sorted(all_users):
        print(f"User {uid:<2}", end="")
        for algo in ["rr", "drr", "qfq", "flin"]:
            r = results[algo]
            shared = r['shared_user_latencies'].get(uid, 0)
            alone = r['alone_user_latencies'].get(uid, 0)
            slowdown = r['slowdowns'].get(uid, 0)
            print(f" | {shared:.4f}s/{alone:.4f}s={slowdown:>6.2f}x", end="")
        print()
    
    print("-" * 110)
    print(f"{'F':<6}", end="")
    for algo in ["rr", "drr", "qfq", "flin"]:
        F = results[algo]['fairness_F']
        print(f" | {F:^22.4f}", end="")
    print()
    
    # 找出最佳算法
    best = max(results.keys(), key=lambda a: results[a]['fairness_F'])
    print(f"\n最公平算法: {best.upper()} (F = {results[best]['fairness_F']:.4f})")
    
    return results


def main():
    print("=" * 70)
    print("   FLIN Slowdown-based Fairness 评估 (Per-User Latency)")
    print("=" * 70)
    print()
    print("公式: S_i = RT_i^shared / RT_i^alone (每用户减速)")
    print("      F = min(S) / max(S) (越接近1越公平)")
    print()
    print("F=1.0: 所有用户减速相同 (完全公平)")
    print("F→0:  某些用户减速远超其他 (极不公平)")
    
    scenarios = [
        ("traces/contention/contention_drr_size_gap.csv", "大小差异场景", 32768),
        ("traces/contention/contention_flin_write_storm.csv", "写风暴场景", None),
        ("traces/contention/contention_flin_read_protect.csv", "读保护场景", None),
    ]
    
    for trace_path, desc, quantum in scenarios:
        if Path(trace_path).exists():
            analyze_scenario(trace_path, desc, quantum)
        else:
            print(f"\n跳过 {desc}: {trace_path} 不存在")
    
    print("\n" + "=" * 70)
    print("                       结论")
    print("=" * 70)
    print("""
FLIN Paper 的 Slowdown Fairness 指标优势:
1. 直接衡量每个用户因共享而产生的"痛苦"
2. F = min/max 确保最坏情况用户不会太差
3. 更适合评估 FLIN 这类保护性调度器

关键发现:
- 当所有用户减速比例相近时，F 接近 1
- 当某用户被"欺负"（减速远大于其他人）时，F 接近 0
- FLIN 应该在读写不对称场景下提高 F
""")


if __name__ == "__main__":
    main()

