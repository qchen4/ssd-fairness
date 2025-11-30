#!/usr/bin/env python3
"""
智能算法选择器

根据以下因素选择最佳调度算法：
1. 用户的优化目标 (公平性类型)
2. 工作负载特征 (大小差异、读写比例等)
"""

import csv
import math
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional
from enum import Enum


class FairnessGoal(Enum):
    """公平性优化目标"""
    REQUEST = "request"      # 请求数公平 → RR
    BYTE = "byte"           # 字节数公平 → DRR
    LATENCY = "latency"     # 延迟公平 → QFQ
    SLOWDOWN = "slowdown"   # 减速公平 → FLIN
    AUTO = "auto"           # 自动检测


@dataclass
class WorkloadProfile:
    """工作负载特征"""
    num_users: int
    total_requests: int
    min_size: int
    max_size: int
    size_ratio: float
    avg_size: float
    overall_read_ratio: float
    read_ratio_variance: float
    has_pure_read_user: bool
    has_pure_write_user: bool
    arrival_variance: float
    has_burst: bool
    has_sequential: bool


def analyze_workload(trace_path: str) -> WorkloadProfile:
    """分析工作负载特征"""
    users = {}
    sizes = []
    timestamps = []
    addresses = {}
    
    with open(trace_path, 'r') as f:
        for row in csv.DictReader(f):
            uid = int(row['user_id'])
            size = int(row['size'])
            ts = int(row['timestamp'])
            is_read = row['type'].upper() == 'READ'
            addr = int(row['address'], 16) if row['address'].startswith('0x') else int(row['address'])
            
            sizes.append(size)
            timestamps.append(ts)
            
            if uid not in users:
                users[uid] = {'reads': 0, 'writes': 0, 'sizes': [], 'addrs': []}
            
            users[uid]['sizes'].append(size)
            users[uid]['addrs'].append(addr)
            if is_read:
                users[uid]['reads'] += 1
            else:
                users[uid]['writes'] += 1
    
    # Size metrics
    min_size = min(sizes)
    max_size = max(sizes)
    size_ratio = max_size / min_size if min_size > 0 else 1.0
    avg_size = sum(sizes) / len(sizes)
    
    # Read/Write metrics
    total_reads = sum(u['reads'] for u in users.values())
    total_writes = sum(u['writes'] for u in users.values())
    overall_read_ratio = total_reads / (total_reads + total_writes) if (total_reads + total_writes) > 0 else 0.5
    
    # Per-user read ratios
    ratios = []
    has_pure_read = False
    has_pure_write = False
    for u in users.values():
        total = u['reads'] + u['writes']
        r = u['reads'] / total if total > 0 else 0.5
        ratios.append(r)
        if r > 0.95:
            has_pure_read = True
        if r < 0.05:
            has_pure_write = True
    
    avg_ratio = sum(ratios) / len(ratios) if ratios else 0.5
    read_ratio_variance = sum((r - avg_ratio)**2 for r in ratios) / len(ratios) if ratios else 0
    
    # Arrival pattern
    ts_counts = {}
    for ts in timestamps:
        ts_counts[ts] = ts_counts.get(ts, 0) + 1
    
    max_concurrent = max(ts_counts.values()) if ts_counts else 0
    has_burst = max_concurrent > len(users) * 2
    
    # Check for sequential access
    has_sequential = False
    for u in users.values():
        addrs = sorted(u['addrs'])
        if len(addrs) > 10:
            diffs = [addrs[i+1] - addrs[i] for i in range(len(addrs)-1)]
            avg_diff = sum(diffs) / len(diffs)
            # If addresses are roughly sequential (within 2x average size)
            if all(d > 0 and d < avg_size * 2 for d in diffs[:10]):
                has_sequential = True
                break
    
    # Arrival variance
    if len(timestamps) > 1:
        ts_sorted = sorted(timestamps)
        gaps = [ts_sorted[i+1] - ts_sorted[i] for i in range(len(ts_sorted)-1)]
        avg_gap = sum(gaps) / len(gaps) if gaps else 0
        arrival_variance = sum((g - avg_gap)**2 for g in gaps) / len(gaps) if gaps and avg_gap > 0 else 0
        arrival_variance = arrival_variance / (avg_gap ** 2) if avg_gap > 0 else 0  # Normalized
    else:
        arrival_variance = 0
    
    return WorkloadProfile(
        num_users=len(users),
        total_requests=len(sizes),
        min_size=min_size,
        max_size=max_size,
        size_ratio=size_ratio,
        avg_size=avg_size,
        overall_read_ratio=overall_read_ratio,
        read_ratio_variance=read_ratio_variance,
        has_pure_read_user=has_pure_read,
        has_pure_write_user=has_pure_write,
        arrival_variance=arrival_variance,
        has_burst=has_burst,
        has_sequential=has_sequential
    )


