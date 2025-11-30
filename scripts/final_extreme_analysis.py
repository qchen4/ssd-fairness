#!/usr/bin/env python3
"""
最终极端场景分析 - 多维度评估

关键洞察：
- 不同算法优化不同目标
- 用单一指标评估所有算法是错误的
- 需要针对每个算法设计专属测试
"""

import subprocess
import csv
import random
import math
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List


@dataclass
class Metrics:
    combined_fairness: float
    throughput_fairness: float
    latency_fairness: float
    avg_latency: float
    throughput_mbps: float


def run_sim(trace: str, scheduler: str, quantum: int = None) -> Metrics:
    cmd = [".\\build\\Release\\ssd-fairness.exe", 
           "--trace", trace, "--scheduler", scheduler]
    if quantum and scheduler == "drr":
        cmd.extend(["--quantum", str(quantum)])
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    output = result.stdout + result.stderr
    
    def parse(key):
        for line in output.split('\n'):
            if key in line:
                return float(line.split(':')[1].strip())
        return 0.0
    
    return Metrics(
        combined_fairness=parse("Fairness Index (combined)"),
        throughput_fairness=parse("Fairness Index (throughput)"),
        latency_fairness=parse("Fairness Index (latency)"),
        avg_latency=parse("Average latency"),
        throughput_mbps=parse("Throughput (MB/s)")
    )


