#!/usr/bin/env python3
"""
算法验证 Trace 生成器

根据学术论文中各算法的理论特性，生成专门的验证测试场景
"""

import csv
import random
import math
from pathlib import Path
from typing import List, Dict


def write_trace(rows: List[Dict], path: Path, description: str = "") -> None:
    """写入 trace 文件"""
    path.parent.mkdir(parents=True, exist_ok=True)
    rows_sorted = sorted(rows, key=lambda r: (r["timestamp"], r["user_id"]))
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["timestamp", "process_id", "user_id", "type", "address", "size"]
        )
        writer.writeheader()
        writer.writerows(rows_sorted)
    
    total_bytes = sum(r["size"] for r in rows)
    print(f"  生成: {path.name}")
    print(f"    请求数: {len(rows)}, 总字节: {total_bytes/(1024*1024):.1f}MB")
    if description:
        print(f"    说明: {description}")


def gen_requests(uid, count, ts_start, gap_range, size, read_ratio, rng, proc_id=""):
    """生成请求序列"""
    rows = []
    ts = ts_start
    addr = uid * (1 << 40)
    
    for _ in range(count):
        ts += rng.randint(gap_range[0], gap_range[1])
        sz = size if isinstance(size, int) else rng.choice(size)
        op = "READ" if rng.random() < read_ratio else "WRITE"
        rows.append({
            "timestamp": ts,
            "process_id": proc_id or f"user{uid}",
            "user_id": uid,
            "type": op,
            "address": hex(addr),
            "size": sz,
        })
        addr += sz
    return rows


# ============================================================================
# DRR 验证场景 (根据 Shreedhar & Varghese 1996)
# ============================================================================

def generate_drr_validation_traces(out_dir: Path, rng: random.Random):
    """
    DRR 验证: 字节级公平
    
    理论: 不同大小请求的用户应获得相同的字节吞吐
    """
    print("\n" + "="*60)
    print("DRR 验证场景 (字节公平)")
    print("="*60)
    
    # 场景1: 等字节不等请求数
    # 用户传输相同字节，但请求大小不同
    rows = []
    # 用户0: 10000 × 4KB = 40MB
    rows.extend(gen_requests(0, 10000, 0, (5, 15), 4096, 0.5, rng, "small_req"))
    # 用户1: 2500 × 16KB = 40MB
    rows.extend(gen_requests(1, 2500, 0, (20, 40), 16384, 0.5, rng, "medium_req"))
    # 用户2: 625 × 64KB = 40MB
    rows.extend(gen_requests(2, 625, 0, (50, 100), 65536, 0.5, rng, "large_req"))
    # 用户3: 156 × 256KB ≈ 40MB
    rows.extend(gen_requests(3, 156, 0, (100, 200), 262144, 0.5, rng, "huge_req"))
    write_trace(rows, out_dir / "drr_v1_equal_bytes.csv", 
                "等字节不等请求: DRR应实现字节公平")

    # 场景2: 极端大小差异 (256倍)
    rows = []
    for uid in range(2):
        rows.extend(gen_requests(uid, 8000, 0, (5, 15), 4096, 0.5, rng, f"tiny{uid}"))
    for uid in range(2, 4):
        rows.extend(gen_requests(uid, 200, 0, (100, 200), 1048576, 0.5, rng, f"mega{uid}"))
    write_trace(rows, out_dir / "drr_v2_size_256x.csv",
                "256倍大小差异: 测试DRR的字节公平极限")

    # 场景3: 持续竞争
    rows = []
    for uid in range(4):
        size = 4096 * (2 ** uid)  # 4KB, 8KB, 16KB, 32KB
        count = 10000 // (2 ** uid)  # 保持总字节相近
        rows.extend(gen_requests(uid, count, 0, (10, 30), size, 0.5, rng, f"scale{uid}"))
    write_trace(rows, out_dir / "drr_v3_scaled_competition.csv",
                "按比例缩放: 测试DRR的稳定性")


# ============================================================================
# QFQ 验证场景 (根据 WFQ 理论)
# ============================================================================

