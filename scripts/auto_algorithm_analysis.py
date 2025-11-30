#!/usr/bin/env python3
"""
自动算法分析系统

对每个 trace:
1. 运行 4 种算法 (RR, DRR, QFQ, FLIN)
2. 计算 4 种公平性指标
3. 分析工作负载特征
4. 建立 特征 → 最佳算法 的映射关系
"""

import subprocess
import csv
import math
import tempfile
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Tuple
import json


@dataclass
class WorkloadFeatures:
    """工作负载特征"""
    name: str
    num_users: int
    total_requests: int
    min_size: int
    max_size: int
    size_ratio: float
    avg_size: float
    read_ratio: float
    rw_variance: float
    has_pure_read: bool
    has_pure_write: bool
    has_burst: bool
    
    def to_vector(self) -> List[float]:
        """转换为特征向量"""
        return [
            self.num_users,
            math.log10(self.size_ratio + 1),
            self.rw_variance,
            1.0 if self.has_pure_read else 0.0,
            1.0 if self.has_pure_write else 0.0,
            1.0 if self.has_burst else 0.0,
        ]


@dataclass
class AlgorithmMetrics:
    """单个算法的所有指标"""
    request_fairness: float = 0.0  # Jain(requests/user)
    byte_fairness: float = 0.0     # Jain(bytes/user)
    latency_fairness: float = 0.0  # Jain(1/latency)
    slowdown_fairness: float = 0.0 # min(S)/max(S)


@dataclass
class TraceAnalysis:
    """单个 trace 的完整分析结果"""
    trace_name: str
    features: WorkloadFeatures
    metrics: Dict[str, AlgorithmMetrics] = field(default_factory=dict)
    
    # 每个指标的最佳算法
    best_for_request: str = ""
    best_for_byte: str = ""
    best_for_latency: str = ""
    best_for_slowdown: str = ""
    
    # 综合最佳算法 (平均排名)
    overall_best: str = ""


def run_sim(trace: str, scheduler: str, quantum: int = None) -> Dict:
    """运行模拟器"""
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
                user_data[uid] = {
                    'completed': int(row['completed']),
                    'avg_latency': float(row['avg_latency_s']),
                    'total_bytes': int(row['total_bytes'])
                }
    return user_data


def jain_index(values: List[float]) -> float:
    """Jain's Fairness Index"""
    values = [v for v in values if v > 0]
    if len(values) < 2:
        return 1.0
    n = len(values)
    sum_v = sum(values)
    sum_sq = sum(v * v for v in values)
    return (sum_v * sum_v) / (n * sum_sq) if sum_sq > 0 else 1.0


def extract_features(trace_path: str) -> WorkloadFeatures:
    """提取工作负载特征"""
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
    
    # 计算特征
    min_size = min(sizes)
    max_size = max(sizes)
    size_ratio = max_size / min_size if min_size > 0 else 1.0
    
    total_reads = sum(u['reads'] for u in users.values())
    total_writes = sum(u['writes'] for u in users.values())
    read_ratio = total_reads / (total_reads + total_writes) if (total_reads + total_writes) > 0 else 0.5
    
    ratios = []
    has_pure_read = False
    has_pure_write = False
    for u in users.values():
        total = u['reads'] + u['writes']
        r = u['reads'] / total if total > 0 else 0.5
        ratios.append(r)
        if r > 0.95: has_pure_read = True
        if r < 0.05: has_pure_write = True
    
    avg_ratio = sum(ratios) / len(ratios) if ratios else 0.5
    rw_variance = sum((r - avg_ratio)**2 for r in ratios) / len(ratios) if ratios else 0
    
    max_concurrent = max(timestamps.values()) if timestamps else 0
    has_burst = max_concurrent > len(users) * 2
    
    return WorkloadFeatures(
        name=Path(trace_path).stem,
        num_users=len(users),
        total_requests=len(sizes),
        min_size=min_size,
        max_size=max_size,
        size_ratio=size_ratio,
        avg_size=sum(sizes) / len(sizes),
        read_ratio=read_ratio,
        rw_variance=rw_variance,
        has_pure_read=has_pure_read,
        has_pure_write=has_pure_write,
        has_burst=has_burst
    )


