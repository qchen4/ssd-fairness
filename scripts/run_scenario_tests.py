#!/usr/bin/env python3
"""
场景化测试运行器

运行所有场景 trace，比较四种调度算法的 fairness 表现，
并生成分析报告。

使用方法:
    1. 生成场景 trace:
       python scripts/scenario_traces.py
    
    2. 运行场景测试:
       python scripts/run_scenario_tests.py
    
    3. 查看报告:
       cat results/scenario_analysis/report.txt
"""

import argparse
import csv
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple
from collections import defaultdict


# 场景到最优算法的映射
SCENARIO_EXPECTED_WINNER = {
    # RR 最优场景
    "rr_optimal_uniform": "rr",
    "rr_optimal_similar": "rr",
    
    # DRR 最优场景
    "drr_optimal_size_disparity": "drr",
    "drr_optimal_mixed_sizes": "drr",
    "drr_optimal_bandwidth_hog": "drr",
    
    # WFQ 最优场景
    "wfq_optimal_high_contention": "qfq",
    "wfq_optimal_burst_vs_steady": "qfq",
    "wfq_optimal_latency_mix": "qfq",
    
    # FLIN 最优场景
    "flin_optimal_rw_asymmetry": "flin",
    "flin_optimal_protect_reads": "flin",
    "flin_optimal_gc_scenario": "flin",
    "flin_optimal_realistic_mix": "flin",
    
    # 挑战场景（预期失败）
    "challenge_rr_fail_size": "drr",      # RR 应该失败，DRR 应该赢
    "challenge_drr_fail_latency": "qfq",  # DRR 可能延迟差，WFQ 应该更好
    "challenge_wfq_fail_rw": "flin",      # WFQ 不考虑读写，FLIN 应该赢
    "challenge_flin_fail_uniform": "rr",  # 均匀场景，简单算法即可
}


def parse_simulator_output(stdout: str) -> Dict[str, float]:
    """解析模拟器输出"""
    metrics = {}
    for line in stdout.splitlines():
        if line.startswith("Fairness Index (combined):"):
            metrics["fairness_index"] = float(line.split(":")[1].strip())
        elif line.startswith("Fairness Index (throughput):"):
            metrics["throughput_fairness"] = float(line.split(":")[1].strip())
        elif line.startswith("Fairness Index (latency):"):
            metrics["latency_fairness"] = float(line.split(":")[1].strip())
        elif line.startswith("Throughput (MB/s):"):
            metrics["throughput_MBps"] = float(line.split(":")[1].strip())
        elif line.startswith("Average latency"):
            metrics["avg_latency_s"] = float(line.split(":")[1].strip())
        elif line.startswith("Completed requests:"):
            parts = line.split()
            if len(parts) >= 4:
                metrics["completed"] = int(parts[2])
                runtime_str = parts[4].rstrip("s")
                metrics["runtime_s"] = float(runtime_str)
    return metrics


def run_single_test(
    binary: Path, 
    trace: Path, 
    scheduler: str, 
    results_dir: Path
) -> Dict:
    """运行单个测试"""
    result_file = results_dir / f"{trace.stem}_{scheduler}.csv"
    result_file.parent.mkdir(parents=True, exist_ok=True)
    
    cmd = [
        str(binary),
        "--trace", str(trace),
        "--scheduler", scheduler,
        "--results", str(result_file),
    ]
    
    try:
        proc = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            check=True,
            timeout=60
        )
        metrics = parse_simulator_output(proc.stdout)
        metrics["status"] = "success"
    except subprocess.CalledProcessError as e:
        metrics = {"status": "error", "error": e.stderr}
    except subprocess.TimeoutExpired:
        metrics = {"status": "timeout"}
    
    metrics.update({
        "trace": trace.stem,
        "scheduler": scheduler,
        "results_path": str(result_file),
    })
    return metrics


def analyze_scenario(
    scenario_name: str, 
    results: Dict[str, Dict]
) -> Dict:
    """分析单个场景的结果"""
    analysis = {
        "scenario": scenario_name,
        "expected_winner": SCENARIO_EXPECTED_WINNER.get(scenario_name, "unknown"),
    }
    
    # 找出 fairness 最高的算法
    valid_results = {
        sched: r for sched, r in results.items() 
        if r.get("status") == "success" and "fairness_index" in r
    }
    
    if not valid_results:
        analysis["actual_winner"] = "N/A"
        analysis["match"] = False
        return analysis
    
    winner = max(valid_results.keys(), key=lambda s: valid_results[s]["fairness_index"])
    analysis["actual_winner"] = winner
    analysis["match"] = (winner == analysis["expected_winner"])
    
    # 记录各算法得分
    for sched, r in valid_results.items():
        analysis[f"{sched}_fairness"] = r.get("fairness_index", 0)
        analysis[f"{sched}_latency"] = r.get("avg_latency_s", 0)
        analysis[f"{sched}_throughput"] = r.get("throughput_MBps", 0)
    
    return analysis


