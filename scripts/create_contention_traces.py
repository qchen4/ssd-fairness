#!/usr/bin/env python3
"""
创建真正有排队竞争的极端场景 Trace

关键：SSD 配置是 8 通道，1200MB/s 读，800MB/s 写
- 每通道读: 150MB/s = 0.0067μs/byte
- 4KB 读需要 27μs 服务时间

要形成排队，请求到达速度必须超过 SSD 处理速度！
"""

import csv
import random
import math
from pathlib import Path


def write_trace(rows, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    rows_sorted = sorted(rows, key=lambda r: (r["timestamp"], r["user_id"]))
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["timestamp", "process_id", "user_id", "type", "address", "size"]
        )
        writer.writeheader()
        writer.writerows(rows_sorted)
    print(f"  {path.name}: {len(rows)} 请求")


def extreme_rr_scenario(out_dir: Path):
    """RR 极端场景: 完全相同的请求，同时到达"""
    print("\n=== RR 极端场景 ===")
    print("设计: 所有请求完全相同 (4KB)，高度同时到达")
    print("预期: RR = DRR = QFQ > FLIN")
    
    rows = []
    # 4 用户，每人 2000 请求，全部在 0.1 秒内到达
    for uid in range(4):
        for i in range(2000):
            rows.append({
                "timestamp": i * 50,  # 50μs 间隔 = 20000 请求/秒 (接近饱和)
                "process_id": f"uniform{uid}",
                "user_id": uid,
                "type": "READ",
                "address": hex(uid * (1 << 40) + i * 4096),
                "size": 4096,
            })
    write_trace(rows, out_dir / "contention_rr_uniform.csv")


def extreme_drr_scenario(out_dir: Path, rng: random.Random):
    """DRR 极端场景: 大小差异极大，需要字节级公平"""
    print("\n=== DRR 极端场景 ===")
    print("设计: 用户0-1发4KB，用户2-3发256KB，256倍差异")
    print("预期: DRR > RR/QFQ (字节公平)")
    
    rows = []
    # 高度重叠到达
    for batch in range(500):
        base_ts = batch * 200  # 每 200μs 一批
        
        # 小请求用户: 每批 4 个请求
        for uid in range(2):
            for i in range(4):
                rows.append({
                    "timestamp": base_ts + uid * 10 + i * 5,
                    "process_id": f"tiny{uid}",
                    "user_id": uid,
                    "type": "READ",
                    "address": hex(uid * (1 << 40) + batch * 4 * 4096 + i * 4096),
                    "size": 4096,
                })
        
        # 大请求用户: 每批 1 个请求
        for uid in range(2, 4):
            rows.append({
                "timestamp": base_ts + 50,
                "process_id": f"huge{uid}",
                "user_id": uid,
                "type": "READ",
                "address": hex(uid * (1 << 40) + batch * 262144),
                "size": 262144,  # 256KB
            })
    
    write_trace(rows, out_dir / "contention_drr_size_gap.csv")


def extreme_qfq_scenario(out_dir: Path):
    """QFQ 极端场景: 大规模同时到达，测试虚拟时间调度"""
    print("\n=== QFQ 极端场景 ===")
    print("设计: 8用户同时提交各自的突发，测试公平调度")
    print("预期: QFQ = DRR > RR (虚拟时间更精确)")
    
    rows = []
    # 8 用户，每人同时提交 1000 个请求
    for uid in range(8):
        for i in range(1000):
            rows.append({
                "timestamp": 0,  # 全部时间戳 = 0！
                "process_id": f"burst{uid}",
                "user_id": uid,
                "type": "READ" if i % 2 == 0 else "WRITE",
                "address": hex(uid * (1 << 40) + i * 8192),
                "size": 8192,
            })
    write_trace(rows, out_dir / "contention_qfq_simultaneous.csv")
    
    # QFQ 场景 2: 不同大小但同时到达
    rows = []
    sizes = [4096, 8192, 16384, 32768]
    for uid in range(4):
        for i in range(2000):
            rows.append({
                "timestamp": 0,
                "process_id": f"sized{uid}",
                "user_id": uid,
                "type": "READ",
                "address": hex(uid * (1 << 40) + i * sizes[uid]),
                "size": sizes[uid],
            })
    write_trace(rows, out_dir / "contention_qfq_sized.csv")


def extreme_flin_scenario(out_dir: Path, rng: random.Random):
    """FLIN 极端场景: 读写极端不对称"""
    print("\n=== FLIN 极端场景 ===")
    print("设计: 纯读用户 vs 疯狂写用户，测试读保护")
    print("预期: FLIN 平均延迟最低 (保护读)")
    
    rows = []
    # 场景1: 读用户被写用户攻击
    # 读用户: 少量小读请求
    for uid in range(2):
        for i in range(500):
            rows.append({
                "timestamp": i * 100,  # 稀疏读请求
                "process_id": f"reader{uid}",
                "user_id": uid,
                "type": "READ",
                "address": hex(uid * (1 << 40) + i * 4096),
                "size": 4096,
            })
    
    # 写攻击者: 疯狂大写
    for uid in range(2, 4):
        for i in range(3000):
            rows.append({
                "timestamp": i * 10,  # 高频写
                "process_id": f"writer{uid}",
                "user_id": uid,
                "type": "WRITE",
                "address": hex(uid * (1 << 40) + i * 131072),
                "size": 131072,  # 128KB
            })
    
    write_trace(rows, out_dir / "contention_flin_read_protect.csv")
    
    # 场景2: 更极端 - 99% 读用户 vs 1% 写风暴
    rows = []
    # 读用户占多数但请求少
    for uid in range(3):
        for i in range(800):
            rows.append({
                "timestamp": i * 50,
                "process_id": f"reader{uid}",
                "user_id": uid,
                "type": "READ",
                "address": hex(uid * (1 << 40) + i * 4096),
                "size": 4096,
            })
    
    # 一个写风暴者
    for i in range(5000):
        rows.append({
            "timestamp": i * 5,  # 极高频
            "process_id": "write_storm",
            "user_id": 3,
            "type": "WRITE",
            "address": hex(3 * (1 << 40) + i * 262144),
            "size": 262144,  # 256KB
        })
    
    write_trace(rows, out_dir / "contention_flin_write_storm.csv")


def main():
    rng = random.Random(42)
    out_dir = Path("traces/contention")
    
    print("=" * 60)
    print("创建高竞争极端场景")
    print("=" * 60)
    
    extreme_rr_scenario(out_dir)
    extreme_drr_scenario(out_dir, rng)
    extreme_qfq_scenario(out_dir)
    extreme_flin_scenario(out_dir, rng)
    
    print("\n" + "=" * 60)
    print("完成!")
    print("=" * 60)


if __name__ == "__main__":
    main()