def calc_all_metrics(trace: str, algo: str, quantum: int = None) -> AlgorithmMetrics:
    """计算一个算法的所有指标"""
    temp_dir = Path(tempfile.gettempdir()) / "ssd_auto"
    temp_dir.mkdir(exist_ok=True)
    
    # 运行共享场景
    user_data = run_sim(trace, algo, quantum)
    if not user_data:
        return AlgorithmMetrics()
    
    # 1. Request Fairness
    requests = [d['completed'] for d in user_data.values()]
    request_fairness = jain_index(requests)
    
    # 2. Byte Fairness
    bytes_list = [d['total_bytes'] for d in user_data.values()]
    byte_fairness = jain_index(bytes_list)
    
    # 3. Latency Fairness
    inv_latencies = [1.0 / d['avg_latency'] if d['avg_latency'] > 0 else 0 
                    for d in user_data.values()]
    latency_fairness = jain_index(inv_latencies)
    
    # 4. Slowdown Fairness (需要单独运行)
    shared_lat = {uid: d['avg_latency'] for uid, d in user_data.items()}
    
    user_rows = {}
    with open(trace, 'r') as f:
        for row in csv.DictReader(f):
            uid = int(row['user_id'])
            if uid not in user_rows:
                user_rows[uid] = []
            user_rows[uid].append(row)
    
    alone_lat = {}
    for uid, rows in user_rows.items():
        trace_out = temp_dir / f"alone_{uid}.csv"
        with open(trace_out, 'w', newline='') as f:
            w = csv.DictWriter(f, ["timestamp", "process_id", "user_id", "type", "address", "size"])
            w.writeheader()
            for r in rows:
                r2 = dict(r)
                r2['user_id'] = 0
                w.writerow(r2)
        alone_data = run_sim(str(trace_out), algo, quantum)
        alone_lat[uid] = alone_data.get(0, {}).get('avg_latency', 0.0001)
    
    slowdowns = []
    for uid in shared_lat:
        if alone_lat.get(uid, 0) > 0:
            slowdowns.append(shared_lat[uid] / alone_lat[uid])
        else:
            slowdowns.append(1.0)
    
    slowdown_fairness = min(slowdowns) / max(slowdowns) if slowdowns and max(slowdowns) > 0 else 1.0
    
    return AlgorithmMetrics(
        request_fairness=request_fairness,
        byte_fairness=byte_fairness,
        latency_fairness=latency_fairness,
        slowdown_fairness=slowdown_fairness
    )


def analyze_trace(trace_path: str) -> TraceAnalysis:
    """完整分析一个 trace"""
    features = extract_features(trace_path)
    
    # 计算 quantum
    quantum = int(math.sqrt(features.min_size * features.max_size))
    
    # 运行所有算法
    algos = ["rr", "drr", "qfq", "flin"]
    metrics = {}
    
    for algo in algos:
        q = quantum if algo == "drr" else None
        metrics[algo] = calc_all_metrics(trace_path, algo, q)
    
    analysis = TraceAnalysis(
        trace_name=features.name,
        features=features,
        metrics=metrics
    )
    
    # 找出每个指标的最佳算法
    analysis.best_for_request = max(algos, key=lambda a: metrics[a].request_fairness)
    analysis.best_for_byte = max(algos, key=lambda a: metrics[a].byte_fairness)
    analysis.best_for_latency = max(algos, key=lambda a: metrics[a].latency_fairness)
    analysis.best_for_slowdown = max(algos, key=lambda a: metrics[a].slowdown_fairness)
    
    # 综合排名
    rankings = {algo: 0 for algo in algos}
    for algo in algos:
        # 每个指标的排名 (0=最好, 3=最差)
        for metric_name in ['request_fairness', 'byte_fairness', 'latency_fairness', 'slowdown_fairness']:
            sorted_algos = sorted(algos, key=lambda a: getattr(metrics[a], metric_name), reverse=True)
            rankings[algo] += sorted_algos.index(algo)
    
    analysis.overall_best = min(rankings.keys(), key=lambda k: rankings[k])
    
    return analysis


def build_recommendation_model(analyses: List[TraceAnalysis]) -> Dict:
    """基于分析结果构建推荐模型"""
    
    # 统计特征与最佳算法的关系
    patterns = {
        'size_ratio_high': {'threshold': 4, 'results': []},
        'rw_variance_high': {'threshold': 0.05, 'results': []},
        'pure_rw_users': {'results': []},
        'burst': {'results': []},
        'simple': {'results': []},
    }
    
    for a in analyses:
        f = a.features
        
        if f.size_ratio > 4:
            patterns['size_ratio_high']['results'].append(a.overall_best)
        
        if f.rw_variance > 0.05:
            patterns['rw_variance_high']['results'].append(a.overall_best)
        
        if f.has_pure_read and f.has_pure_write:
            patterns['pure_rw_users']['results'].append(a.overall_best)
        
        if f.has_burst:
            patterns['burst']['results'].append(a.overall_best)
        
        if f.size_ratio < 2 and f.rw_variance < 0.01:
            patterns['simple']['results'].append(a.overall_best)
    
    # 统计每个模式下最常见的最佳算法
    recommendations = {}
    for pattern_name, data in patterns.items():
        results = data['results']
        if results:
            from collections import Counter
            counts = Counter(results)
            most_common = counts.most_common(1)[0]
            recommendations[pattern_name] = {
                'recommended': most_common[0],
                'confidence': most_common[1] / len(results),
                'sample_size': len(results)
            }
    
    return recommendations


