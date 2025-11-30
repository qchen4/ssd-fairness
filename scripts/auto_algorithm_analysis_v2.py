#!/usr/bin/env python3
"""
自动算法分析系统 v2

发现：Request/Byte Fairness 无法区分算法（所有请求最终都完成）
重点关注：Latency Fairness 和 Slowdown Fairness

分析流程：
1. 运行 4 种算法
2. 计算 Latency Fairness 和 Slowdown Fairness
3. 根据工作负载特征确定应该优化哪个指标
4. 建立 特征 → 最佳算法 映射
"""

import subprocess
import csv
import math
import tempfile
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List
import json


@dataclass
class WorkloadFeatures:
    name: str
    num_users: int
    size_ratio: float
    rw_variance: float
    has_pure_read: bool
    has_pure_write: bool
    has_burst: bool
    read_ratio: float


@dataclass
class Metrics:
    latency_fairness: float
    slowdown_fairness: float


def run_sim(trace: str, scheduler: str, quantum: int = None) -> Dict:
    cmd = [".\\build\\Release\\ssd-fairness.exe", 
           "--trace", trace, "--scheduler", scheduler]
    if quantum and scheduler == "drr":
        cmd.extend(["--quantum", str(quantum)])
    subprocess.run(cmd, capture_output=True, text=True)
    
    user_data = {}
    if Path("results/results.csv").exists():
        with open("results/results.csv", 'r') as f:
            for row in csv.DictReader(f):
                uid = int(row['user_id'])
                user_data[uid] = {'avg_latency': float(row['avg_latency_s'])}
    return user_data


def jain_index(values: List[float]) -> float:
    values = [v for v in values if v > 0]
    if len(values) < 2:
        return 1.0
    n = len(values)
    return (sum(values) ** 2) / (n * sum(v*v for v in values))


def extract_features(trace_path: str) -> WorkloadFeatures:
    users = {}
    sizes = []
    timestamps = {}
    
    with open(trace_path, 'r') as f:
        for row in csv.DictReader(f):
            uid = int(row['user_id'])
            size = int(row['size'])
            ts = int(row['timestamp'])
            is_read = row['type'].upper() == 'READ'
            
            sizes.append(size)
            timestamps[ts] = timestamps.get(ts, 0) + 1
            if uid not in users:
                users[uid] = {'reads': 0, 'writes': 0}
            if is_read:
                users[uid]['reads'] += 1
            else:
                users[uid]['writes'] += 1
    
    size_ratio = max(sizes) / min(sizes) if min(sizes) > 0 else 1.0
    
    total_r = sum(u['reads'] for u in users.values())
    total_w = sum(u['writes'] for u in users.values())
    read_ratio = total_r / (total_r + total_w) if (total_r + total_w) > 0 else 0.5
    
    ratios = []
    has_pure_read = has_pure_write = False
    for u in users.values():
        t = u['reads'] + u['writes']
        r = u['reads'] / t if t > 0 else 0.5
        ratios.append(r)
        if r > 0.95: has_pure_read = True
        if r < 0.05: has_pure_write = True
    
    avg = sum(ratios) / len(ratios)
    rw_var = sum((r - avg)**2 for r in ratios) / len(ratios)
    
    max_concurrent = max(timestamps.values()) if timestamps else 0
    has_burst = max_concurrent > len(users) * 2
    
    return WorkloadFeatures(
        name=Path(trace_path).stem,
        num_users=len(users),
        size_ratio=size_ratio,
        rw_variance=rw_var,
        has_pure_read=has_pure_read,
        has_pure_write=has_pure_write,
        has_burst=has_burst,
        read_ratio=read_ratio
    )


def calc_metrics(trace: str, algo: str, quantum: int = None) -> Metrics:
    temp_dir = Path(tempfile.gettempdir()) / "ssd_v2"
    temp_dir.mkdir(exist_ok=True)
    
    # Shared run
    shared = run_sim(trace, algo, quantum)
    if not shared:
        return Metrics(0, 0)
    
    # Latency Fairness
    inv_lat = [1.0 / d['avg_latency'] if d['avg_latency'] > 0 else 0 for d in shared.values()]
    lat_fairness = jain_index(inv_lat)
    
    # Slowdown Fairness
    user_rows = {}
    with open(trace, 'r') as f:
        for row in csv.DictReader(f):
            uid = int(row['user_id'])
            if uid not in user_rows:
                user_rows[uid] = []
            user_rows[uid].append(row)
    
    alone = {}
    for uid, rows in user_rows.items():
        out = temp_dir / f"alone_{uid}.csv"
        with open(out, 'w', newline='') as f:
            w = csv.DictWriter(f, ["timestamp", "process_id", "user_id", "type", "address", "size"])
            w.writeheader()
            for r in rows:
                r2 = dict(r)
                r2['user_id'] = 0
                w.writerow(r2)
        data = run_sim(str(out), algo, quantum)
        alone[uid] = data.get(0, {}).get('avg_latency', 0.0001)
    
    slowdowns = []
    for uid in shared:
        if alone.get(uid, 0) > 0:
            slowdowns.append(shared[uid]['avg_latency'] / alone[uid])
        else:
            slowdowns.append(1.0)
    
    slow_fairness = min(slowdowns) / max(slowdowns) if slowdowns and max(slowdowns) > 0 else 1.0
    
    return Metrics(lat_fairness, slow_fairness)


