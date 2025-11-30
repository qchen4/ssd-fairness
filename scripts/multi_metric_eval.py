#!/usr/bin/env python3
"""
多指标公平性评估系统

每个算法使用其最适合的指标进行评估:
- RR: 请求公平性 (Request Fairness)
- DRR: 字节公平性 (Byte Fairness)
- QFQ: 加权公平性 (Weighted Fairness)
- FLIN: Slowdown 公平性 (Slowdown Fairness)
"""

import subprocess
import csv
import math
import tempfile
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List, Tuple
from datetime import datetime
import json


@dataclass
class MultiMetricResult:
    """多指标结果"""
    trace: str
    # 各项指标
    request_fairness: Dict[str, float]   # Jain(requests)
    byte_fairness: Dict[str, float]      # Jain(bytes)
    latency_fairness: Dict[str, float]   # Jain(1/latency)
    slowdown_fairness: Dict[str, float]  # min(S)/max(S)
    # 每个算法的"主场"得分
    home_scores: Dict[str, float]
    # 综合得分
    overall_winner: str


def run_sim(trace: str, scheduler: str, quantum: int = None) -> Dict:
    """运行模拟器并获取结果"""
    cmd = [".\\build\\Release\\ssd-fairness.exe", 
           "--trace", trace, "--scheduler", scheduler]
    if quantum and scheduler == "drr":
        cmd.extend(["--quantum", str(quantum)])
    
    subprocess.run(cmd, capture_output=True, text=True)
    
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
    return user_data


def jain_index(values: List[float]) -> float:
    """Jain's Fairness Index"""
    values = [v for v in values if v > 0]
    if len(values) < 2:
        return 1.0
    n = len(values)
    sum_v = sum(values)
    sum_sq = sum(v * v for v in values)
    return (sum_v * sum_v) / (n * sum_sq) if sum_sq > 0 else 1.0


def calc_request_fairness(user_data: Dict) -> float:
    """请求公平性: Jain(completed_requests)"""
    requests = [d['completed'] for d in user_data.values()]
    return jain_index(requests)


def calc_byte_fairness(user_data: Dict) -> float:
    """字节公平性: Jain(total_bytes)"""
    bytes_list = [d['total_bytes'] for d in user_data.values()]
    return jain_index(bytes_list)


def calc_latency_fairness(user_data: Dict) -> float:
    """延迟公平性: Jain(1/latency) - 延迟越低越好"""
    inv_latencies = [1.0 / d['avg_latency'] if d['avg_latency'] > 0 else 0 
                    for d in user_data.values()]
    return jain_index(inv_latencies)


def calc_slowdown_fairness(trace: str, algo: str, quantum: int = None) -> float:
    """Slowdown 公平性: min(S)/max(S)"""
    temp_dir = Path(tempfile.gettempdir()) / "ssd_multi"
    temp_dir.mkdir(exist_ok=True)
    
    # Shared run
    shared_data = run_sim(trace, algo, quantum)
    if not shared_data:
        return 0.0
    
    # Split trace by user
    user_rows = {}
    with open(trace, 'r') as f:
        for row in csv.DictReader(f):
            uid = int(row['user_id'])
            if uid not in user_rows:
                user_rows[uid] = []
            user_rows[uid].append(row)
    
    # Alone runs
    alone_latencies = {}
    for uid, rows in user_rows.items():
        trace_out = temp_dir / f"alone_{uid}.csv"
        with open(trace_out, 'w', newline='') as f:
            w = csv.DictWriter(f, ["timestamp", "process_id", "user_id", "type", "address", "size"])
            w.writeheader()
            for r in rows:
                r2 = dict(r)
                r2['user_id'] = 0
                w.writerow(r2)
        alone_data = run_sim(str(trace_out), algo, quantum)
        alone_latencies[uid] = alone_data.get(0, {}).get('avg_latency', 0.0001)
    
    # Calculate slowdowns
    slowdowns = []
    for uid, data in shared_data.items():
        alone_lat = alone_latencies.get(uid, 0.0001)
        if alone_lat > 0:
            slowdowns.append(data['avg_latency'] / alone_lat)
        else:
            slowdowns.append(1.0)
    
    if len(slowdowns) < 2:
        return 1.0
    
    return min(slowdowns) / max(slowdowns) if max(slowdowns) > 0 else 1.0


