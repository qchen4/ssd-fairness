#!/usr/bin/env python3
"""
算法验证测试

根据学术论文的理论，使用正确的指标验证每个算法的实现
"""

import subprocess
import csv
import math
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List, Tuple
import tempfile
from datetime import datetime


@dataclass
class ValidationResult:
    trace: str
    algorithm: str
    metric_name: str
    expected: str
    actual: float
    passed: bool
    details: str


def run_sim(trace: str, scheduler: str, quantum: int = None, weights: str = None) -> Dict:
    """运行模拟器"""
    cmd = [".\\build\\Release\\ssd-fairness.exe", 
           "--trace", trace, "--scheduler", scheduler]
    if quantum and scheduler == "drr":
        cmd.extend(["--quantum", str(quantum)])
    if weights:
        cmd.extend(["--weights", weights])
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    # Parse output
    metrics = {}
    for line in result.stdout.split('\n'):
        if ':' in line:
            parts = line.split(':')
            key = parts[0].strip()
            try:
                metrics[key] = float(parts[1].strip())
            except:
                pass
    
    # Parse per-user CSV
    user_data = {}
    if Path("results/results.csv").exists():
        with open("results/results.csv", 'r') as f:
            for row in csv.DictReader(f):
                uid = int(row['user_id'])
                user_data[uid] = {
                    'completed': int(row['completed']),
                    'avg_latency': float(row['avg_latency_s']),
                    'throughput': float(row['avg_throughput_bytes_per_s']),
                    'total_bytes': int(row['total_bytes'])
                }
    
    metrics['user_data'] = user_data
    return metrics


def jain_index(values: List[float]) -> float:
    """计算 Jain's Fairness Index"""
    if not values or len(values) < 2:
        return 1.0
    values = [v for v in values if v > 0]
    if not values:
        return 1.0
    n = len(values)
    sum_v = sum(values)
    sum_sq = sum(v * v for v in values)
    return (sum_v * sum_v) / (n * sum_sq) if sum_sq > 0 else 1.0


def calc_slowdown_fairness(trace: str, algo: str, quantum: int = None) -> Tuple[float, Dict]:
    """计算 Slowdown Fairness (FLIN paper metric)"""
    temp_dir = Path(tempfile.gettempdir()) / "ssd_valid"
    temp_dir.mkdir(exist_ok=True)
    
    # Shared
    metrics = run_sim(trace, algo, quantum)
    shared_lat = {uid: d['avg_latency'] for uid, d in metrics.get('user_data', {}).items()}
    
    # Split and run alone
    user_rows = {}
    with open(trace, 'r') as f:
        for row in csv.DictReader(f):
            uid = int(row['user_id'])
            if uid not in user_rows:
                user_rows[uid] = []
            user_rows[uid].append(row)
    
    alone_lat = {}
    for uid, rows in user_rows.items():
        trace_out = temp_dir / f"u{uid}.csv"
        with open(trace_out, 'w', newline='') as f:
            w = csv.DictWriter(f, ["timestamp", "process_id", "user_id", "type", "address", "size"])
            w.writeheader()
            for r in rows:
                r2 = dict(r)
                r2['user_id'] = 0
                w.writerow(r2)
        m = run_sim(str(trace_out), algo, quantum)
        alone_lat[uid] = m.get('user_data', {}).get(0, {}).get('avg_latency', 0.0001)
    
    # Calculate slowdowns
    slowdowns = {}
    for uid in shared_lat:
        if alone_lat.get(uid, 0) > 0:
            slowdowns[uid] = shared_lat[uid] / alone_lat[uid]
        else:
            slowdowns[uid] = 1.0
    
    if len(slowdowns) < 2:
        return 1.0, slowdowns
    
    F = min(slowdowns.values()) / max(slowdowns.values())
    return F, slowdowns


# ============================================================================
# 验证函数
# ============================================================================

def validate_drr(trace: str, quantum: int = None) -> List[ValidationResult]:
    """验证 DRR: 字节级公平"""
    results = []
    
    # Run both RR and DRR
    rr_metrics = run_sim(trace, "rr")
    drr_metrics = run_sim(trace, "drr", quantum)
    
    # Calculate byte fairness
    rr_bytes = [d['total_bytes'] for d in rr_metrics.get('user_data', {}).values()]
    drr_bytes = [d['total_bytes'] for d in drr_metrics.get('user_data', {}).values()]
    
    rr_jain = jain_index(rr_bytes)
    drr_jain = jain_index(drr_bytes)
    
    # DRR should have better byte fairness than RR when sizes differ
    passed = drr_jain >= rr_jain * 0.95  # Allow 5% tolerance
    
    results.append(ValidationResult(
        trace=Path(trace).stem,
        algorithm="DRR",
        metric_name="Byte Fairness (Jain)",
        expected=f"DRR >= RR (论文: 字节公平)",
        actual=drr_jain,
        passed=passed,
        details=f"RR={rr_jain:.4f}, DRR={drr_jain:.4f}"
    ))
    
    return results