def select_algorithm(
    profile: WorkloadProfile, 
    goal: FairnessGoal = FairnessGoal.AUTO,
    weights_specified: bool = False
) -> Tuple[str, str, Dict[str, float]]:
    """
    选择最佳算法
    
    Returns:
        (algorithm, reason, scores)
    """
    
    # 如果用户明确指定了目标
    if goal != FairnessGoal.AUTO:
        goal_to_algo = {
            FairnessGoal.REQUEST: ("rr", "用户指定请求公平目标"),
            FairnessGoal.BYTE: ("drr", "用户指定字节公平目标"),
            FairnessGoal.LATENCY: ("qfq", "用户指定延迟公平目标"),
            FairnessGoal.SLOWDOWN: ("flin", "用户指定减速公平目标"),
        }
        algo, reason = goal_to_algo[goal]
        return algo, reason, {algo: 1.0}
    
    # 自动选择：基于评分系统
    scores = {"rr": 0.0, "drr": 0.0, "qfq": 0.0, "flin": 0.0}
    reasons = []
    
    # ===== 规则 1: 请求大小差异 =====
    if profile.size_ratio > 16:
        scores["drr"] += 3.0
        scores["qfq"] += 2.5
        reasons.append(f"大小差异极大 ({profile.size_ratio:.0f}x) → DRR/QFQ")
    elif profile.size_ratio > 4:
        scores["drr"] += 2.0
        scores["qfq"] += 1.5
        reasons.append(f"大小差异显著 ({profile.size_ratio:.0f}x) → DRR/QFQ")
    elif profile.size_ratio < 2:
        scores["rr"] += 1.5
        reasons.append("大小均匀 → RR")
    
    # ===== 规则 2: 读写比例差异 =====
    if profile.read_ratio_variance > 0.1:
        scores["flin"] += 3.0
        reasons.append(f"读写差异大 (var={profile.read_ratio_variance:.3f}) → FLIN")
    elif profile.read_ratio_variance > 0.05:
        scores["flin"] += 1.5
        reasons.append(f"读写有差异 → FLIN")
    
    # ===== 规则 3: 纯读/纯写用户 =====
    if profile.has_pure_read_user and profile.has_pure_write_user:
        scores["flin"] += 2.5
        reasons.append("存在纯读+纯写用户 → FLIN (保护读延迟)")
    elif profile.has_pure_read_user:
        scores["flin"] += 1.0
        scores["qfq"] += 0.5
        reasons.append("存在纯读用户 → FLIN/QFQ")
    elif profile.has_pure_write_user:
        scores["drr"] += 1.0
        reasons.append("存在纯写用户 → DRR")
    
    # ===== 规则 4: 突发流量 =====
    if profile.has_burst:
        scores["qfq"] += 2.0
        reasons.append("检测到突发流量 → QFQ (虚拟时间调度)")
    
    # ===== 规则 5: 多用户场景 =====
    if profile.num_users > 8:
        scores["qfq"] += 1.5
        scores["drr"] += 1.0
        reasons.append(f"多用户场景 ({profile.num_users}) → QFQ/DRR")
    elif profile.num_users <= 2:
        scores["rr"] += 1.0
        reasons.append("少用户场景 → RR")
    
    # ===== 规则 6: 权重指定 =====
    if weights_specified:
        scores["qfq"] += 5.0
        reasons.append("用户指定权重 → QFQ")
    
    # ===== 规则 7: 顺序访问 =====
    if profile.has_sequential:
        scores["drr"] += 0.5
        reasons.append("顺序访问模式 → DRR")
    
    # ===== 规则 8: 简单场景加分 RR =====
    is_simple = (
        profile.size_ratio < 2 and 
        profile.read_ratio_variance < 0.01 and 
        not profile.has_burst and
        profile.num_users <= 4
    )
    if is_simple:
        scores["rr"] += 2.0
        reasons.append("简单均匀场景 → RR (低开销)")
    
    # 选择最高分
    best_algo = max(scores.keys(), key=lambda k: scores[k])
    
    # 生成原因
    if not reasons:
        reasons.append("默认选择")
    
    return best_algo, "; ".join(reasons), scores


def print_selection_result(
    trace: str, 
    profile: WorkloadProfile, 
    algo: str, 
    reason: str, 
    scores: Dict[str, float]
):
    """打印选择结果"""
    print("\n" + "=" * 60)
    print(f"📊 工作负载分析: {Path(trace).name}")
    print("=" * 60)
    
    print(f"\n用户数: {profile.num_users}")
    print(f"请求数: {profile.total_requests}")
    print(f"大小范围: {profile.min_size} - {profile.max_size} ({profile.size_ratio:.1f}x)")
    print(f"读比例: {profile.overall_read_ratio*100:.1f}%")
    print(f"读写方差: {profile.read_ratio_variance:.4f}")
    print(f"纯读用户: {'是' if profile.has_pure_read_user else '否'}")
    print(f"纯写用户: {'是' if profile.has_pure_write_user else '否'}")
    print(f"突发流量: {'是' if profile.has_burst else '否'}")
    
    print(f"\n📈 算法评分:")
    for a, s in sorted(scores.items(), key=lambda x: -x[1]):
        bar = "█" * int(s * 5)
        print(f"  {a.upper():5} {s:5.1f} {bar}")
    
    print(f"\n🎯 推荐算法: {algo.upper()}")
    print(f"📝 原因: {reason}")
    
    # 推荐的评估指标
    metrics = {
        "rr": "Request Fairness - Jain(requests/user)",
        "drr": "Byte Fairness - Jain(bytes/user)",
        "qfq": "Latency Fairness - Jain(1/latency)",
        "flin": "Slowdown Fairness - min(S)/max(S)"
    }
    print(f"📏 评估指标: {metrics[algo]}")


