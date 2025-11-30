#!/usr/bin/env python3
"""
综合评估框架 - 使用正确的指标评估每种算法

算法目标：
- RR:   请求级公平 (每用户处理相同数量的请求)
- DRR:  字节级公平 (每用户传输相同字节数)
- QFQ:  加权公平 (按权重分配带宽)
- FLIN: 读延迟保护 (降低读请求延迟)
"""

import csv
import subprocess
import random
import math
from pathlib import Path
from typing import Dict, List, Tuple


def write_trace(rows: List[Dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows_sorted = sorted(rows, key=lambda r: (r["timestamp"], r["user_id"]))
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["timestamp", "process_id", "user_id", "type", "address", "size"]
        )
        writer.writeheader()
        writer.writerows(rows_sorted)


def run_simulator(trace_path: str, scheduler: str, quantum: int = None) -> Dict:
    """运行模拟器并解析输出"""
    cmd = [
        ".\\build\\Release\\ssd-fairness.exe",
        "--trace", trace_path,
        "--scheduler", scheduler
    ]
    if quantum and scheduler == "drr":
        cmd.extend(["--quantum", str(quantum)])
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    output = result.stdout + result.stderr
    
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


def generate_requests(user_id, count, ts_start, gap_range, size, read_ratio, rng, proc_id=""):
    rows = []
    ts = ts_start
    addr = user_id * (1 << 40)
    for _ in range(count):
        ts += rng.randint(gap_range[0], gap_range[1])
        sz = size if isinstance(size, int) else rng.choice(size)
        op = "READ" if rng.random() < read_ratio else "WRITE"
        rows.append({
            "timestamp": ts,
            "process_id": proc_id or f"user{user_id}",
            "user_id": user_id,
            "type": op,
            "address": hex(addr),
            "size": sz,
        })
        addr += sz
    return rows


def test_rr_scenarios(rng: random.Random, out_dir: Path) -> List[Dict]:
    """RR 最佳场景：请求大小相同，需要请求级公平"""
    print("\n" + "="*60)
    print("RR 场景测试: 请求级公平")
    print("="*60)
    
    results = []
    
    # 场景1: 完全均匀请求
    trace_path = out_dir / "rr_uniform.csv"
    rows = []
    for uid in range(4):
        rows.extend(generate_requests(uid, 3000, 0, (10, 20), 4096, 0.5, rng))
    write_trace(rows, trace_path)
    
    print("\n场景: 均匀请求 (所有请求4KB)")
    for algo in ["rr", "drr", "qfq", "flin"]:
        m = run_simulator(str(trace_path), algo)
        completed = m.get("Requests completed", 0)
        throughput_f = m.get("Fairness Index (throughput)", 0)
        print(f"  {algo.upper()}: throughput_fairness={throughput_f:.4f}")
        results.append({"scene": "rr_uniform", "algo": algo, 
                       "throughput_fairness": throughput_f})
    
    # 场景2: 不均匀到达但相同大小
    trace_path = out_dir / "rr_uneven_arrival.csv"
    rows = []
    # 用户0: 高频
    rows.extend(generate_requests(0, 5000, 0, (5, 10), 4096, 0.5, rng))
    # 其他用户: 低频
    for uid in range(1, 4):
        rows.extend(generate_requests(uid, 2000, 0, (30, 50), 4096, 0.5, rng))
    write_trace(rows, trace_path)
    
    print("\n场景: 不均匀到达 (高频 vs 低频，相同大小)")
    for algo in ["rr", "drr", "qfq", "flin"]:
        m = run_simulator(str(trace_path), algo)
        throughput_f = m.get("Fairness Index (throughput)", 0)
        print(f"  {algo.upper()}: throughput_fairness={throughput_f:.4f}")
        results.append({"scene": "rr_uneven", "algo": algo, 
                       "throughput_fairness": throughput_f})
    
    return results


def test_drr_scenarios(rng: random.Random, out_dir: Path) -> List[Dict]:
    """DRR 最佳场景：请求大小差异大，需要字节级公平"""
    print("\n" + "="*60)
    print("DRR 场景测试: 字节级公平")
    print("="*60)
    
    results = []
    
    # 场景1: 极端大小差异 (4KB vs 512KB)
    trace_path = out_dir / "drr_size_diff.csv"
    rows = []
    # 小请求用户
    for uid in range(2):
        rows.extend(generate_requests(uid, 8000, 0, (5, 15), 4096, 0.5, rng, f"small{uid}"))
    # 大请求用户
    for uid in range(2, 4):
        rows.extend(generate_requests(uid, 500, 0, (80, 120), 524288, 0.5, rng, f"large{uid}"))
    write_trace(rows, trace_path)
    
    # 计算合适的 quantum
    sqrt_q = int(math.sqrt(4096 * 524288))
    
    print(f"\n场景: 极端大小差异 (4KB vs 512KB, quantum={sqrt_q})")
    print("  目标: 每用户获得相似的字节数")
    for algo in ["rr", "drr", "qfq", "flin"]:
        quantum = sqrt_q if algo == "drr" else None
        m = run_simulator(str(trace_path), algo, quantum)
        throughput_f = m.get("Fairness Index (throughput)", 0)
        print(f"  {algo.upper()}: throughput_fairness={throughput_f:.4f}")
        results.append({"scene": "drr_size_diff", "algo": algo, 
                       "throughput_fairness": throughput_f})
    
    # 场景2: 持续带宽竞争
    trace_path = out_dir / "drr_bandwidth.csv"
    rows = []
    for uid in range(4):
        size = 4096 if uid < 2 else 262144  # 4KB vs 256KB
        count = 6000 if uid < 2 else 800
        gap = (10, 20) if uid < 2 else (50, 100)
        rows.extend(generate_requests(uid, count, 0, gap, size, 0.6, rng))
    write_trace(rows, trace_path)
    
    sqrt_q = int(math.sqrt(4096 * 262144))
    print(f"\n场景: 持续带宽竞争 (quantum={sqrt_q})")
    for algo in ["rr", "drr", "qfq", "flin"]:
        quantum = sqrt_q if algo == "drr" else None
        m = run_simulator(str(trace_path), algo, quantum)
        throughput_f = m.get("Fairness Index (throughput)", 0)
        print(f"  {algo.upper()}: throughput_fairness={throughput_f:.4f}")
        results.append({"scene": "drr_bandwidth", "algo": algo,
                       "throughput_fairness": throughput_f})
    
    return results


def test_qfq_scenarios(rng: random.Random, out_dir: Path) -> List[Dict]:
    """QFQ 最佳场景：高竞争下的虚拟时间调度优势"""
    print("\n" + "="*60)
    print("QFQ 场景测试: 高竞争调度")
    print("="*60)
    
    results = []
    
    # 场景1: 大规模同时突发
    trace_path = out_dir / "qfq_burst.csv"
    rows = []
    for uid in range(8):
        for i in range(1500):
            rows.append({
                "timestamp": 0,  # 全部同时!
                "process_id": f"burst{uid}",
                "user_id": uid,
                "type": "READ" if i % 2 == 0 else "WRITE",
                "address": hex(uid * (1 << 40) + i * 4096),
                "size": 4096,
            })
    write_trace(rows, trace_path)
    
    print("\n场景: 8用户同时突发 (12000请求同时到达)")
    for algo in ["rr", "drr", "qfq", "flin"]:
        m = run_simulator(str(trace_path), algo)
        throughput_f = m.get("Fairness Index (throughput)", 0)
        latency_f = m.get("Fairness Index (latency)", 0)
        print(f"  {algo.upper()}: throughput={throughput_f:.4f}, latency={latency_f:.4f}")
        results.append({"scene": "qfq_burst", "algo": algo,
                       "throughput_fairness": throughput_f,
                       "latency_fairness": latency_f})
    
    # 场景2: 混合大小竞争
    trace_path = out_dir / "qfq_mixed.csv"
    rows = []
    sizes = [4096, 8192, 16384, 32768, 65536]
    for uid in range(5):
        for i in range(3000):
            rows.append({
                "timestamp": i * 10 + uid,  # 交错
                "process_id": f"mixed{uid}",
                "user_id": uid,
                "type": "READ",
                "address": hex(uid * (1 << 40) + i * sizes[uid]),
                "size": sizes[uid],
            })
    write_trace(rows, trace_path)
    
    print("\n场景: 5用户不同大小交错竞争")
    for algo in ["rr", "drr", "qfq", "flin"]:
        m = run_simulator(str(trace_path), algo)
        throughput_f = m.get("Fairness Index (throughput)", 0)
        latency_f = m.get("Fairness Index (latency)", 0)
        combined = m.get("Fairness Index (combined)", 0)
        print(f"  {algo.upper()}: combined={combined:.4f}")
        results.append({"scene": "qfq_mixed", "algo": algo,
                       "combined_fairness": combined})
    
    return results


def test_flin_scenarios(rng: random.Random, out_dir: Path) -> List[Dict]:
    """FLIN 最佳场景：读写不对称，需要保护读延迟"""
    print("\n" + "="*60)
    print("FLIN 场景测试: 读延迟保护")
    print("="*60)
    print("  注意: FLIN 优化的是读延迟，不是公平性！")
    
    results = []
    
    # 场景1: 纯读用户 vs 纯写用户
    trace_path = out_dir / "flin_rw_split.csv"
    rows = []
    # 读用户
    for uid in range(2):
        rows.extend(generate_requests(uid, 4000, 0, (15, 30), 4096, 1.0, rng, f"reader{uid}"))
    # 写用户 (大写)
    for uid in range(2, 4):
        rows.extend(generate_requests(uid, 2000, 0, (20, 40), 65536, 0.0, rng, f"writer{uid}"))
    write_trace(rows, trace_path)
    
    print("\n场景: 读用户 vs 写用户")
    print("  评估: 平均延迟 (越低越好)")
    for algo in ["rr", "drr", "qfq", "flin"]:
        m = run_simulator(str(trace_path), algo)
        avg_lat = m.get("Average latency (s)", 0)
        throughput = m.get("Throughput (MB/s)", 0)
        print(f"  {algo.upper()}: avg_latency={avg_lat:.4f}s, throughput={throughput:.1f}MB/s")
        results.append({"scene": "flin_rw_split", "algo": algo,
                       "avg_latency": avg_lat, "throughput": throughput})
    
    # 场景2: 写风暴攻击
    trace_path = out_dir / "flin_write_storm.csv"
    rows = []
    # 正常读用户
    for uid in range(3):
        rows.extend(generate_requests(uid, 3000, 0, (20, 40), 4096, 0.95, rng, f"normal{uid}"))
    # 写攻击者
    rows.extend(generate_requests(3, 8000, 0, (2, 8), 131072, 0.0, rng, "attacker"))
    write_trace(rows, trace_path)
    
    print("\n场景: 写风暴攻击")
    print("  评估: 在攻击下保护读延迟")
    for algo in ["rr", "drr", "qfq", "flin"]:
        m = run_simulator(str(trace_path), algo)
        avg_lat = m.get("Average latency (s)", 0)
        throughput = m.get("Throughput (MB/s)", 0)
        print(f"  {algo.upper()}: avg_latency={avg_lat:.4f}s, throughput={throughput:.1f}MB/s")
        results.append({"scene": "flin_write_storm", "algo": algo,
                       "avg_latency": avg_lat, "throughput": throughput})
    
    # 场景3: 混合读写比例
    trace_path = out_dir / "flin_mixed_rw.csv"
    rows = []
    read_ratios = [0.99, 0.8, 0.5, 0.1]
    for uid, rr in enumerate(read_ratios):
        count = 3000 if rr > 0.5 else 2000
        size = 4096 if rr > 0.5 else 32768
        rows.extend(generate_requests(uid, count, 0, (15, 35), size, rr, rng, f"rw{int(rr*100)}"))
    write_trace(rows, trace_path)
    
    print("\n场景: 混合读写比例 (99%, 80%, 50%, 10% 读)")
    for algo in ["rr", "drr", "qfq", "flin"]:
        m = run_simulator(str(trace_path), algo)
        avg_lat = m.get("Average latency (s)", 0)
        throughput = m.get("Throughput (MB/s)", 0)
        print(f"  {algo.upper()}: avg_latency={avg_lat:.4f}s, throughput={throughput:.1f}MB/s")
        results.append({"scene": "flin_mixed_rw", "algo": algo,
                       "avg_latency": avg_lat, "throughput": throughput})
    
    return results


def main():
    rng = random.Random(42)
    out_dir = Path("traces/eval")
    
    print("=" * 60)
    print("           综合算法评估")
    print("=" * 60)
    
    all_results = []
    all_results.extend(test_rr_scenarios(rng, out_dir))
    all_results.extend(test_drr_scenarios(rng, out_dir))
    all_results.extend(test_qfq_scenarios(rng, out_dir))
    all_results.extend(test_flin_scenarios(rng, out_dir))
    
    # 总结
    print("\n" + "=" * 60)
    print("                总结分析")
    print("=" * 60)
    
    print("""
关键发现：
1. RR 场景: 请求大小相同时，RR/DRR/QFQ 表现相当
2. DRR 场景: 请求大小差异大时，DRR 提供更好的字节公平性
3. QFQ 场景: 高竞争时提供稳定的虚拟时间调度
4. FLIN 场景: 优化的是延迟，不是公平性指标！

建议：
- 对于公平性需求，比较 throughput_fairness
- 对于 FLIN，比较 avg_latency
- 各算法针对不同优化目标，不应用同一指标比较
""")


if __name__ == "__main__":
    main()