def main():
    print("=" * 70)
    print("          自动算法分析系统")
    print("=" * 70)
    print()
    print("对每个 trace 运行 4 种算法，计算 4 种指标，确定最佳算法")
    print()
    
    # 收集所有 traces
    traces = []
    for pattern in ["traces/validation/*.csv", "traces/competition/*.csv", "traces/contention/*.csv"]:
        traces.extend(Path(".").glob(pattern))
    
    traces = sorted(set(traces))[:20]  # 去重并限制数量
    print(f"分析 {len(traces)} 个 traces...")
    print()
    
    analyses = []
    
    print("-" * 100)
    print(f"{'Trace':<30} | {'Request':<12} | {'Byte':<12} | {'Latency':<12} | {'Slowdown':<12} | {'Overall':<8}")
    print("-" * 100)
    
    for trace in traces:
        print(f"分析: {trace.name}...", end=" ", flush=True)
        analysis = analyze_trace(str(trace))
        analyses.append(analysis)
        
        # 打印结果
        print(f"\r{analysis.trace_name:<30} | "
              f"{analysis.best_for_request.upper():<12} | "
              f"{analysis.best_for_byte.upper():<12} | "
              f"{analysis.best_for_latency.upper():<12} | "
              f"{analysis.best_for_slowdown.upper():<12} | "
              f"{analysis.overall_best.upper():<8}")
    
    print("-" * 100)
    
    # 统计
    print("\n" + "=" * 70)
    print("                    统计分析")
    print("=" * 70)
    
    # 每个指标下各算法获胜次数
    print("\n各指标下算法获胜次数:")
    for metric_name, attr_name in [
        ("Request Fairness", "best_for_request"),
        ("Byte Fairness", "best_for_byte"),
        ("Latency Fairness", "best_for_latency"),
        ("Slowdown Fairness", "best_for_slowdown"),
        ("Overall", "overall_best")
    ]:
        counts = {}
        for a in analyses:
            best = getattr(a, attr_name)
            counts[best] = counts.get(best, 0) + 1
        
        print(f"\n  {metric_name}:")
        for algo in ["rr", "drr", "qfq", "flin"]:
            count = counts.get(algo, 0)
            bar = "█" * count
            print(f"    {algo.upper()}: {count:2d} {bar}")
    
    # 构建推荐模型
    print("\n" + "=" * 70)
    print("                    推荐模型")
    print("=" * 70)
    
    model = build_recommendation_model(analyses)
    
    print("\n基于特征的算法推荐:")
    print()
    
    feature_descriptions = {
        'size_ratio_high': '大小差异 > 4x',
        'rw_variance_high': '读写方差 > 0.05',
        'pure_rw_users': '纯读 + 纯写用户',
        'burst': '突发流量',
        'simple': '简单均匀场景',
    }
    
    for pattern, data in model.items():
        desc = feature_descriptions.get(pattern, pattern)
        print(f"  {desc}:")
        print(f"    → 推荐: {data['recommended'].upper()}")
        print(f"    → 置信度: {data['confidence']*100:.1f}% (样本数: {data['sample_size']})")
        print()
    
    # 保存详细结果
    output_path = Path("results/algorithm_analysis.json")
    output_path.parent.mkdir(exist_ok=True)
    
    results = {
        'analyses': [
            {
                'trace': a.trace_name,
                'features': {
                    'num_users': a.features.num_users,
                    'size_ratio': a.features.size_ratio,
                    'rw_variance': a.features.rw_variance,
                    'has_pure_read': a.features.has_pure_read,
                    'has_pure_write': a.features.has_pure_write,
                    'has_burst': a.features.has_burst,
                },
                'best_for': {
                    'request': a.best_for_request,
                    'byte': a.best_for_byte,
                    'latency': a.best_for_latency,
                    'slowdown': a.best_for_slowdown,
                },
                'overall_best': a.overall_best,
                'metrics': {
                    algo: {
                        'request': m.request_fairness,
                        'byte': m.byte_fairness,
                        'latency': m.latency_fairness,
                        'slowdown': m.slowdown_fairness,
                    } for algo, m in a.metrics.items()
                }
            } for a in analyses
        ],
        'model': model
    }
    
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n详细结果已保存: {output_path}")
    print("=" * 70)


if __name__ == "__main__":
    main()

