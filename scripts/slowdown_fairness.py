#!/usr/bin/env python3
"""
FLIN Paper Slowdown-based Fairness Metric

公式来源: FLIN: Enabling Fairness and Enhancing Performance in Modern NVMe SSDs
- S_i = RT_i^shared / RT_i^alone  (slowdown)
- F = min(S_i) / max(S_i)         (fairness, 1 = perfectly fair)

步骤:
1. 为每个用户单独运行 trace (baseline)
2. 所有用户一起运行 (shared)
3. 计算每个用户的 slowdown
4. 计算 F = min/max
"""

import subprocess
import csv
import random
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List
import tempfile
import os


def run_sim(trace: str, scheduler: str, quantum: int = None) -> Dict[str, float]:
    """运行模拟器，返回每用户平均延迟"""
    cmd = [".\\build\\Release\\ssd-fairness.exe", 
           "--trace", trace, "--scheduler", scheduler]
    if quantum and scheduler == "drr":
        cmd.extend(["--quantum", str(quantum)])
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    output = result.stdout + result.stderr
    
    # 解析整体指标
    metrics = {}
    for line in output.split('\n'):
        if ':' in line:
            parts = line.split(':')
            key = parts[0].strip()
            try:
                value = float(parts[1].strip())
                metrics[key] = value
            except:
                pass
    return metrics


def split_trace_by_user(trace_path: str) -> Dict[int, str]:
    """将 trace 按用户分割成单独的 trace 文件"""
    user_rows = {}
    
    with open(trace_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            uid = int(row['user_id'])
            if uid not in user_rows:
                user_rows[uid] = []
            user_rows[uid].append(row)
    
    # 写入临时文件
    user_traces = {}
    temp_dir = Path(tempfile.gettempdir()) / "ssd_fairness_traces"
    temp_dir.mkdir(exist_ok=True)
    
    for uid, rows in user_rows.items():
        # 重新映射 user_id 为 0（单用户场景）
        trace_path_out = temp_dir / f"user_{uid}_alone.csv"
        with open(trace_path_out, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=["timestamp", "process_id", "user_id", "type", "address", "size"])
            writer.writeheader()
            for row in rows:
                new_row = dict(row)
                new_row['user_id'] = 0  # 单用户
                writer.writerow(new_row)
        user_traces[uid] = str(trace_path_out)
    
    return user_traces


def calculate_slowdown_fairness(trace_path: str, scheduler: str, quantum: int = None) -> Dict:
    """
    计算 FLIN 论文的 slowdown-based fairness
    
    Returns:
        dict with slowdowns per user and overall fairness F
    """
    print(f"\n计算 {scheduler.upper()} 的 slowdown fairness...")
    
    # Step 1: 运行完整 trace (shared)
    shared_metrics = run_sim(trace_path, scheduler, quantum)
    shared_avg_latency = shared_metrics.get("Average latency (s)", 0)
    
    # Step 2: 分割 trace 并单独运行每个用户
    user_traces = split_trace_by_user(trace_path)
    
    alone_latencies = {}
    for uid, user_trace in user_traces.items():
        metrics = run_sim(user_trace, scheduler, quantum)
        alone_latencies[uid] = metrics.get("Average latency (s)", 0)
    
    # Step 3: 计算 slowdown
    # 注意：我们需要每用户在 shared 场景下的延迟
    # 当前模拟器只输出整体平均延迟，所以这里用整体延迟近似
    # 理想情况下需要修改模拟器输出每用户延迟
    
    slowdowns = {}
    for uid, alone_lat in alone_latencies.items():
        if alone_lat > 0:
            # 近似：使用整体 shared 延迟代替每用户 shared 延迟
            slowdowns[uid] = shared_avg_latency / alone_lat
        else:
            slowdowns[uid] = 1.0
    
    # Step 4: 计算 F = min/max
    if slowdowns:
        min_s = min(slowdowns.values())
        max_s = max(slowdowns.values())
        fairness = min_s / max_s if max_s > 0 else 1.0
    else:
        fairness = 1.0
    
    return {
        "alone_latencies": alone_latencies,
        "shared_latency": shared_avg_latency,
        "slowdowns": slowdowns,
        "fairness_F": fairness
    }


def test_slowdown_fairness():
    """测试 slowdown fairness 指标"""
    print("=" * 70)
    print("      FLIN Slowdown-based Fairness 评估")
    print("=" * 70)
    print()
    print("公式: S_i = RT_shared / RT_alone")
    print("      F = min(S) / max(S)  [越接近1越公平]")
    
    traces = [
        ("traces/contention/contention_drr_size_gap.csv", "大小差异场景"),
        ("traces/contention/contention_flin_write_storm.csv", "写风暴场景"),
    ]
    
    for trace_path, desc in traces:
        if not Path(trace_path).exists():
            print(f"\n跳过 {desc}: trace 不存在")
            continue
            
        print(f"\n{'='*70}")
        print(f"场景: {desc}")
        print(f"{'='*70}")
        
        # 计算 sqrt quantum
        with open(trace_path) as f:
            sizes = [int(r['size']) for r in csv.DictReader(f)]
        quantum = int((min(sizes) * max(sizes)) ** 0.5)
        
        results = {}
        for algo in ["rr", "drr", "qfq", "flin"]:
            q = quantum if algo == "drr" else None
            results[algo] = calculate_slowdown_fairness(trace_path, algo, q)
        
        # 打印结果
        print(f"\n{'算法':<6} | {'Shared Lat':<12} | {'Slowdowns':<30} | {'F (fairness)':<12}")
        print("-" * 70)
        for algo in ["rr", "drr", "qfq", "flin"]:
            r = results[algo]
            slowdown_str = ", ".join([f"u{k}:{v:.2f}x" for k, v in sorted(r["slowdowns"].items())])
            print(f"{algo.upper():<6} | {r['shared_latency']:<12.4f} | {slowdown_str:<30} | {r['fairness_F']:<12.4f}")
        
        # 分析
        print("\n分析:")
        best_algo = max(results.keys(), key=lambda a: results[a]["fairness_F"])
        print(f"  最公平算法 (F最高): {best_algo.upper()} (F = {results[best_algo]['fairness_F']:.4f})")
        
        worst_algo = min(results.keys(), key=lambda a: results[a]["fairness_F"])
        print(f"  最不公平算法 (F最低): {worst_algo.upper()} (F = {results[worst_algo]['fairness_F']:.4f})")


def main():
    test_slowdown_fairness()
    
    print("\n" + "=" * 70)
    print("结论")
    print("=" * 70)
    print("""
FLIN 论文的 Slowdown-based Fairness 指标:
- 衡量的是"所有用户是否被同等减速"
- 与 Jain's Fairness Index 完全不同
- 更能体现 FLIN 的设计目标

局限性:
- 当前实现使用整体 shared 延迟近似每用户延迟
- 理想情况需要模拟器输出每用户单独延迟
- 建议修改 metrics.cpp 添加 per-user latency 输出
""")


if __name__ == "__main__":
    main()

