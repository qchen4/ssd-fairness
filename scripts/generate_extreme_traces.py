#!/usr/bin/env python3
"""
生成极端场景 Trace - 寻找四种算法各自的最佳场景

设计原则：
1. 每种算法设计 2-3 个极端场景
2. 场景要足够极端，差异要明显
3. 请求数量要足够大 (10,000+)
"""

import csv
import random
import math
from pathlib import Path
from typing import List, Dict


def write_trace(rows: List[Dict], path: Path) -> None:
    """写入 trace 文件"""
    path.parent.mkdir(parents=True, exist_ok=True)
    rows_sorted = sorted(rows, key=lambda r: (r["timestamp"], r["user_id"]))
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["timestamp", "process_id", "user_id", "type", "address", "size"]
        )
        writer.writeheader()
        writer.writerows(rows_sorted)
    print(f"  生成: {path.name} ({len(rows)} 请求)")


def generate_requests(user_id, count, ts_start, gap_range, size, read_ratio, rng, label=""):
    """生成请求序列"""
    rows = []
    ts = ts_start
    addr = user_id * (1 << 40)
    
    for _ in range(count):
        ts += rng.randint(gap_range[0], gap_range[1])
        sz = size if isinstance(size, int) else rng.choice(size)
        op = "READ" if rng.random() < read_ratio else "WRITE"
        rows.append({
            "timestamp": ts,
            "process_id": label or f"user{user_id}",
            "user_id": user_id,
            "type": op,
            "address": hex(addr),
            "size": sz,
        })
        addr += sz
    return rows


