#!/usr/bin/env python3
"""
生成大规模、更真实的测试 Trace

特点:
1. 10,000-100,000 请求
2. 更长时间跨度 (100ms - 10s)
3. 真实负载模式：
   - 突发-平稳循环
   - 多用户竞争
   - 读写混合变化
   - 请求大小分布更真实
"""

import csv
import random
import math
from pathlib import Path
from typing import List, Dict
from dataclasses import dataclass


@dataclass
class UserProfile:
    user_id: int
    base_rate: float      # 基础请求率 (requests/ms)
    size_dist: str        # 大小分布: "small", "mixed", "large"
    read_ratio: float     # 读比例
    bursty: bool          # 是否有突发
    label: str


def size_sample(dist: str, rng: random.Random) -> int:
    """根据分布类型采样请求大小"""
    if dist == "small":
        # 小请求: 4KB-16KB
        return rng.choice([4096, 8192, 16384])
    elif dist == "large":
        # 大请求: 64KB-256KB
        return rng.choice([65536, 131072, 262144])
    else:  # mixed
        # 混合: 80% 小请求, 20% 大请求 (类似真实 SSD 负载)
        if rng.random() < 0.8:
            return rng.choice([4096, 8192, 16384])
        else:
            return rng.choice([65536, 131072])


def generate_user_requests(
    profile: UserProfile,
    duration_ms: float,
    rng: random.Random,
) -> List[Dict]:
    """生成单个用户的请求序列"""
    rows = []
    ts = 0.0  # 微秒
    addr = profile.user_id * (1 << 40)
    
    while ts < duration_ms * 1000:  # 转换为微秒
        # 计算当前请求率 (考虑突发)
        rate = profile.base_rate
        if profile.bursty:
            # 每 50ms 一个突发周期
            cycle_pos = (ts / 1000) % 50  # ms
            if cycle_pos < 10:  # 前 10ms 是突发期
                rate *= 5  # 5倍速率
        
        # 请求间隔 (指数分布)
        if rate > 0:
            interval = rng.expovariate(rate) * 1000  # 转为微秒
        else:
            interval = 1000000  # 1秒
        
        ts += interval
        if ts >= duration_ms * 1000:
            break
        
        # 生成请求
        size = size_sample(profile.size_dist, rng)
        op = "READ" if rng.random() < profile.read_ratio else "WRITE"
        
        rows.append({
            "timestamp": int(ts),
            "process_id": profile.label,
            "user_id": profile.user_id,
            "type": op,
            "address": hex(addr),
            "size": size,
        })
        addr += size
    
    return rows


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


