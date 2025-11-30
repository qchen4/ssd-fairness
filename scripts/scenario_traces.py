#!/usr/bin/env python3
"""
场景化 Trace 生成器

根据四种调度算法的最优应用场景，生成针对性的测试 trace。

算法场景分析：
==============

1. Round Robin (RR) - 轮询调度
   最优场景：请求大小均匀，用户数量相近，负载均衡
   - 所有用户发送相似大小的请求
   - 请求到达率相近
   - 不需要考虑字节级公平

2. Deficit Round Robin (DRR) - 差额轮询
   最优场景：请求大小差异大，需要字节级公平
   - 某些用户发大请求，某些发小请求
   - 需要按带宽而非请求数公平分配
   - 支持权重差异化

3. Weighted Fair Queuing (WFQ/QFQ) - 加权公平队列
   最优场景：需要精确比例分配，延迟敏感
   - 需要严格按权重比例分配带宽
   - 对延迟可预测性要求高
   - 混合大小请求但需要公平

4. FLIN - 公平感知延迟干扰归一化
   最优场景：读写混合，需要保护读延迟
   - 写密集型用户与读密集型用户共存
   - 需要抑制"坏公民"（高流量、写多）
   - SSD 特性敏感的场景
"""

import argparse
import csv
import random
from pathlib import Path
from typing import Dict, List, Tuple
from dataclasses import dataclass


@dataclass
class UserProfile:
    """用户配置"""
    user_id: int
    request_count: int
    gap_range: Tuple[int, int]      # 请求间隔范围 (微秒)
    size_choices: List[int]          # 请求大小选项 (字节)
    read_ratio: float                # 读操作比例 (0-1)
    label: str = ""