def generate_qfq_validation_traces(out_dir: Path, rng: random.Random):
    """
    QFQ 验证: 加权公平
    
    理论: 用户吞吐应与权重成比例
    """
    print("\n" + "="*60)
    print("QFQ 验证场景 (加权公平)")
    print("="*60)
    
    # 场景1: 相同请求，测试权重效果
    # 权重 4:2:1:1，所有用户发送相同请求
    rows = []
    for uid in range(4):
        rows.extend(gen_requests(uid, 5000, 0, (10, 20), 8192, 0.5, rng, f"weighted{uid}"))
    write_trace(rows, out_dir / "qfq_v1_weight_test.csv",
                "权重测试: 配合 --weights 4,2,1,1 使用")

    # 场景2: 高竞争 (全部同时到达)
    rows = []
    for uid in range(8):
        for i in range(1000):
            rows.append({
                "timestamp": 0,
                "process_id": f"burst{uid}",
                "user_id": uid,
                "type": "READ" if i % 2 == 0 else "WRITE",
                "address": hex(uid * (1 << 40) + i * 8192),
                "size": 8192,
            })
    write_trace(rows, out_dir / "qfq_v2_high_contention.csv",
                "高竞争: 8用户同时突发，测试虚拟时间调度")

    # 场景3: 多用户不同大小
    rows = []
    sizes = [4096, 8192, 16384, 32768, 65536, 131072, 262144, 524288]
    for uid in range(8):
        for i in range(500):
            rows.append({
                "timestamp": i * 10 + uid,
                "process_id": f"varied{uid}",
                "user_id": uid,
                "type": "READ",
                "address": hex(uid * (1 << 40) + i * sizes[uid]),
                "size": sizes[uid],
            })
    write_trace(rows, out_dir / "qfq_v3_varied_sizes_8users.csv",
                "8用户不同大小: 测试QFQ多流扩展性")


# ============================================================================
# FLIN 验证场景 (根据 ISCA 2018)
# ============================================================================

def generate_flin_validation_traces(out_dir: Path, rng: random.Random):
    """
    FLIN 验证: Slowdown 公平
    
    理论: 平衡所有用户的相对减速
    """
    print("\n" + "="*60)
    print("FLIN 验证场景 (Slowdown 公平)")
    print("="*60)
    
    # 场景1: 纯读 vs 纯写 (极端)
    rows = []
    # 纯读用户: 小请求
    for uid in range(2):
        rows.extend(gen_requests(uid, 5000, 0, (10, 30), 4096, 1.0, rng, f"pure_read{uid}"))
    # 纯写用户: 大请求
    for uid in range(2, 4):
        rows.extend(gen_requests(uid, 2000, 0, (20, 50), 65536, 0.0, rng, f"pure_write{uid}"))
    write_trace(rows, out_dir / "flin_v1_pure_rw.csv",
                "纯读vs纯写: FLIN应平衡slowdown")

    # 场景2: 写风暴攻击
    rows = []
    # 正常读用户
    for uid in range(3):
        rows.extend(gen_requests(uid, 3000, 0, (15, 35), 4096, 0.95, rng, f"reader{uid}"))
    # 写风暴攻击者
    rows.extend(gen_requests(3, 10000, 0, (2, 8), 131072, 0.0, rng, "write_storm"))
    write_trace(rows, out_dir / "flin_v2_write_storm.csv",
                "写风暴: FLIN应保护读用户")

    # 场景3: 渐变读写比例
    rows = []
    read_ratios = [1.0, 0.75, 0.5, 0.25, 0.0]
    for uid, rr in enumerate(read_ratios):
        rows.extend(gen_requests(uid, 3000, 0, (15, 35), 8192, rr, rng, f"rw_{int(rr*100)}"))
    write_trace(rows, out_dir / "flin_v3_gradient_rw.csv",
                "渐变读写: 测试FLIN对不同比例的处理")

    # 场景4: 突发读请求
    rows = []
    # 背景写用户
    for uid in range(3):
        rows.extend(gen_requests(uid, 5000, 0, (10, 30), 32768, 0.1, rng, f"bg_write{uid}"))
    # 突发读用户
    for i in range(2000):
        rows.append({
            "timestamp": i * 5,  # 高频
            "process_id": "burst_read",
            "user_id": 3,
            "type": "READ",
            "address": hex(3 * (1 << 40) + i * 4096),
            "size": 4096,
        })
    write_trace(rows, out_dir / "flin_v4_burst_read.csv",
                "突发读: 测试FLIN对突发读的保护")


# ============================================================================
# RR 验证场景 (基线)
# ============================================================================