def evaluate_trace(trace: str) -> MultiMetricResult:
    """对一个 trace 进行多指标评估"""
    algos = ["rr", "drr", "qfq", "flin"]
    
    # 计算 quantum
    with open(trace, 'r') as f:
        sizes = [int(r['size']) for r in csv.DictReader(f)]
    quantum = int(math.sqrt(min(sizes) * max(sizes)))
    
    # 收集所有指标
    request_fairness = {}
    byte_fairness = {}
    latency_fairness = {}
    slowdown_fairness = {}
    
    for algo in algos:
        q = quantum if algo == "drr" else None
        user_data = run_sim(trace, algo, q)
        
        request_fairness[algo] = calc_request_fairness(user_data)
        byte_fairness[algo] = calc_byte_fairness(user_data)
        latency_fairness[algo] = calc_latency_fairness(user_data)
        slowdown_fairness[algo] = calc_slowdown_fairness(trace, algo, q)
    
    # 每个算法在其"主场"指标上的得分
    home_scores = {
        "rr": request_fairness["rr"],
        "drr": byte_fairness["drr"],
        "qfq": latency_fairness["qfq"],  # QFQ 优化延迟公平
        "flin": slowdown_fairness["flin"]
    }
    
    # 综合评分：每个算法在所有指标上的平均排名
    rankings = {algo: 0 for algo in algos}
    
    for metric_dict in [request_fairness, byte_fairness, latency_fairness, slowdown_fairness]:
        sorted_algos = sorted(algos, key=lambda a: metric_dict[a], reverse=True)
        for rank, algo in enumerate(sorted_algos):
            rankings[algo] += rank
    
    # 平均排名最低的获胜
    overall_winner = min(rankings.keys(), key=lambda k: rankings[k])
    
    return MultiMetricResult(
        trace=Path(trace).stem,
        request_fairness=request_fairness,
        byte_fairness=byte_fairness,
        latency_fairness=latency_fairness,
        slowdown_fairness=slowdown_fairness,
        home_scores=home_scores,
        overall_winner=overall_winner
    )


def run_multi_metric_evaluation():
    """运行多指标评估"""
    print("=" * 70)
    print("          多指标公平性评估系统")
    print("=" * 70)
    print()
    print("评估指标:")
    print("  1. Request Fairness - Jain(requests/user) - RR 主场")
    print("  2. Byte Fairness    - Jain(bytes/user)    - DRR 主场")
    print("  3. Latency Fairness - Jain(1/latency)     - QFQ 主场")
    print("  4. Slowdown Fairness - min(S)/max(S)      - FLIN 主场")
    print()
    
    # 收集所有 traces
    traces = []
    for pattern in ["traces/validation/*.csv", "traces/competition/*.csv"]:
        traces.extend(Path(".").glob(pattern))
    
    traces = sorted(traces)[:15]  # 限制数量
    print(f"评估 {len(traces)} 个场景...")
    print()
    
    results = []
    for trace in traces:
        print(f"测试: {trace.stem}")
        result = evaluate_trace(str(trace))
        results.append(result)
        print(f"  综合胜者: {result.overall_winner.upper()}")
    
    return results


