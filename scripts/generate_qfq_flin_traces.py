#!/usr/bin/env python3
"""
生成专门针对 QFQ 和 FLIN 的测试场景

QFQ 优势场景:
1. 需要加权分配的场景 (不同用户有不同权重)
2. 严格比例公平的场景

FLIN 优势场景:
1. 极端读写不对称 (写密集用户 vs 读密集用户)
2. 需要保护读延迟的场景
3. 突发写流量场景
"""

import csv
import random
from pathlib import Path
from typing import List, Dict


def write_trace(rows: List[Dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows_sorted = sorted(rows, key=lambda r: (r["timestamp"], r["user_id"]))
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["timestamp", "process_id", "user_id", "type", "address", "size"]
        )
        writer.writeheader()
        writer.writerows(rows_sorted)


def generate_requests(
    user_id: int,
    count: int,
    gap_range: tuple,
    size: int,
    read_ratio: float,
    rng: random.Random,
    start_ts: int = 0,
    label: str = ""
) -> List[Dict]:
    rows = []
    ts = start_ts
    addr = user_id * (1 << 30)
    
    for _ in range(count):
        ts += rng.randint(gap_range[0], gap_range[1])
        op = "READ" if rng.random() < read_ratio else "WRITE"
        rows.append({
            "timestamp": ts,
            "process_id": label or f"user{user_id}",
            "user_id": user_id,
            "type": op,
            "address": hex(addr),
            "size": size,
        })
        addr += size
    return rows


def create_qfq_scenarios(rng: random.Random, out_dir: Path) -> None:
    """QFQ 专属场景"""
    
    # 场景1: 需要加权的场景 (高优先级用户应该获得更多带宽)
    # 注意: 当前实现不支持命令行设置权重，这个场景用于未来扩展
    rows = []
    # VIP 用户: 高优先级，期望更多带宽
    rows.extend(generate_requests(0, 200, (10, 30), 4096, 0.7, rng, label="vip_user"))
    # 普通用户
    for uid in range(1, 4):
        rows.extend(generate_requests(uid, 200, (10, 30), 4096, 0.7, rng, label=f"normal_user{uid}"))
    write_trace(rows, out_dir / "qfq_weighted_priority.csv")
    print(f"  生成: qfq_weighted_priority.csv (需要配合权重使用)")
    
    # 场景2: 严格时序公平 (请求交错到达，需要精确调度)
    rows = []
    for uid in range(4):
        for i in range(50):
            ts = i * 100 + uid * 10  # 交错到达
            rows.append({
                "timestamp": ts,
                "process_id": f"interleaved{uid}",
                "user_id": uid,
                "type": "READ" if i % 2 == 0 else "WRITE",
                "address": hex(uid * (1 << 30) + i * 4096),
                "size": 4096 + uid * 4096,  # 不同用户不同大小
            })
    write_trace(rows, out_dir / "qfq_interleaved_arrival.csv")
    print(f"  生成: qfq_interleaved_arrival.csv")
    
    # 场景3: 长队列竞争 (队列积压时需要公平调度)
    rows = []
    # 所有用户同时发送大量请求
    for uid in range(4):
        for i in range(100):
            rows.append({
                "timestamp": 0,  # 同时到达！
                "process_id": f"burst{uid}",
                "user_id": uid,
                "type": "READ",
                "address": hex(uid * (1 << 30) + i * 8192),
                "size": 8192,
            })
    write_trace(rows, out_dir / "qfq_simultaneous_burst.csv")
    print(f"  生成: qfq_simultaneous_burst.csv")


def create_flin_scenarios(rng: random.Random, out_dir: Path) -> None:
    """FLIN 专属场景"""
    
    # 场景1: 极端读写不对称 (100%读 vs 100%写)
    rows = []
    # 纯读用户 (应该被保护)
    rows.extend(generate_requests(0, 100, (20, 50), 4096, 1.0, rng, label="pure_reader"))
    rows.extend(generate_requests(1, 100, (20, 50), 4096, 1.0, rng, label="pure_reader2"))
    # 纯写用户 (应该被惩罚)
    rows.extend(generate_requests(2, 100, (20, 50), 4096, 0.0, rng, label="pure_writer"))
    rows.extend(generate_requests(3, 100, (20, 50), 4096, 0.0, rng, label="pure_writer2"))
    write_trace(rows, out_dir / "flin_extreme_rw.csv")
    print(f"  生成: flin_extreme_rw.csv")
    
    # 场景2: 写风暴 (突发大量写，读用户需要保护)
    rows = []
    # 正常读用户 (持续)
    rows.extend(generate_requests(0, 200, (30, 60), 4096, 1.0, rng, label="steady_reader"))
    # 写风暴用户 (集中在开始)
    for i in range(150):
        rows.append({
            "timestamp": i * 5,  # 密集写入
            "process_id": "write_storm",
            "user_id": 1,
            "type": "WRITE",
            "address": hex((1 << 30) + i * 65536),
            "size": 65536,  # 大写请求
        })
    write_trace(rows, out_dir / "flin_write_storm.csv")
    print(f"  生成: flin_write_storm.csv")
    
    # 场景3: 持续写压力 (写用户持续高负载)
    rows = []
    # 读用户 (正常负载)
    for uid in range(3):
        rows.extend(generate_requests(uid, 80, (30, 60), 4096, 0.95, rng, label=f"reader{uid}"))
    # 写霸占者 (高负载写)
    rows.extend(generate_requests(3, 300, (5, 15), 32768, 0.05, rng, label="write_hog"))
    write_trace(rows, out_dir / "flin_sustained_write_pressure.csv")
    print(f"  生成: flin_sustained_write_pressure.csv")
    
    # 场景4: 混合突发 (读写用户都有突发)
    rows = []
    # 读突发
    for i in range(100):
        rows.append({
            "timestamp": i * 10,
            "process_id": "read_burst",
            "user_id": 0,
            "type": "READ",
            "address": hex(i * 4096),
            "size": 4096,
        })
    # 写突发 (稍后开始)
    for i in range(100):
        rows.append({
            "timestamp": 500 + i * 10,
            "process_id": "write_burst",
            "user_id": 1,
            "type": "WRITE",
            "address": hex((1 << 30) + i * 32768),
            "size": 32768,
        })
    # 后续正常读
    rows.extend(generate_requests(2, 100, (20, 40), 4096, 0.9, rng, start_ts=0, label="normal_reader"))
    write_trace(rows, out_dir / "flin_mixed_bursts.csv")
    print(f"  生成: flin_mixed_bursts.csv")


def main():
    rng = random.Random(42)
    out_dir = Path("traces/scenarios")
    
    print("生成 QFQ 专属场景...")
    create_qfq_scenarios(rng, out_dir)
    
    print("\n生成 FLIN 专属场景...")
    create_flin_scenarios(rng, out_dir)
    
    print("\n完成！")


if __name__ == "__main__":
    main()