def generate_decision_tree():
    """生成决策树文档"""
    tree = """
    ┌─────────────────────────────────────────────────────────────┐
    │              智能算法选择决策树                              │
    └─────────────────────────────────────────────────────────────┘
    
                            开始
                              │
                    ┌─────────▼─────────┐
                    │ 用户指定权重?      │
                    └─────────┬─────────┘
                          Yes │ No
                    ┌─────────▼─┐    │
                    │   QFQ    │    │
                    └───────────┘    │
                                     ▼
                    ┌─────────────────────┐
                    │ 纯读 + 纯写用户?     │
                    └─────────┬───────────┘
                          Yes │ No
                    ┌─────────▼─┐    │
                    │   FLIN   │    │
                    └───────────┘    │
                                     ▼
                    ┌─────────────────────┐
                    │ 读写差异大?          │
                    │ (variance > 0.1)    │
                    └─────────┬───────────┘
                          Yes │ No
                    ┌─────────▼─┐    │
                    │   FLIN   │    │
                    └───────────┘    │
                                     ▼
                    ┌─────────────────────┐
                    │ 大小差异大?          │
                    │ (ratio > 4x)        │
                    └─────────┬───────────┘
                          Yes │ No
                    ┌─────────▼─┐    │
                    │   DRR    │    │
                    └───────────┘    │
                                     ▼
                    ┌─────────────────────┐
                    │ 突发流量?            │
                    └─────────┬───────────┘
                          Yes │ No
                    ┌─────────▼─┐    │
                    │   QFQ    │    │
                    └───────────┘    │
                                     ▼
                              ┌─────────┐
                              │   RR    │
                              └─────────┘
    
    ═══════════════════════════════════════════════════════════════
    
    快速参考表:
    
    ┌────────────┬─────────────────────────────────────────────────┐
    │ 场景特征    │ 推荐算法                                        │
    ├────────────┼─────────────────────────────────────────────────┤
    │ 大小均匀    │ RR (简单高效)                                   │
    │ 大小差异大  │ DRR (字节公平)                                  │
    │ 读写分离    │ FLIN (保护读延迟)                               │
    │ 需要权重    │ QFQ (加权调度)                                  │
    │ 突发流量    │ QFQ (虚拟时间)                                  │
    │ 多租户云    │ FLIN (SLO保障)                                  │
    └────────────┴─────────────────────────────────────────────────┘
    """
    return tree


def main():
    import sys
    
    print("=" * 60)
    print("     智能 SSD 调度算法选择器")
    print("=" * 60)
    
    # 检查命令行参数
    if len(sys.argv) < 2:
        print("\n用法: python algorithm_selector.py <trace.csv> [goal]")
        print("\ngoal 可选值:")
        print("  auto     - 自动检测 (默认)")
        print("  request  - 请求公平")
        print("  byte     - 字节公平")
        print("  latency  - 延迟公平")
        print("  slowdown - 减速公平")
        print("\n决策树:")
        print(generate_decision_tree())
        return
    
    trace_path = sys.argv[1]
    goal_str = sys.argv[2] if len(sys.argv) > 2 else "auto"
    
    goal_map = {
        "auto": FairnessGoal.AUTO,
        "request": FairnessGoal.REQUEST,
        "byte": FairnessGoal.BYTE,
        "latency": FairnessGoal.LATENCY,
        "slowdown": FairnessGoal.SLOWDOWN,
    }
    goal = goal_map.get(goal_str.lower(), FairnessGoal.AUTO)
    
    # 分析工作负载
    profile = analyze_workload(trace_path)
    
    # 选择算法
    algo, reason, scores = select_algorithm(profile, goal)
    
    # 打印结果
    print_selection_result(trace_path, profile, algo, reason, scores)
    
    # 计算推荐的 quantum (for DRR)
    if algo == "drr":
        quantum = int(math.sqrt(profile.min_size * profile.max_size))
        print(f"\n💡 推荐 DRR quantum: {quantum} bytes")
        print(f"   命令: --scheduler drr --quantum {quantum}")
    elif algo == "qfq":
        print(f"\n💡 如需权重，使用: --weights w1,w2,w3,...")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