def create_large_traces(seed: int, out_dir: Path) -> None:
    """创建大规模测试 trace"""
    rng = random.Random(seed)
    
    print("生成大规模测试 Trace...")
    print()
    
    # =========================================================================
    # Trace 1: 长时间均匀负载 (10秒, ~50,000 请求)
    # =========================================================================
    print("1. long_uniform: 10秒均匀负载...")
    profiles = [
        UserProfile(i, 1.0, "mixed", 0.7, False, f"user{i}")
        for i in range(4)
    ]
    rows = []
    for p in profiles:
        rows.extend(generate_user_requests(p, 10000, rng))  # 10秒
    write_trace(rows, out_dir / "long_uniform.csv")
    print(f"   生成 {len(rows)} 请求")
    
    # =========================================================================
    # Trace 2: 突发竞争 (5秒, ~30,000 请求)
    # =========================================================================
    print("2. long_bursty: 5秒突发竞争...")
    profiles = [
        UserProfile(0, 2.0, "small", 0.9, True, "bursty_reader"),
        UserProfile(1, 1.0, "mixed", 0.5, False, "steady_mixed"),
        UserProfile(2, 0.5, "large", 0.2, True, "bursty_writer"),
        UserProfile(3, 1.5, "small", 0.8, False, "steady_reader"),
    ]
    rows = []
    for p in profiles:
        rows.extend(generate_user_requests(p, 5000, rng))  # 5秒
    write_trace(rows, out_dir / "long_bursty.csv")
    print(f"   生成 {len(rows)} 请求")
    
    # =========================================================================
    # Trace 3: 大小差异极端 (3秒, ~20,000 请求)
    # =========================================================================
    print("3. long_size_disparity: 3秒大小差异...")
    profiles = [
        UserProfile(0, 3.0, "small", 0.7, False, "small_user0"),
        UserProfile(1, 3.0, "small", 0.7, False, "small_user1"),
        UserProfile(2, 0.3, "large", 0.5, False, "large_user0"),
        UserProfile(3, 0.3, "large", 0.5, False, "large_user1"),
    ]
    rows = []
    for p in profiles:
        rows.extend(generate_user_requests(p, 3000, rng))  # 3秒
    write_trace(rows, out_dir / "long_size_disparity.csv")
    print(f"   生成 {len(rows)} 请求")
    
    # =========================================================================
    # Trace 4: 读写极端不对称 (3秒, ~15,000 请求)
    # =========================================================================
    print("4. long_rw_asymmetry: 3秒读写不对称...")
    profiles = [
        UserProfile(0, 2.0, "small", 0.99, False, "pure_reader0"),
        UserProfile(1, 2.0, "small", 0.99, False, "pure_reader1"),
        UserProfile(2, 1.0, "mixed", 0.01, False, "pure_writer0"),
        UserProfile(3, 1.0, "large", 0.01, False, "pure_writer1"),
    ]
    rows = []
    for p in profiles:
        rows.extend(generate_user_requests(p, 3000, rng))  # 3秒
    write_trace(rows, out_dir / "long_rw_asymmetry.csv")
    print(f"   生成 {len(rows)} 请求")
    
    # =========================================================================
    # Trace 5: 带宽霸占者 (5秒, ~25,000 请求)
    # =========================================================================
    print("5. long_bandwidth_hog: 5秒带宽霸占...")
    profiles = [
        UserProfile(0, 5.0, "large", 0.3, True, "bandwidth_hog"),  # 霸占者
        UserProfile(1, 1.0, "small", 0.9, False, "victim1"),
        UserProfile(2, 1.0, "small", 0.9, False, "victim2"),
        UserProfile(3, 1.0, "small", 0.9, False, "victim3"),
    ]
    rows = []
    for p in profiles:
        rows.extend(generate_user_requests(p, 5000, rng))  # 5秒
    write_trace(rows, out_dir / "long_bandwidth_hog.csv")
    print(f"   生成 {len(rows)} 请求")
    
    # =========================================================================
    # Trace 6: 多用户高竞争 (2秒, ~40,000 请求)
    # =========================================================================
    print("6. long_high_contention: 2秒高竞争...")
    profiles = [
        UserProfile(i, 2.5, "mixed", 0.6, i % 2 == 0, f"user{i}")
        for i in range(8)  # 8个用户
    ]
    rows = []
    for p in profiles:
        rows.extend(generate_user_requests(p, 2000, rng))  # 2秒
    write_trace(rows, out_dir / "long_high_contention.csv")
    print(f"   生成 {len(rows)} 请求")
    
    # =========================================================================
    # Trace 7: 真实混合负载 (10秒, ~60,000 请求)
    # =========================================================================
    print("7. long_realistic_mix: 10秒真实混合...")
    profiles = [
        # OLTP: 高频小读
        UserProfile(0, 3.0, "small", 0.95, True, "oltp"),
        # 分析: 中频大读
        UserProfile(1, 0.5, "large", 0.9, False, "analytics"),
        # 日志: 持续写
        UserProfile(2, 2.0, "mixed", 0.05, False, "logging"),
        # 备份: 间歇大写
        UserProfile(3, 0.2, "large", 0.0, True, "backup"),
        # 普通用户
        UserProfile(4, 1.0, "mixed", 0.7, False, "user1"),
        UserProfile(5, 1.0, "mixed", 0.7, False, "user2"),
    ]
    rows = []
    for p in profiles:
        rows.extend(generate_user_requests(p, 10000, rng))  # 10秒
    write_trace(rows, out_dir / "long_realistic_mix.csv")
    print(f"   生成 {len(rows)} 请求")
    
    print()
    print("完成！")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="生成大规模测试 trace")
    parser.add_argument("--output-dir", default="traces/large", help="输出目录")
    parser.add_argument("--seed", type=int, default=42, help="随机种子")
    args = parser.parse_args()
    
    create_large_traces(args.seed, Path(args.output_dir))


if __name__ == "__main__":
    main()