def generate_rr_validation_traces(out_dir: Path, rng: random.Random):
    """
    RR 验证: 请求级公平
    
    理论: 每用户获得相同调度机会
    """
    print("\n" + "="*60)
    print("RR 验证场景 (请求公平)")
    print("="*60)
    
    # 场景1: 完全均匀
    rows = []
    for uid in range(4):
        rows.extend(gen_requests(uid, 5000, 0, (10, 20), 4096, 0.5, rng, f"uniform{uid}"))
    write_trace(rows, out_dir / "rr_v1_uniform.csv",
                "完全均匀: 所有算法应表现相同")

    # 场景2: 不同到达率
    rows = []
    rows.extend(gen_requests(0, 10000, 0, (3, 8), 4096, 0.5, rng, "high_freq"))
    for uid in range(1, 4):
        rows.extend(gen_requests(uid, 2000, 0, (30, 60), 4096, 0.5, rng, f"low_freq{uid}"))
    write_trace(rows, out_dir / "rr_v2_arrival_diff.csv",
                "到达率差异: RR应给予相同调度机会")


# ============================================================================
# 综合混合场景
# ============================================================================

def generate_mixed_scenarios(out_dir: Path, rng: random.Random):
    """生成复杂混合场景"""
    print("\n" + "="*60)
    print("综合混合场景")
    print("="*60)
    
    # 场景1: 云存储多租户
    rows = []
    # VIP 用户: 高频小请求
    rows.extend(gen_requests(0, 8000, 0, (5, 15), 4096, 0.8, rng, "vip"))
    # 普通用户
    for uid in range(1, 3):
        rows.extend(gen_requests(uid, 3000, 0, (20, 50), 16384, 0.6, rng, f"normal{uid}"))
    # 批处理用户: 低频大请求
    rows.extend(gen_requests(3, 500, 0, (100, 200), 262144, 0.3, rng, "batch"))
    write_trace(rows, out_dir / "mixed_v1_cloud_storage.csv",
                "云存储: VIP + 普通 + 批处理")

    # 场景2: 数据库工作负载
    rows = []
    # OLTP: 高频小读
    rows.extend(gen_requests(0, 10000, 0, (2, 8), 4096, 0.95, rng, "oltp"))
    # OLAP: 低频大读
    rows.extend(gen_requests(1, 500, 0, (50, 150), 262144, 0.9, rng, "olap"))
    # 日志写入: 持续写
    rows.extend(gen_requests(2, 5000, 0, (10, 30), 16384, 0.0, rng, "wal"))
    # 检查点: 周期性大写
    for i in range(100):
        base_ts = i * 10000
        for j in range(10):
            rows.append({
                "timestamp": base_ts + j * 100,
                "process_id": "checkpoint",
                "user_id": 3,
                "type": "WRITE",
                "address": hex(3 * (1 << 40) + i * 10 * 1048576 + j * 1048576),
                "size": 1048576,
            })
    write_trace(rows, out_dir / "mixed_v2_database.csv",
                "数据库: OLTP + OLAP + WAL + Checkpoint")

    # 场景3: 长时间运行
    rows = []
    for uid in range(4):
        base_size = 4096 * (2 ** uid)
        for batch in range(20):  # 20个时间段
            batch_ts = batch * 100000
            count = 500 // (uid + 1)
            rows.extend(gen_requests(
                uid, count, batch_ts, 
                (50 + uid * 20, 100 + uid * 40),
                base_size, 0.5 + 0.1 * uid, rng, f"long_run{uid}"
            ))
    write_trace(rows, out_dir / "mixed_v3_long_running.csv",
                "长时间: 20个时间段的持续运行")


def main():
    rng = random.Random(42)
    out_dir = Path("traces/validation")
    
    print("=" * 60)
    print("     算法验证 Trace 生成器")
    print("=" * 60)
    print()
    print("根据学术论文生成验证测试场景:")
    print("  - DRR: Shreedhar & Varghese 1996")
    print("  - QFQ: Demers et al. 1989, Checconi et al. 2013")
    print("  - FLIN: Tavakkol et al. ISCA 2018")
    
    generate_drr_validation_traces(out_dir, rng)
    generate_qfq_validation_traces(out_dir, rng)
    generate_flin_validation_traces(out_dir, rng)
    generate_rr_validation_traces(out_dir, rng)
    generate_mixed_scenarios(out_dir, rng)
    
    # 统计
    traces = list(out_dir.glob("*.csv"))
    total_requests = 0
    for t in traces:
        with open(t) as f:
            total_requests += sum(1 for _ in f) - 1
    
    print("\n" + "=" * 60)
    print(f"生成完成: {len(traces)} 个 trace, {total_requests} 个请求")
    print("=" * 60)


if __name__ == "__main__":
    main()