def generate_report(
    all_results: Dict[str, Dict[str, Dict]],
    output_path: Path
) -> str:
    """生成分析报告"""
    lines = []
    lines.append("=" * 80)
    lines.append("           SSD 调度算法场景化测试报告")
    lines.append("=" * 80)
    lines.append("")
    
    # 统计
    total = 0
    correct = 0
    by_algorithm = defaultdict(lambda: {"expected": 0, "actual": 0})
    
    # 按场景类型分组
    scenario_groups = {
        "RR 最优场景": [],
        "DRR 最优场景": [],
        "WFQ 最优场景": [],
        "FLIN 最优场景": [],
        "挑战场景": [],
    }
    
    for scenario_name, results in all_results.items():
        analysis = analyze_scenario(scenario_name, results)
        total += 1
        if analysis["match"]:
            correct += 1
        
        expected = analysis["expected_winner"]
        actual = analysis["actual_winner"]
        by_algorithm[expected]["expected"] += 1
        if actual != "N/A":
            by_algorithm[actual]["actual"] += 1
        
        # 分组
        if "rr_optimal" in scenario_name:
            scenario_groups["RR 最优场景"].append((scenario_name, analysis, results))
        elif "drr_optimal" in scenario_name:
            scenario_groups["DRR 最优场景"].append((scenario_name, analysis, results))
        elif "wfq_optimal" in scenario_name:
            scenario_groups["WFQ 最优场景"].append((scenario_name, analysis, results))
        elif "flin_optimal" in scenario_name:
            scenario_groups["FLIN 最优场景"].append((scenario_name, analysis, results))
        elif "challenge" in scenario_name:
            scenario_groups["挑战场景"].append((scenario_name, analysis, results))
    
    # 总体统计
    lines.append("【总体统计】")
    lines.append(f"  测试场景数: {total}")
    lines.append(f"  预期匹配数: {correct}")
    lines.append(f"  匹配率: {correct/total*100:.1f}%" if total > 0 else "  匹配率: N/A")
    lines.append("")
    
    # 各算法统计
    lines.append("【各算法表现】")
    for algo in ["rr", "drr", "qfq", "flin"]:
        exp = by_algorithm[algo]["expected"]
        act = by_algorithm[algo]["actual"]
        lines.append(f"  {algo.upper():5s}: 预期最优 {exp} 次, 实际最优 {act} 次")
    lines.append("")
    
    # 详细结果
    for group_name, scenarios in scenario_groups.items():
        if not scenarios:
            continue
        lines.append("-" * 80)
        lines.append(f"【{group_name}】")
        lines.append("-" * 80)
        
        for scenario_name, analysis, results in scenarios:
            expected = analysis["expected_winner"]
            actual = analysis["actual_winner"]
            match_str = "[OK]" if analysis["match"] else "[X]"
            
            lines.append(f"\n  场景: {scenario_name}")
            lines.append(f"  预期最优: {expected.upper()}, 实际最优: {actual.upper()} [{match_str}]")
            
            # Fairness 得分表
            lines.append("  Fairness 得分:")
            for algo in ["rr", "drr", "qfq", "flin"]:
                score = analysis.get(f"{algo}_fairness", "N/A")
                if isinstance(score, float):
                    marker = " *" if algo == actual else ""
                    lines.append(f"    {algo.upper():5s}: {score:.4f}{marker}")
            
            # 延迟和吞吐量
            lines.append("  平均延迟 (s) / 吞吐量 (MB/s):")
            for algo in ["rr", "drr", "qfq", "flin"]:
                lat = analysis.get(f"{algo}_latency", "N/A")
                thr = analysis.get(f"{algo}_throughput", "N/A")
                if isinstance(lat, float) and isinstance(thr, float):
                    lines.append(f"    {algo.upper():5s}: {lat:.6f} / {thr:.2f}")
    
    lines.append("")
    lines.append("=" * 80)
    lines.append("                          报告结束")
    lines.append("=" * 80)
    
    report = "\n".join(lines)
    
    # 写入文件
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")
    
    return report