def generate_user_stream(
    profile: UserProfile,
    rng: random.Random,
    start_ts: int = 0,
) -> List[Dict]:
    """生成单个用户的请求流"""
    ts = start_ts
    addr = profile.user_id * (1 << 30)  # 每用户独立地址空间
    rows = []
    label = profile.label or f"user{profile.user_id}"
    
    for _ in range(profile.request_count):
        ts += rng.randint(profile.gap_range[0], profile.gap_range[1])
        size = rng.choice(profile.size_choices)
        op = "READ" if rng.random() < profile.read_ratio else "WRITE"
        rows.append({
            "timestamp": ts,
            "process_id": label,
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


# =============================================================================
# 场景 1: RR 最优场景 - 均匀请求
# =============================================================================

def scenario_rr_optimal(rng: random.Random) -> Dict[str, List[Dict]]:
    """
    RR 最优场景：所有用户请求大小相同，到达率相近
    
    预期结果：RR 应该获得最高 fairness，因为：
    - 请求大小相同，按请求数公平 = 按字节公平
    - 简单调度足够，复杂算法无额外收益
    """
    traces = {}
    
    # 场景 1a: 完全均匀（4用户，相同请求大小和速率）
    rows = []
    for uid in range(4):
        profile = UserProfile(
            user_id=uid,
            request_count=100,
            gap_range=(80, 120),      # 相近的间隔
            size_choices=[4096],       # 固定 4KB
            read_ratio=0.7,
            label=f"uniform_user{uid}"
        )
        rows.extend(generate_user_stream(profile, rng))
    traces["rr_optimal_uniform"] = rows
    
    # 场景 1b: 略有差异但请求大小相同
    rows = []
    for uid in range(4):
        profile = UserProfile(
            user_id=uid,
            request_count=80 + uid * 10,  # 80, 90, 100, 110
            gap_range=(60 + uid * 10, 100 + uid * 10),
            size_choices=[4096],
            read_ratio=0.6,
            label=f"similar_user{uid}"
        )
        rows.extend(generate_user_stream(profile, rng))
    traces["rr_optimal_similar"] = rows
    
    return traces


# =============================================================================
# 场景 2: DRR 最优场景 - 大小差异大
# =============================================================================

def scenario_drr_optimal(rng: random.Random) -> Dict[str, List[Dict]]:
    """
    DRR 最优场景：请求大小差异大，需要字节级公平
    
    预期结果：DRR 应该获得最高 fairness，因为：
    - 大请求用户不会独占带宽
    - 小请求用户获得公平的带宽份额
    - deficit 机制确保字节级公平
    """
    traces = {}
    
    # 场景 2a: 极端大小差异（小请求 vs 大请求）
    rows = []
    # 用户0,1: 小请求（4KB），高频
    for uid in range(2):
        profile = UserProfile(
            user_id=uid,
            request_count=200,
            gap_range=(10, 30),
            size_choices=[4096],
            read_ratio=0.7,
            label=f"small_req_user{uid}"
        )
        rows.extend(generate_user_stream(profile, rng))
    # 用户2,3: 大请求（128KB），低频
    for uid in range(2, 4):
        profile = UserProfile(
            user_id=uid,
            request_count=50,
            gap_range=(100, 300),
            size_choices=[131072],  # 128KB
            read_ratio=0.7,
            label=f"large_req_user{uid}"
        )
        rows.extend(generate_user_stream(profile, rng))
    traces["drr_optimal_size_disparity"] = rows
    
    # 场景 2b: 混合大小（某些用户大小混合）
    rows = []
    for uid in range(4):
        if uid < 2:
            sizes = [4096]  # 固定小
        else:
            sizes = [4096, 16384, 65536, 131072]  # 混合
        profile = UserProfile(
            user_id=uid,
            request_count=100,
            gap_range=(20, 80),
            size_choices=sizes,
            read_ratio=0.6,
            label=f"mixed_user{uid}"
        )
        rows.extend(generate_user_stream(profile, rng))
    traces["drr_optimal_mixed_sizes"] = rows
    
    # 场景 2c: 带宽竞争（高带宽需求 vs 低带宽需求）
    rows = []
    # 高带宽用户：大请求 + 高频
    profile = UserProfile(
        user_id=0,
        request_count=100,
        gap_range=(5, 15),
        size_choices=[65536],  # 64KB
        read_ratio=0.5,
        label="bandwidth_hog"
    )
    rows.extend(generate_user_stream(profile, rng))
    # 低带宽用户：小请求 + 低频
    for uid in range(1, 4):
        profile = UserProfile(
            user_id=uid,
            request_count=50,
            gap_range=(100, 200),
            size_choices=[4096],
            read_ratio=0.8,
            label=f"light_user{uid}"
        )
        rows.extend(generate_user_stream(profile, rng))
    traces["drr_optimal_bandwidth_hog"] = rows
    
    return traces


# =============================================================================
# 场景 3: WFQ 最优场景 - 需要精确比例分配
# =============================================================================

def scenario_wfq_optimal(rng: random.Random) -> Dict[str, List[Dict]]:
    """
    WFQ 最优场景：需要按权重精确分配，延迟敏感
    
    预期结果：WFQ 应该获得最高 fairness，因为：
    - 虚拟时间确保精确比例分配
    - 延迟可预测
    - 不受请求大小影响
    """
    traces = {}
    
    # 场景 3a: 持续高负载竞争
    rows = []
    for uid in range(4):
        profile = UserProfile(
            user_id=uid,
            request_count=150,
            gap_range=(5, 20),  # 高频，持续竞争
            size_choices=[4096, 8192, 16384],
            read_ratio=0.6,
            label=f"competing_user{uid}"
        )
        rows.extend(generate_user_stream(profile, rng))
    traces["wfq_optimal_high_contention"] = rows
    
    # 场景 3b: 突发后持续（某用户突发，其他持续）
    rows = []
    # 突发用户
    profile = UserProfile(
        user_id=0,
        request_count=200,
        gap_range=(1, 5),  # 极高频突发
        size_choices=[8192],
        read_ratio=0.7,
        label="bursty_user"
    )
    rows.extend(generate_user_stream(profile, rng))
    # 持续用户
    for uid in range(1, 4):
        profile = UserProfile(
            user_id=uid,
            request_count=100,
            gap_range=(30, 60),
            size_choices=[8192],
            read_ratio=0.7,
            label=f"steady_user{uid}"
        )
        rows.extend(generate_user_stream(profile, rng))
    traces["wfq_optimal_burst_vs_steady"] = rows
    
    # 场景 3c: 延迟敏感混合负载
    rows = []
    for uid in range(6):
        profile = UserProfile(
            user_id=uid,
            request_count=80,
            gap_range=(10, 50),
            size_choices=[4096, 8192, 16384, 32768],
            read_ratio=0.65,
            label=f"latency_sensitive{uid}"
        )
        rows.extend(generate_user_stream(profile, rng))
    traces["wfq_optimal_latency_mix"] = rows
    
    return traces


# =============================================================================
# 场景 4: FLIN 最优场景 - 读写不对称，需要保护读
# =============================================================================

def scenario_flin_optimal(rng: random.Random) -> Dict[str, List[Dict]]:
    """
    FLIN 最优场景：读写混合，需要保护读延迟，抑制写密集用户
    
    预期结果：FLIN 应该获得最高 fairness，因为：
    - 写密集用户被自动节流
    - 读密集用户获得保护
    - 考虑 SSD 读写不对称特性
    """
    traces = {}
    
    # 场景 4a: 读密集 vs 写密集用户
    rows = []
    # 读密集用户（应该被保护）
    for uid in range(2):
        profile = UserProfile(
            user_id=uid,
            request_count=100,
            gap_range=(20, 60),
            size_choices=[4096, 8192],
            read_ratio=0.95,  # 95% 读
            label=f"read_heavy_user{uid}"
        )
        rows.extend(generate_user_stream(profile, rng))
    # 写密集用户（应该被节流）
    for uid in range(2, 4):
        profile = UserProfile(
            user_id=uid,
            request_count=100,
            gap_range=(20, 60),
            size_choices=[4096, 8192, 32768],
            read_ratio=0.1,  # 90% 写
            label=f"write_heavy_user{uid}"
        )
        rows.extend(generate_user_stream(profile, rng))
    traces["flin_optimal_rw_asymmetry"] = rows
    
    # 场景 4b: 流量差异大（高流量写 vs 低流量读）
    rows = []
    # 高流量写用户（"坏公民"）
    profile = UserProfile(
        user_id=0,
        request_count=200,
        gap_range=(5, 15),
        size_choices=[32768, 65536],  # 大写
        read_ratio=0.1,
        label="write_hog"
    )
    rows.extend(generate_user_stream(profile, rng))
    # 低流量读用户（应该被保护）
    for uid in range(1, 4):
        profile = UserProfile(
            user_id=uid,
            request_count=50,
            gap_range=(50, 150),
            size_choices=[4096],
            read_ratio=0.9,
            label=f"read_light{uid}"
        )
        rows.extend(generate_user_stream(profile, rng))
    traces["flin_optimal_protect_reads"] = rows
    
    # 场景 4c: GC 模拟（大量写后读延迟应该被保护）
    rows = []
    # 先大量写
    profile = UserProfile(
        user_id=0,
        request_count=150,
        gap_range=(5, 10),
        size_choices=[65536],
        read_ratio=0.0,  # 100% 写
        label="gc_trigger"
    )
    rows.extend(generate_user_stream(profile, rng, start_ts=0))
    # 后续读用户
    for uid in range(1, 3):
        profile = UserProfile(
            user_id=uid,
            request_count=80,
            gap_range=(20, 50),
            size_choices=[4096],
            read_ratio=1.0,  # 100% 读
            label=f"post_gc_reader{uid}"
        )
        rows.extend(generate_user_stream(profile, rng, start_ts=1000))
    traces["flin_optimal_gc_scenario"] = rows
    
    # 场景 4d: 混合工作负载（真实场景模拟）
    rows = []
    profiles = [
        # OLTP 用户：小读为主
        UserProfile(0, 120, (10, 30), [4096], 0.85, "oltp_user"),
        # 分析用户：大读
        UserProfile(1, 60, (50, 100), [65536, 131072], 0.9, "analytics_user"),
        # 日志用户：顺序写
        UserProfile(2, 100, (15, 40), [16384, 32768], 0.05, "logging_user"),
        # 备份用户：大写
        UserProfile(3, 40, (100, 200), [131072], 0.0, "backup_user"),
    ]
    for profile in profiles:
        rows.extend(generate_user_stream(profile, rng))
    traces["flin_optimal_realistic_mix"] = rows
    
    return traces


# =============================================================================
# 对比场景：每种算法都可能失败的场景
# =============================================================================

def scenario_challenging(rng: random.Random) -> Dict[str, List[Dict]]:
    """
    挑战场景：测试各算法的弱点
    """
    traces = {}
    
    # RR 失败场景：大小差异极大
    rows = []
    profile = UserProfile(0, 50, (50, 100), [4096], 0.7, "tiny_user")
    rows.extend(generate_user_stream(profile, rng))
    profile = UserProfile(1, 50, (50, 100), [524288], 0.7, "huge_user")  # 512KB
    rows.extend(generate_user_stream(profile, rng))
    traces["challenge_rr_fail_size"] = rows
    
    # DRR 失败场景：需要严格延迟保证
    rows = []
    for uid in range(4):
        profile = UserProfile(
            uid, 200, (1, 5), [4096, 8192], 0.6, f"latency_critical{uid}"
        )
        rows.extend(generate_user_stream(profile, rng))
    traces["challenge_drr_fail_latency"] = rows
    
    # WFQ 失败场景：读写不对称严重
    rows = []
    profile = UserProfile(0, 100, (20, 50), [4096], 0.0, "all_write")  # 100% 写
    rows.extend(generate_user_stream(profile, rng))
    profile = UserProfile(1, 100, (20, 50), [4096], 1.0, "all_read")   # 100% 读
    rows.extend(generate_user_stream(profile, rng))
    traces["challenge_wfq_fail_rw"] = rows
    
    # FLIN 失败场景：均匀负载（FLIN 的复杂性无收益）
    rows = []
    for uid in range(4):
        profile = UserProfile(
            uid, 100, (50, 100), [4096], 0.5, f"balanced_user{uid}"
        )
        rows.extend(generate_user_stream(profile, rng))
    traces["challenge_flin_fail_uniform"] = rows
    
    return traces


# =============================================================================
# 主程序
# =============================================================================

def build_all_scenarios(seed: int) -> Dict[str, List[Dict]]:
    """构建所有场景"""
    rng = random.Random(seed)
    all_traces = {}
    
    all_traces.update(scenario_rr_optimal(rng))
    all_traces.update(scenario_drr_optimal(rng))
    all_traces.update(scenario_wfq_optimal(rng))
    all_traces.update(scenario_flin_optimal(rng))
    all_traces.update(scenario_challenging(rng))
    
    return all_traces


def main() -> None:
    parser = argparse.ArgumentParser(
        description="生成针对四种调度算法的场景化测试 trace"
    )
    parser.add_argument(
        "--output-dir", 
        default="traces/scenarios", 
        help="输出目录"
    )
    parser.add_argument(
        "--seed", 
        type=int, 
        default=42, 
        help="随机种子"
    )
    parser.add_argument(
        "--scenarios",
        nargs="*",
        default=["all"],
        choices=[
            "all", "rr", "drr", "wfq", "flin", "challenge",
        ],
        help="要生成的场景类型"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="列出所有场景名称"
    )
    args = parser.parse_args()

    all_traces = build_all_scenarios(args.seed)
    
    if args.list:
        print("可用场景:")
        for name in sorted(all_traces.keys()):
            print(f"  - {name}")
        return
    
    # 过滤场景
    requested = set(args.scenarios)
    if "all" not in requested:
        filtered = {}
        for name, rows in all_traces.items():
            if any(s in name for s in requested):
                filtered[name] = rows
        all_traces = filtered
    
    # 输出
    out_dir = Path(args.output_dir)
    for name, rows in all_traces.items():
        path = out_dir / f"{name}.csv"
        write_trace(rows, path)
        print(f"生成: {path} ({len(rows)} 请求)")
    
    print(f"\n共生成 {len(all_traces)} 个场景 trace")
    print(f"\n建议运行测试:")
    print(f"  python scripts/run_scenario_tests.py --traces {out_dir}")


if __name__ == "__main__":
    main()