def write_trace(rows, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(
            f, ["timestamp", "process_id", "user_id", "type", "address", "size"]
        )
        writer.writeheader()
        for r in sorted(rows, key=lambda x: (x["timestamp"], x["user_id"])):
            writer.writerow(r)
    return str(path)


def analyze_drr_advantage():
    """DRR 真正优势：低延迟 + 字节公平"""
    print("\n" + "="*70)
    print("DRR 极端场景: 大小差异 (4KB vs 256KB)")
    print("="*70)
    print("设计: 小请求用户频繁发送，大请求用户偶尔发送")
    print("评估: avg_latency (DRR 应该更低)")
    print()
    
    trace = Path("traces/contention/contention_drr_size_gap.csv")
    sizes = []
    with open(trace) as f:
        sizes = [int(r['size']) for r in csv.DictReader(f)]
    quantum = int(math.sqrt(min(sizes) * max(sizes)))
    
    results = {}
    for algo in ["rr", "drr", "qfq", "flin"]:
        m = run_sim(str(trace), algo, quantum if algo == "drr" else None)
        results[algo] = m
        
    print(f"{'算法':<6} | {'Avg Latency (s)':<15} | {'Combined Fair':<12} | {'Throughput Fair':<15}")
    print("-" * 60)
    for algo in ["rr", "drr", "qfq", "flin"]:
        m = results[algo]
        winner = " <-- 最低延迟" if algo == "drr" and m.avg_latency == min(r.avg_latency for r in results.values()) else ""
        print(f"{algo.upper():<6} | {m.avg_latency:<15.4f} | {m.combined_fairness:<12.4f} | {m.throughput_fairness:<15.4f}{winner}")
    
    # 计算改进比例
    rr_lat = results["rr"].avg_latency
    drr_lat = results["drr"].avg_latency
    if drr_lat > 0:
        improvement = (rr_lat - drr_lat) / rr_lat * 100
        print(f"\nDRR 延迟改进: {improvement:.1f}% (相比 RR)")


def analyze_qfq_with_weights():
    """QFQ 真正优势需要权重"""
    print("\n" + "="*70)
    print("QFQ 场景说明")
    print("="*70)
    print("""
QFQ (Weighted Fair Queuing) 的真正优势在于:
1. 支持不同用户不同权重
2. 精确的虚拟时间调度

当前实现问题:
- 默认所有用户权重=1.0
- 没有命令行参数设置权重
- 因此 QFQ 和 DRR 表现相似

要体现 QFQ 优势，需要:
1. 添加权重设置接口
2. 测试加权场景 (如 用户0权重=2, 用户1权重=1)
""")


def analyze_flin_read_protection():
    """FLIN 真正优势：保护读延迟"""
    print("\n" + "="*70)
    print("FLIN 极端场景: 写风暴攻击")
    print("="*70)
    print("设计: 3个读用户 vs 1个疯狂写用户")
    print("评估: avg_latency (FLIN 应该保护读用户)")
    print()
    
    trace = Path("traces/contention/contention_flin_write_storm.csv")
    
    results = {}
    for algo in ["rr", "drr", "qfq", "flin"]:
        m = run_sim(str(trace), algo)
        results[algo] = m
    
    print(f"{'算法':<6} | {'Avg Latency (s)':<15} | {'Throughput (MB/s)':<18}")
    print("-" * 50)
    for algo in ["rr", "drr", "qfq", "flin"]:
        m = results[algo]
        print(f"{algo.upper():<6} | {m.avg_latency:<15.4f} | {m.throughput_mbps:<18.1f}")
    
    # 分析
    rr_lat = results["rr"].avg_latency
    flin_lat = results["flin"].avg_latency
    if flin_lat > 0 and rr_lat > flin_lat:
        improvement = (rr_lat - flin_lat) / rr_lat * 100
        print(f"\nFLIN 延迟改进: {improvement:.1f}% (相比 RR)")
    else:
        print("\n注意: 当前场景 FLIN 未能显著改进延迟")


def generate_true_extreme_scenarios(rng: random.Random):
    """生成真正极端的场景"""
    print("\n" + "="*70)
    print("生成更极端的 FLIN 场景")
    print("="*70)
    
    out_dir = Path("traces/extreme_v2")
    
    # FLIN 极端场景: 10:1 读写比例，疯狂写风暴
    rows = []
    # 10个轻量读用户
    for uid in range(10):
        for i in range(200):
            rows.append({
                "timestamp": i * 100 + uid * 10,
                "process_id": f"light_reader{uid}",
                "user_id": uid,
                "type": "READ",
                "address": hex(uid * (1 << 40) + i * 4096),
                "size": 4096,
            })
    
    # 1个疯狂写用户
    for i in range(5000):
        rows.append({
            "timestamp": i * 3,
            "process_id": "write_monster",
            "user_id": 10,
            "type": "WRITE",
            "address": hex(10 * (1 << 40) + i * 262144),
            "size": 262144,
        })
    
    trace = write_trace(rows, out_dir / "flin_extreme_10v1.csv")
    print(f"生成: flin_extreme_10v1.csv ({len(rows)} 请求)")
    
    print("\n测试 10 读用户 vs 1 写风暴:")
    results = {}
    for algo in ["rr", "drr", "qfq", "flin"]:
        m = run_sim(trace, algo)
        results[algo] = m
    
    print(f"{'算法':<6} | {'Avg Latency (s)':<15} | {'Latency Fair':<12}")
    print("-" * 45)
    for algo in ["rr", "drr", "qfq", "flin"]:
        m = results[algo]
        print(f"{algo.upper():<6} | {m.avg_latency:<15.4f} | {m.latency_fairness:<12.4f}")


def main():
    rng = random.Random(42)
    
    print("="*70)
    print("           最终极端场景多维度分析")
    print("="*70)
    
    analyze_drr_advantage()
    analyze_qfq_with_weights()
    analyze_flin_read_protection()
    generate_true_extreme_scenarios(rng)
    
    print("\n" + "="*70)
    print("                    结论")
    print("="*70)
    print("""
1. DRR 优势场景: 请求大小差异大
   - 评估指标: avg_latency
   - DRR 可以显著降低延迟

2. QFQ 优势场景: 需要加权公平
   - 当前实现未支持权重参数
   - 需要扩展接口才能体现优势

3. FLIN 优势场景: 读写不对称
   - 评估指标: avg_latency 或 read_latency
   - 在极端场景下可能保护读延迟

4. RR 适用场景: 请求均匀
   - 简单高效
   - 无需配置

关键教训:
- 用错误的指标评估算法会得出错误结论
- combined_fairness 不适合评估 FLIN
- 每个算法有其特定优势场景
""")


if __name__ == "__main__":
    main()