def save_csv_summary(
    all_results: Dict[str, Dict[str, Dict]], 
    output_path: Path
) -> None:
    """保存 CSV 格式的汇总结果"""
    rows = []
    for scenario_name, results in all_results.items():
        analysis = analyze_scenario(scenario_name, results)
        row = {
            "scenario": scenario_name,
            "expected_winner": analysis["expected_winner"],
            "actual_winner": analysis["actual_winner"],
            "match": analysis["match"],
        }
        for algo in ["rr", "drr", "qfq", "flin"]:
            row[f"{algo}_fairness"] = analysis.get(f"{algo}_fairness", "")
            row[f"{algo}_latency"] = analysis.get(f"{algo}_latency", "")
            row[f"{algo}_throughput"] = analysis.get(f"{algo}_throughput", "")
        rows.append(row)
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "scenario", "expected_winner", "actual_winner", "match",
        "rr_fairness", "rr_latency", "rr_throughput",
        "drr_fairness", "drr_latency", "drr_throughput",
        "qfq_fairness", "qfq_latency", "qfq_throughput",
        "flin_fairness", "flin_latency", "flin_throughput",
    ]
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def find_binary() -> str:
    """自动查找模拟器可执行文件"""
    import platform
    
    candidates = [
        "build/ssd-fairness",
        "build/ssd-fairness.exe",
        "build/Debug/ssd-fairness.exe",
        "build/Release/ssd-fairness.exe",
        "build/bin/ssd-fairness",
        "build/bin/ssd-fairness.exe",
    ]
    
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return str(path)
    
    # 在 Windows 上，检查没有扩展名的文件是否可执行
    if platform.system() == "Windows":
        return "build/ssd-fairness.exe"  # 默认
    return "build/ssd-fairness"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="运行场景化测试并生成分析报告"
    )
    parser.add_argument(
        "--binary",
        default=None,
        help="模拟器可执行文件路径（默认自动检测）"
    )
    parser.add_argument(
        "--traces",
        default="traces/scenarios",
        help="场景 trace 目录"
    )
    parser.add_argument(
        "--output-dir",
        default="results/scenario_analysis",
        help="结果输出目录"
    )
    parser.add_argument(
        "--schedulers",
        nargs="*",
        default=["rr", "drr", "qfq", "flin"],
        help="要测试的调度算法"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="显示详细输出"
    )
    args = parser.parse_args()
    
    binary_path = args.binary if args.binary else find_binary()
    binary = Path(binary_path)
    if not binary.exists():
        print(f"错误: 找不到模拟器 {binary}")
        print()
        print("请先编译项目:")
        print("  Windows (MSVC):")
        print("    mkdir build && cd build")
        print("    cmake ..")
        print("    cmake --build . --config Release")
        print()
        print("  Linux/Mac:")
        print("    mkdir -p build && cd build")
        print("    cmake ..")
        print("    make")
        sys.exit(1)
    
    trace_dir = Path(args.traces)
    if not trace_dir.exists():
        print(f"错误: 找不到 trace 目录 {trace_dir}")
        print("请先生成场景 trace: python scripts/scenario_traces.py")
        sys.exit(1)
    
    traces = sorted(trace_dir.glob("*.csv"))
    if not traces:
        print(f"错误: {trace_dir} 中没有 CSV 文件")
        sys.exit(1)
    
    output_dir = Path(args.output_dir)
    
    # 运行所有测试
    all_results: Dict[str, Dict[str, Dict]] = {}
    total_tests = len(traces) * len(args.schedulers)
    current = 0
    
    print(f"运行 {len(traces)} 个场景 × {len(args.schedulers)} 个算法 = {total_tests} 个测试")
    print()
    
    for trace in traces:
        scenario_name = trace.stem
        all_results[scenario_name] = {}
        
        for scheduler in args.schedulers:
            current += 1
            print(f"[{current}/{total_tests}] {scenario_name} + {scheduler}...", end=" ")
            
            result = run_single_test(binary, trace, scheduler, output_dir)
            all_results[scenario_name][scheduler] = result
            
            if result["status"] == "success":
                fairness = result.get("fairness_index", 0)
                print(f"fairness={fairness:.4f}")
            else:
                print(f"[{result['status']}]")
    
    print()
    
    # 生成报告
    report_path = output_dir / "report.txt"
    report = generate_report(all_results, report_path)
    print(report)
    
    # 保存 CSV
    csv_path = output_dir / "summary.csv"
    save_csv_summary(all_results, csv_path)
    print(f"\nCSV 汇总已保存: {csv_path}")
    print(f"详细报告已保存: {report_path}")


if __name__ == "__main__":
    main()