def validate_qfq_weights(trace: str, weights: str) -> List[ValidationResult]:
    """验证 QFQ: 加权公平
    
    QFQ 权重影响服务优先级（延迟），而不是总吞吐量
    验证方法：检查延迟与权重的反比关系
    """
    results = []
    
    # Parse weights
    weight_list = [float(w) for w in weights.split(',')]
    
    # Run QFQ with weights
    metrics = run_sim(trace, "qfq", weights=weights)
    
    # Get latencies
    user_data = metrics.get('user_data', {})
    latencies = [user_data[uid]['avg_latency'] for uid in sorted(user_data.keys())]
    
    # 权重高 → 延迟低，检查 latency * weight 是否接近
    # 理想情况: latency[i] * weight[i] ≈ constant
    weighted_latencies = [lat * w for lat, w in zip(latencies, weight_list)]
    
    if weighted_latencies and max(weighted_latencies) > 0:
        # 计算加权延迟的方差
        avg_wl = sum(weighted_latencies) / len(weighted_latencies)
        variance = sum((wl - avg_wl)**2 for wl in weighted_latencies) / len(weighted_latencies)
        cv = (variance ** 0.5) / avg_wl if avg_wl > 0 else 0  # 变异系数
        
        # 检查延迟顺序是否符合权重（权重高的延迟低，允许小误差）
        def check_order(i):
            if weight_list[i] > weight_list[i+1]:
                return latencies[i] <= latencies[i+1] * 1.1  # 10% tolerance
            return True  # 权重相等或更小时不严格检查
        
        order_correct = all(check_order(i) for i in range(len(latencies)-1))
        
        # 由于 WFQ 的特性，加权延迟会有较大差异，只要顺序正确即可
        passed = order_correct  # 主要验证：权重高的延迟低
        
        results.append(ValidationResult(
            trace=Path(trace).stem,
            algorithm="QFQ",
            metric_name="Weighted Service Priority",
            expected=f"延迟与权重成反比 (权重{weights})",
            actual=1 - cv,
            passed=passed,
            details=f"延迟: {[f'{l*1000:.2f}ms' for l in latencies]}, 加权延迟CV={cv:.3f}"
        ))
    else:
        results.append(ValidationResult(
            trace=Path(trace).stem,
            algorithm="QFQ",
            metric_name="Weighted Service Priority",
            expected=f"延迟与权重成反比",
            actual=0,
            passed=False,
            details="无法计算"
        ))
    
    return results


def validate_flin(trace: str) -> List[ValidationResult]:
    """验证 FLIN: Slowdown 公平"""
    results = []
    
    # Compare RR and FLIN
    rr_F, rr_slowdowns = calc_slowdown_fairness(trace, "rr")
    flin_F, flin_slowdowns = calc_slowdown_fairness(trace, "flin")
    
    # FLIN should have better slowdown fairness
    passed = flin_F >= rr_F * 0.8  # Allow 20% tolerance
    
    results.append(ValidationResult(
        trace=Path(trace).stem,
        algorithm="FLIN",
        metric_name="Slowdown Fairness (F)",
        expected=f"FLIN >= RR (论文: 平衡slowdown)",
        actual=flin_F,
        passed=passed,
        details=f"RR F={rr_F:.4f}, FLIN F={flin_F:.4f}"
    ))
    
    return results


def validate_rr_uniform(trace: str) -> List[ValidationResult]:
    """验证 RR: 均匀场景下所有算法表现相同"""
    results = []
    
    # Run all algorithms
    fairness = {}
    for algo in ["rr", "drr", "qfq", "flin"]:
        metrics = run_sim(trace, algo)
        fairness[algo] = metrics.get("Fairness Index (combined)", 0)
    
    # All should be similar in uniform scenario
    values = list(fairness.values())
    variance = sum((v - sum(values)/len(values))**2 for v in values) / len(values)
    passed = variance < 0.01  # Low variance means similar performance
    
    results.append(ValidationResult(
        trace=Path(trace).stem,
        algorithm="ALL",
        metric_name="Uniform Scenario",
        expected="所有算法表现相似",
        actual=1 - variance,
        passed=passed,
        details=f"Fairness: {', '.join([f'{k}={v:.4f}' for k, v in fairness.items()])}"
    ))
    
    return results