def generate_multi_metric_report(results: List[MultiMetricResult]):
    """生成多指标报告"""
    
    # 统计
    wins = {"rr": 0, "drr": 0, "qfq": 0, "flin": 0}
    home_wins = {"rr": 0, "drr": 0, "qfq": 0, "flin": 0}
    
    for r in results:
        wins[r.overall_winner] += 1
        # 检查每个算法在主场的表现
        for algo in ["rr", "drr", "qfq", "flin"]:
            if algo == "rr":
                metric = r.request_fairness
            elif algo == "drr":
                metric = r.byte_fairness
            elif algo == "qfq":
                metric = r.latency_fairness
            else:
                metric = r.slowdown_fairness
            
            if metric[algo] == max(metric.values()):
                home_wins[algo] += 1
    
    print("\n" + "=" * 70)
    print("                    评估结果")
    print("=" * 70)
    
    print("\n综合排名胜出次数:")
    for algo, count in sorted(wins.items(), key=lambda x: -x[1]):
        print(f"  {algo.upper()}: {count} 次")
    
    print("\n主场指标胜出次数:")
    metrics_names = {"rr": "Request", "drr": "Byte", "qfq": "Latency", "flin": "Slowdown"}
    for algo, count in home_wins.items():
        print(f"  {algo.upper()} ({metrics_names[algo]} Fairness): {count}/{len(results)}")
    
    # 生成 HTML 报告
    html = f'''<!DOCTYPE html>
<html><head>
<meta charset="UTF-8">
<title>多指标公平性评估报告</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
body {{ font-family: 'Segoe UI', Arial; max-width: 1400px; margin: 0 auto; padding: 20px; 
       background: linear-gradient(135deg, #0f0c29, #302b63, #24243e); color: #eee; min-height: 100vh; }}
h1 {{ text-align: center; color: #00d9ff; text-shadow: 0 0 20px rgba(0,217,255,0.5); }}
.subtitle {{ text-align: center; color: #888; margin-bottom: 30px; }}
.metrics-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin: 20px 0; }}
.metric-card {{ background: rgba(255,255,255,0.05); border-radius: 15px; padding: 20px; text-align: center;
               border: 1px solid rgba(255,255,255,0.1); }}
.metric-card h3 {{ margin: 0 0 10px; font-size: 0.9em; color: #aaa; }}
.metric-card .value {{ font-size: 2em; font-weight: bold; }}
.rr {{ color: #ff6b6b; }}
.drr {{ color: #4ecdc4; }}
.qfq {{ color: #ffe66d; }}
.flin {{ color: #95e1d3; }}
.chart-container {{ background: rgba(255,255,255,0.05); border-radius: 15px; padding: 20px; margin: 20px 0; }}
.chart-row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
th, td {{ padding: 10px; border: 1px solid #333; text-align: center; }}
th {{ background: rgba(0,217,255,0.2); color: #00d9ff; }}
.best {{ background: rgba(0,255,136,0.2); font-weight: bold; }}
</style></head><body>
<h1>📊 多指标公平性评估报告</h1>
<p class="subtitle">每个算法使用其最适合的指标进行评估 | {datetime.now().strftime("%Y-%m-%d %H:%M")}</p>

<h2>🎯 评估指标说明</h2>
<div class="metrics-grid">
    <div class="metric-card">
        <h3>REQUEST FAIRNESS</h3>
        <div class="value rr">RR</div>
        <p>Jain(requests/user)<br>请求数公平</p>
    </div>
    <div class="metric-card">
        <h3>BYTE FAIRNESS</h3>
        <div class="value drr">DRR</div>
        <p>Jain(bytes/user)<br>字节数公平</p>
    </div>
    <div class="metric-card">
        <h3>LATENCY FAIRNESS</h3>
        <div class="value qfq">QFQ</div>
        <p>Jain(1/latency)<br>延迟公平</p>
    </div>
    <div class="metric-card">
        <h3>SLOWDOWN FAIRNESS</h3>
        <div class="value flin">FLIN</div>
        <p>min(S)/max(S)<br>减速公平</p>
    </div>
</div>

<div class="chart-row">
<div class="chart-container">
    <h2>🏆 综合排名胜出</h2>
    <canvas id="winsChart"></canvas>
</div>
<div class="chart-container">
    <h2>🏠 主场指标胜出</h2>
    <canvas id="homeChart"></canvas>
</div>
</div>

<h2>📋 详细结果</h2>
<table>
<tr>
    <th>场景</th>
    <th>Request<br>(RR主场)</th>
    <th>Byte<br>(DRR主场)</th>
    <th>Latency<br>(QFQ主场)</th>
    <th>Slowdown<br>(FLIN主场)</th>
    <th>综合胜者</th>
</tr>
'''
    
    for r in results:
        # Find best for each metric
        req_best = max(r.request_fairness.values())
        byte_best = max(r.byte_fairness.values())
        lat_best = max(r.latency_fairness.values())
        slow_best = max(r.slowdown_fairness.values())
        
        def format_cell(metric_dict, best_val):
            cells = []
            for algo in ["rr", "drr", "qfq", "flin"]:
                val = metric_dict[algo]
                cls = "best" if abs(val - best_val) < 0.001 else ""
                cells.append(f'<span class="{cls} {algo}">{val:.3f}</span>')
            return " | ".join(cells)
        
        html += f'''<tr>
    <td>{r.trace}</td>
    <td>{format_cell(r.request_fairness, req_best)}</td>
    <td>{format_cell(r.byte_fairness, byte_best)}</td>
    <td>{format_cell(r.latency_fairness, lat_best)}</td>
    <td>{format_cell(r.slowdown_fairness, slow_best)}</td>
    <td class="{r.overall_winner}">{r.overall_winner.upper()}</td>
</tr>'''
    
    html += f'''</table>

<script>
new Chart(document.getElementById('winsChart'), {{
    type: 'doughnut',
    data: {{
        labels: ['RR', 'DRR', 'QFQ', 'FLIN'],
        datasets: [{{
            data: [{wins['rr']}, {wins['drr']}, {wins['qfq']}, {wins['flin']}],
            backgroundColor: ['#ff6b6b', '#4ecdc4', '#ffe66d', '#95e1d3']
        }}]
    }},
    options: {{ plugins: {{ legend: {{ labels: {{ color: '#eee' }} }} }} }}
}});

new Chart(document.getElementById('homeChart'), {{
    type: 'bar',
    data: {{
        labels: ['RR (Request)', 'DRR (Byte)', 'QFQ (Latency)', 'FLIN (Slowdown)'],
        datasets: [{{
            label: '主场胜出次数',
            data: [{home_wins['rr']}, {home_wins['drr']}, {home_wins['qfq']}, {home_wins['flin']}],
            backgroundColor: ['#ff6b6b', '#4ecdc4', '#ffe66d', '#95e1d3']
        }}]
    }},
    options: {{
        plugins: {{ legend: {{ display: false }} }},
        scales: {{
            y: {{ ticks: {{ color: '#aaa' }}, grid: {{ color: 'rgba(255,255,255,0.1)' }}, max: {len(results)} }},
            x: {{ ticks: {{ color: '#aaa' }} }}
        }}
    }}
}});
</script>
</body></html>'''
    
    report_dir = Path("reports")
    report_dir.mkdir(exist_ok=True)
    report_path = report_dir / f"multi_metric_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(html)
    
    print(f"\n报告已保存: {report_path}")
    return str(report_path)


def main():
    results = run_multi_metric_evaluation()
    report_path = generate_multi_metric_report(results)
    
    import os
    os.startfile(report_path)


if __name__ == "__main__":
    main()

