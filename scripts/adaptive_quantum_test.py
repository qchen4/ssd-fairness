#!/usr/bin/env python3
"""
自适应 Quantum 测试

根据工作负载特征自动选择最优 quantum 值。
"""

import argparse
import csv
import math
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple
from collections import defaultdict
from dataclasses import dataclass


@dataclass
class WorkloadStats:
    """工作负载统计"""
    min_size: int
    max_size: int
    avg_size: float
    size_ratio: float  # max/min
    sizes: List[int]
    
    # 每用户统计
    user_request_counts: Dict[int, int]
    user_total_bytes: Dict[int, int]
    user_avg_sizes: Dict[int, float]
    
    # 频率相关
    freq_variance: float  # 请求频率方差
    freq_cv: float  # 变异系数 (std/mean)
    
    # 大小分布
    size_variance: float
    size_cv: float


def analyze_trace(trace_path: Path) -> WorkloadStats:
    """分析 trace 文件，提取工作负载特征"""
    sizes = []
    user_requests = defaultdict(list)
    user_timestamps = defaultdict(list)
    
    with open(trace_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            size = int(row['size'])
            user_id = int(row['user_id'])
            timestamp = int(row['timestamp'])
            
            sizes.append(size)
            user_requests[user_id].append(size)
            user_timestamps[user_id].append(timestamp)
    
    if not sizes:
        raise ValueError(f"Empty trace: {trace_path}")
    
    # 基本大小统计
    min_size = min(sizes)
    max_size = max(sizes)
    avg_size = sum(sizes) / len(sizes)
    size_ratio = max_size / min_size if min_size > 0 else 1
    
    # 大小方差
    size_mean = avg_size
    size_variance = sum((s - size_mean) ** 2 for s in sizes) / len(sizes)
    size_std = math.sqrt(size_variance)
    size_cv = size_std / size_mean if size_mean > 0 else 0
    
    # 每用户统计
    user_request_counts = {uid: len(reqs) for uid, reqs in user_requests.items()}
    user_total_bytes = {uid: sum(reqs) for uid, reqs in user_requests.items()}
    user_avg_sizes = {uid: sum(reqs)/len(reqs) for uid, reqs in user_requests.items()}
    
    # 频率统计（请求数量的方差）
    counts = list(user_request_counts.values())
    if len(counts) > 1:
        count_mean = sum(counts) / len(counts)
        freq_variance = sum((c - count_mean) ** 2 for c in counts) / len(counts)
        freq_std = math.sqrt(freq_variance)
        freq_cv = freq_std / count_mean if count_mean > 0 else 0
    else:
        freq_variance = 0
        freq_cv = 0
    
    return WorkloadStats(
        min_size=min_size,
        max_size=max_size,
        avg_size=avg_size,
        size_ratio=size_ratio,
        sizes=sorted(set(sizes)),
        user_request_counts=user_request_counts,
        user_total_bytes=user_total_bytes,
        user_avg_sizes=user_avg_sizes,
        freq_variance=freq_variance,
        freq_cv=freq_cv,
        size_variance=size_variance,
        size_cv=size_cv,
    )


def calculate_adaptive_quantum(stats: WorkloadStats) -> Tuple[int, str]:
    """
    根据工作负载特征计算自适应 quantum
    
    返回: (quantum_bytes, reason)
    
    简化策略: 统一使用 sqrt(min * max)
    """
    sqrt_q = int(math.sqrt(stats.min_size * stats.max_size))
    
    # 确保 quantum 至少等于最小请求大小
    if sqrt_q < stats.min_size:
        sqrt_q = stats.min_size
    
    reason = f"sqrt({stats.min_size//1024}KB * {stats.max_size//1024}KB) = {sqrt_q//1024:.1f}KB"
    
    return sqrt_q, reason


def run_simulation(binary: Path, trace: Path, scheduler: str, quantum: int = None) -> Dict:
    """运行模拟并解析结果"""
    cmd = [str(binary), "--trace", str(trace), "--scheduler", scheduler]
    if quantum is not None:
        cmd.extend(["--quantum", str(quantum)])
    
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    
    metrics = {}
    for line in result.stdout.splitlines():
        if line.startswith("Fairness Index (combined):"):
            metrics["combined"] = float(line.split(":")[1].strip())
        elif line.startswith("Fairness Index (throughput):"):
            metrics["throughput"] = float(line.split(":")[1].strip())
        elif line.startswith("Fairness Index (latency):"):
            metrics["latency"] = float(line.split(":")[1].strip())
        elif line.startswith("Completed requests:"):
            parts = line.split()
            metrics["completed"] = int(parts[2])
    
    return metrics


def test_adaptive_quantum(binary: Path, traces_dir: Path) -> None:
    """测试自适应 quantum"""
    
    traces = sorted(traces_dir.glob("*.csv"))
    
    print("=" * 80)
    print("                    自适应 Quantum 测试")
    print("=" * 80)
    
    results = []
    
    for trace in traces:
        print(f"\n{'─' * 80}")
        print(f"场景: {trace.stem}")
        print(f"{'─' * 80}")
        
        # 分析工作负载
        stats = analyze_trace(trace)
        print(f"  请求大小: {stats.min_size/1024:.0f}KB - {stats.max_size/1024:.0f}KB (ratio={stats.size_ratio:.1f})")
        print(f"  大小分布: {[f'{s//1024}KB' for s in stats.sizes]}")
        print(f"  用户请求数: {dict(stats.user_request_counts)}")
        print(f"  频率CV: {stats.freq_cv:.3f}, 大小CV: {stats.size_cv:.3f}")
        
        # 计算自适应 quantum
        adaptive_q, reason = calculate_adaptive_quantum(stats)
        print(f"\n  自适应策略: {reason}")
        print(f"  选择 quantum = {adaptive_q/1024:.1f}KB")
        
        # 测试不同 quantum 值
        test_quantums = [
            ("4KB (默认)", 4096),
            ("sqrt", int(math.sqrt(stats.min_size * stats.max_size))),
            ("max/4", stats.max_size // 4),
            ("自适应", adaptive_q),
        ]
        
        # 去重
        seen = set()
        unique_quantums = []
        for name, q in test_quantums:
            if q not in seen:
                seen.add(q)
                unique_quantums.append((name, q))
        
        print(f"\n  Quantum 对比测试:")
        best_fairness = 0
        best_name = ""
        
        for name, q in unique_quantums:
            metrics = run_simulation(binary, trace, "drr", q)
            fairness = metrics.get("combined", 0)
            marker = ""
            if fairness > best_fairness:
                best_fairness = fairness
                best_name = name
            print(f"    {name:12s} (q={q//1024:3d}KB): fairness={fairness:.4f}, completed={metrics.get('completed', 0)}")
        
        # 与其他算法对比
        print(f"\n  与其他算法对比 (DRR用自适应quantum):")
        algo_results = {}
        for algo in ["rr", "drr", "qfq", "flin"]:
            if algo == "drr":
                metrics = run_simulation(binary, trace, algo, adaptive_q)
            else:
                metrics = run_simulation(binary, trace, algo)
            algo_results[algo] = metrics.get("combined", 0)
            print(f"    {algo.upper():5s}: {metrics.get('combined', 0):.4f}")
        
        winner = max(algo_results, key=algo_results.get)
        adaptive_rank = sorted(algo_results.values(), reverse=True).index(algo_results["drr"]) + 1
        
        print(f"\n  结果: 胜者={winner.upper()}, DRR排名={adaptive_rank}/4")
        
        results.append({
            "trace": trace.stem,
            "adaptive_quantum": adaptive_q,
            "winner": winner,
            "drr_rank": adaptive_rank,
            "drr_fairness": algo_results["drr"],
        })
    
    # 总结
    print(f"\n{'=' * 80}")
    print("                         总结")
    print(f"{'=' * 80}")
    
    drr_wins = sum(1 for r in results if r["winner"] == "drr")
    drr_top2 = sum(1 for r in results if r["drr_rank"] <= 2)
    
    print(f"\n  DRR (自适应quantum) 胜出: {drr_wins}/{len(results)} 场景")
    print(f"  DRR 进入前2: {drr_top2}/{len(results)} 场景")
    
    print(f"\n  详细结果:")
    for r in results:
        status = "✓" if r["winner"] == "drr" else ("~" if r["drr_rank"] <= 2 else "✗")
        print(f"    [{status}] {r['trace']}: quantum={r['adaptive_quantum']//1024}KB, "
              f"winner={r['winner'].upper()}, DRR={r['drr_fairness']:.4f}")


def main():
    parser = argparse.ArgumentParser(description="测试自适应 quantum")
    parser.add_argument("--binary", default="build/Release/ssd-fairness.exe",
                        help="模拟器路径")
    parser.add_argument("--traces", default="traces/scenarios",
                        help="trace 目录")
    args = parser.parse_args()
    
    binary = Path(args.binary)
    traces_dir = Path(args.traces)
    
    if not binary.exists():
        print(f"错误: 找不到模拟器 {binary}")
        return
    
    if not traces_dir.exists():
        print(f"错误: 找不到 trace 目录 {traces_dir}")
        return
    
    test_adaptive_quantum(binary, traces_dir)


if __name__ == "__main__":
    main()