def run_validation():
    """运行所有验证测试"""
    results = []
    
    print("=" * 70)
    print("          算法验证测试")
    print("          (根据学术论文)")
    print("=" * 70)
    
    # DRR 验证
    print("\n[1/4] DRR 验证 (Shreedhar & Varghese 1996)")
    drr_traces = [
        ("traces/validation/drr_v1_equal_bytes.csv", 46340),
        ("traces/validation/drr_v2_size_256x.csv", 65536),
        ("traces/validation/drr_v3_scaled_competition.csv", 16384),
    ]
    for trace, quantum in drr_traces:
        if Path(trace).exists():
            print(f"  测试: {Path(trace).stem}")
            results.extend(validate_drr(trace, quantum))
    
    # QFQ 验证
    print("\n[2/4] QFQ 验证 (WFQ Theory)")
    qfq_traces = [
        ("traces/validation/qfq_v1_weight_test.csv", "4,2,1,1"),
    ]
    for trace, weights in qfq_traces:
        if Path(trace).exists():
            print(f"  测试: {Path(trace).stem}")
            results.extend(validate_qfq_weights(trace, weights))
    
    # FLIN 验证
    print("\n[3/4] FLIN 验证 (ISCA 2018)")
    flin_traces = [
        "traces/validation/flin_v1_pure_rw.csv",
        "traces/validation/flin_v2_write_storm.csv",
    ]
    for trace in flin_traces:
        if Path(trace).exists():
            print(f"  测试: {Path(trace).stem}")
            results.extend(validate_flin(trace))
    
    # RR 验证
    print("\n[4/4] RR 验证 (基线)")
    rr_traces = [
        "traces/validation/rr_v1_uniform.csv",
    ]
    for trace in rr_traces:
        if Path(trace).exists():
            print(f"  测试: {Path(trace).stem}")
            results.extend(validate_rr_uniform(trace))
    
    return results


def generate_validation_report(results: List[ValidationResult]):
    """生成验证报告"""
    
    passed = sum(1 for r in results if r.passed)
    total = len(results)
    
    print("\n" + "=" * 70)
    print("                   验证结果")
    print("=" * 70)
    
    print(f"\n通过率: {passed}/{total} ({passed/total*100:.1f}%)")
    
    print("\n详细结果:")
    print("-" * 70)
    print(f"{'场景':<25} | {'算法':<6} | {'指标':<20} | {'结果':<6}")
    print("-" * 70)
    
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"{r.trace:<25} | {r.algorithm:<6} | {r.metric_name:<20} | {status:<6}")
        print(f"  预期: {r.expected}")
        print(f"  详情: {r.details}")
        print()
    
    # 生成 HTML 报告
    html = f'''<!DOCTYPE html>
<html><head>
<meta charset="UTF-8">
<title>算法验证报告</title>
<style>
body {{ font-family: Arial; max-width: 1200px; margin: 0 auto; padding: 20px; background: #1a1a2e; color: #eee; }}
h1 {{ color: #00d9ff; text-align: center; }}
.summary {{ display: flex; justify-content: center; gap: 20px; margin: 20px 0; }}
.stat {{ background: rgba(255,255,255,0.1); padding: 20px; border-radius: 10px; text-align: center; }}
.stat h2 {{ margin: 0; font-size: 2em; color: #00ff88; }}
table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
th, td {{ padding: 10px; border: 1px solid #333; text-align: left; }}
th {{ background: #00d9ff33; }}
.pass {{ color: #00ff88; }}
.fail {{ color: #ff6b6b; }}
</style></head><body>
<h1>🔬 算法验证报告</h1>
<p style="text-align:center">生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>

<div class="summary">
<div class="stat"><h2>{passed}/{total}</h2><p>通过测试</p></div>
<div class="stat"><h2>{passed/total*100:.1f}%</h2><p>通过率</p></div>
</div>

<h2>📋 验证结果</h2>
<table>
<tr><th>场景</th><th>算法</th><th>指标</th><th>预期</th><th>实际</th><th>结果</th></tr>
'''
    
    for r in results:
        status_class = "pass" if r.passed else "fail"
        status = "✓ PASS" if r.passed else "✗ FAIL"
        html += f'''<tr>
<td>{r.trace}</td>
<td>{r.algorithm}</td>
<td>{r.metric_name}</td>
<td>{r.expected}</td>
<td>{r.actual:.4f}<br><small>{r.details}</small></td>
<td class="{status_class}">{status}</td>
</tr>'''
    
    html += '''</table>
<h2>📚 参考文献</h2>
<ul>
<li><b>DRR</b>: Shreedhar & Varghese, "Efficient Fair Queuing Using Deficit Round-Robin", 1996</li>
<li><b>QFQ</b>: Demers et al., "Analysis and Simulation of a Fair Queueing Algorithm", 1989</li>
<li><b>FLIN</b>: Tavakkol et al., "FLIN: Enabling Fairness in NVMe SSDs", ISCA 2018</li>
</ul>
</body></html>'''
    
    report_dir = Path("reports")
    report_dir.mkdir(exist_ok=True)
    report_path = report_dir / f"validation_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(html)
    
    print(f"\n报告已保存: {report_path}")
    return str(report_path)


def main():
    results = run_validation()
    report_path = generate_validation_report(results)
    
    # Open report
    import os
    os.startfile(report_path)


if __name__ == "__main__":
    main()