def analyze_all_traces():
    print("=" * 80)
    print("          自动算法分析 v2 - 专注于有区分度的指标")
    print("=" * 80)
    print()
    print("指标说明:")
    print("  - Latency Fairness: Jain(1/latency) - 延迟越均衡越好")
    print("  - Slowdown Fairness: min(S)/max(S) - 减速越均衡越好")
    print()
    
    traces = []
    for p in ["traces/validation/*.csv", "traces/competition/*.csv", "traces/contention/*.csv"]:
        traces.extend(Path(".").glob(p))
    traces = sorted(set(traces))[:25]
    
    print(f"分析 {len(traces)} 个 traces...\n")
    
    results = []
    
    # Header
    print("-" * 110)
    print(f"{'Trace':<30} | {'Features':<25} | {'Lat Best':<10} | {'Slow Best':<10} | Recommended")
    print("-" * 110)
    
    for trace in traces:
        features = extract_features(str(trace))
        quantum = int(math.sqrt(features.size_ratio * 4096 * 4096))  # Approximate
        
        metrics = {}
        for algo in ["rr", "drr", "qfq", "flin"]:
            q = quantum if algo == "drr" else None
            metrics[algo] = calc_metrics(str(trace), algo, q)
        
        # Find best for each metric
        best_lat = max(metrics.keys(), key=lambda a: metrics[a].latency_fairness)
        best_slow = max(metrics.keys(), key=lambda a: metrics[a].slowdown_fairness)
        
        # Determine recommendation based on workload type
        # 如果有纯读/写用户或读写差异大 → 用 Slowdown 指标
        # 否则 → 用 Latency 指标
        if features.has_pure_read or features.has_pure_write or features.rw_variance > 0.05:
            recommended = best_slow
            reason = "slowdown"
        else:
            recommended = best_lat
            reason = "latency"
        
        # Feature summary
        feat_str = f"sz:{features.size_ratio:.0f}x rw:{features.rw_variance:.2f}"
        if features.has_pure_read:
            feat_str += " PR"
        if features.has_pure_write:
            feat_str += " PW"
        if features.has_burst:
            feat_str += " B"
        
        print(f"{features.name:<30} | {feat_str:<25} | {best_lat.upper():<10} | {best_slow.upper():<10} | {recommended.upper()} ({reason})")
        
        results.append({
            'trace': features.name,
            'features': {
                'size_ratio': features.size_ratio,
                'rw_variance': features.rw_variance,
                'has_pure_read': features.has_pure_read,
                'has_pure_write': features.has_pure_write,
                'has_burst': features.has_burst,
            },
            'metrics': {algo: {'lat': m.latency_fairness, 'slow': m.slowdown_fairness} 
                       for algo, m in metrics.items()},
            'best_latency': best_lat,
            'best_slowdown': best_slow,
            'recommended': recommended,
            'reason': reason
        })
    
    print("-" * 110)
    
    # Statistics
    print("\n" + "=" * 80)
    print("                         统计")
    print("=" * 80)
    
    # Count wins
    lat_wins = {}
    slow_wins = {}
    rec_counts = {}
    
    for r in results:
        lat_wins[r['best_latency']] = lat_wins.get(r['best_latency'], 0) + 1
        slow_wins[r['best_slowdown']] = slow_wins.get(r['best_slowdown'], 0) + 1
        rec_counts[r['recommended']] = rec_counts.get(r['recommended'], 0) + 1
    
    print("\nLatency Fairness 胜出:")
    for algo in ['rr', 'drr', 'qfq', 'flin']:
        print(f"  {algo.upper()}: {lat_wins.get(algo, 0):2d} {'█' * lat_wins.get(algo, 0)}")
    
    print("\nSlowdown Fairness 胜出:")
    for algo in ['rr', 'drr', 'qfq', 'flin']:
        print(f"  {algo.upper()}: {slow_wins.get(algo, 0):2d} {'█' * slow_wins.get(algo, 0)}")
    
    print("\n最终推荐:")
    for algo in ['rr', 'drr', 'qfq', 'flin']:
        print(f"  {algo.upper()}: {rec_counts.get(algo, 0):2d} {'█' * rec_counts.get(algo, 0)}")
    
    # Build recommendation rules
    print("\n" + "=" * 80)
    print("                    推荐规则")
    print("=" * 80)
    
    # Group by features
    groups = {
        'high_size_ratio': [r for r in results if r['features']['size_ratio'] > 4],
        'rw_mixed': [r for r in results if r['features']['rw_variance'] > 0.05],
        'pure_users': [r for r in results if r['features']['has_pure_read'] or r['features']['has_pure_write']],
        'burst': [r for r in results if r['features']['has_burst']],
        'simple': [r for r in results if r['features']['size_ratio'] < 2 and r['features']['rw_variance'] < 0.01],
    }
    
    rules = {}
    for group_name, group_results in groups.items():
        if not group_results:
            continue
        counts = {}
        for r in group_results:
            counts[r['recommended']] = counts.get(r['recommended'], 0) + 1
        best = max(counts.keys(), key=lambda k: counts[k])
        conf = counts[best] / len(group_results)
        rules[group_name] = {'algo': best, 'confidence': conf, 'n': len(group_results)}
    
    labels = {
        'high_size_ratio': '大小差异 > 4x',
        'rw_mixed': '读写差异 > 0.05',
        'pure_users': '纯读/写用户',
        'burst': '突发流量',
        'simple': '简单场景',
    }
    
    print()
    for name, rule in rules.items():
        print(f"  {labels.get(name, name)}:")
        print(f"    → {rule['algo'].upper()} (置信度 {rule['confidence']*100:.0f}%, n={rule['n']})")
    
    # Save
    with open('results/algorithm_analysis_v2.json', 'w') as f:
        json.dump({'results': results, 'rules': rules}, f, indent=2)
    
    print(f"\n结果已保存: results/algorithm_analysis_v2.json")


if __name__ == "__main__":
    analyze_all_traces()