def create_rr_extreme_scenarios(rng: random.Random, out_dir: Path):
    """
    RR 极端场景：
    - RR 在请求大小完全相同时最优
    - 所有用户负载均衡时 RR 最简单最好
    """
    print("\n=== RR 极端场景 ===")
    
    # RR-1: 完美均匀 - 所有请求完全相同
    rows = []
    for uid in range(4):
        rows.extend(generate_requests(
            uid, 5000, 0,
            gap_range=(10, 10),  # 固定间隔！
            size=4096,           # 固定大小！
            read_ratio=0.5,      # 50% 读写
            rng=rng,
            label=f"identical_user{uid}"
        ))
    write_trace(rows, out_dir / "extreme_rr_perfect_uniform.csv")
    
    # RR-2: 轮流到达 - 请求严格交替
    rows = []
    for i in range(10000):
        uid = i % 4
        rows.append({
            "timestamp": i * 100,  # 严格等间隔
            "process_id": f"round_robin_user{uid}",
            "user_id": uid,
            "type": "READ" if i % 2 == 0 else "WRITE",
            "address": hex(uid * (1 << 40) + (i // 4) * 4096),
            "size": 4096,
        })
    write_trace(rows, out_dir / "extreme_rr_round_robin_arrival.csv")


def create_drr_extreme_scenarios(rng: random.Random, out_dir: Path):
    """
    DRR 极端场景：
    - 请求大小差异极大 (1KB vs 1MB)
    - 需要严格字节级公平
    """
    print("\n=== DRR 极端场景 ===")
    
    # DRR-1: 极端大小差异 (4KB vs 1MB = 256倍差异)
    rows = []
    # 小请求用户：高频小请求
    for uid in range(2):
        rows.extend(generate_requests(
            uid, 10000, 0,
            gap_range=(5, 15),
            size=4096,  # 4KB
            read_ratio=0.7,
            rng=rng,
            label=f"tiny_user{uid}"
        ))
    # 大请求用户：低频大请求
    for uid in range(2, 4):
        rows.extend(generate_requests(
            uid, 500, 0,
            gap_range=(100, 300),
            size=1048576,  # 1MB!
            read_ratio=0.5,
            rng=rng,
            label=f"huge_user{uid}"
        ))
    write_trace(rows, out_dir / "extreme_drr_size_256x.csv")
    
    # DRR-2: 带宽霸占者 vs 受害者
    rows = []
    # 霸占者: 超高频大请求
    rows.extend(generate_requests(
        0, 5000, 0,
        gap_range=(1, 5),  # 极高频
        size=262144,       # 256KB
        read_ratio=0.3,
        rng=rng,
        label="bandwidth_monster"
    ))
    # 受害者: 正常小请求
    for uid in range(1, 4):
        rows.extend(generate_requests(
            uid, 3000, 0,
            gap_range=(20, 60),
            size=4096,
            read_ratio=0.9,
            rng=rng,
            label=f"victim{uid}"
        ))
    write_trace(rows, out_dir / "extreme_drr_bandwidth_monster.csv")
    
    # DRR-3: 持续大小差异竞争
    rows = []
    for uid in range(4):
        if uid < 2:
            size = 4096
            count = 8000
            gap = (10, 30)
        else:
            size = 524288  # 512KB
            count = 1000
            gap = (50, 150)
        rows.extend(generate_requests(
            uid, count, 0,
            gap_range=gap,
            size=size,
            read_ratio=0.6,
            rng=rng,
            label=f"size_class{uid}"
        ))
    write_trace(rows, out_dir / "extreme_drr_sustained_disparity.csv")


def create_qfq_extreme_scenarios(rng: random.Random, out_dir: Path):
    """
    QFQ 极端场景：
    - 需要精确比例分配
    - 高竞争下虚拟时间优势
    - 同时突发（DRR 会死锁的场景）
    """
    print("\n=== QFQ 极端场景 ===")
    
    # QFQ-1: 大规模同时突发
    rows = []
    for uid in range(8):
        for i in range(2000):
            rows.append({
                "timestamp": 0,  # 全部同时到达！
                "process_id": f"burst_user{uid}",
                "user_id": uid,
                "type": "READ" if i % 3 != 0 else "WRITE",
                "address": hex(uid * (1 << 40) + i * 8192),
                "size": 8192,
            })
    write_trace(rows, out_dir / "extreme_qfq_massive_simultaneous.csv")
    
    # QFQ-2: 严格交错竞争（测试虚拟时间调度）
    rows = []
    sizes = [4096, 8192, 16384, 32768]  # 不同大小
    for i in range(20000):
        uid = i % 4
        rows.append({
            "timestamp": i * 50,  # 密集交错
            "process_id": f"interleaved{uid}",
            "user_id": uid,
            "type": "READ",
            "address": hex(uid * (1 << 40) + (i // 4) * sizes[uid]),
            "size": sizes[uid],  # 每个用户不同大小
        })
    write_trace(rows, out_dir / "extreme_qfq_strict_interleave.csv")
    
    # QFQ-3: 持续高负载竞争
    rows = []
    for uid in range(6):
        rows.extend(generate_requests(
            uid, 5000, 0,
            gap_range=(1, 10),  # 极高频，造成排队
            size=[4096, 8192, 16384],
            read_ratio=0.7,
            rng=rng,
            label=f"contender{uid}"
        ))
    write_trace(rows, out_dir / "extreme_qfq_sustained_contention.csv")


def create_flin_extreme_scenarios(rng: random.Random, out_dir: Path):
    """
    FLIN 极端场景：
    - 极端读写不对称
    - 写密集用户需要被严格抑制
    - 读用户延迟需要保护
    """
    print("\n=== FLIN 极端场景 ===")
    
    # FLIN-1: 纯读 vs 纯写
    rows = []
    # 纯读用户
    for uid in range(2):
        rows.extend(generate_requests(
            uid, 5000, 0,
            gap_range=(10, 30),
            size=4096,
            read_ratio=1.0,  # 100% 读！
            rng=rng,
            label=f"pure_reader{uid}"
        ))
    # 纯写用户（大写）
    for uid in range(2, 4):
        rows.extend(generate_requests(
            uid, 3000, 0,
            gap_range=(10, 30),
            size=65536,  # 64KB 大写
            read_ratio=0.0,  # 100% 写！
            rng=rng,
            label=f"pure_writer{uid}"
        ))
    write_trace(rows, out_dir / "extreme_flin_pure_rw_split.csv")
    
    # FLIN-2: 写风暴攻击
    rows = []
    # 正常读用户
    for uid in range(3):
        rows.extend(generate_requests(
            uid, 4000, 0,
            gap_range=(20, 50),
            size=4096,
            read_ratio=0.95,
            rng=rng,
            label=f"normal_reader{uid}"
        ))
    # 写风暴攻击者：疯狂大写
    rows.extend(generate_requests(
        3, 10000, 0,
        gap_range=(1, 5),  # 极高频
        size=131072,       # 128KB
        read_ratio=0.0,    # 全写
        rng=rng,
        label="write_storm_attacker"
    ))
    write_trace(rows, out_dir / "extreme_flin_write_storm_attack.csv")
    
    # FLIN-3: 读写比例渐变
    rows = []
    # 用户读写比例从高到低
    read_ratios = [0.99, 0.7, 0.3, 0.01]
    for uid, rr in enumerate(read_ratios):
        rows.extend(generate_requests(
            uid, 4000, 0,
            gap_range=(15, 45),
            size=[4096, 8192] if rr > 0.5 else [32768, 65536],
            read_ratio=rr,
            rng=rng,
            label=f"rw_ratio_{int(rr*100)}"
        ))
    write_trace(rows, out_dir / "extreme_flin_gradient_rw.csv")


def main():
    rng = random.Random(42)
    out_dir = Path("traces/extreme")
    
    print("=" * 60)
    print("生成极端场景 Trace")
    print("=" * 60)
    
    create_rr_extreme_scenarios(rng, out_dir)
    create_drr_extreme_scenarios(rng, out_dir)
    create_qfq_extreme_scenarios(rng, out_dir)
    create_flin_extreme_scenarios(rng, out_dir)
    
    print("\n" + "=" * 60)
    print("完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()

