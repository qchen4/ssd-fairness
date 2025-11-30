#!/usr/bin/env python3
"""
综合测试与可视化报告生成器

功能:
1. 运行多场景测试
2. 比较算法推荐 vs 实际最佳
3. 生成 HTML 可视化报告
"""

import subprocess
import csv
import random
import math
import json
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Dict, List, Tuple
import tempfile
from datetime import datetime


@dataclass
class WorkloadProfile:
    name: str
    num_users: int
    total_requests: int
    size_ratio: float
    read_ratio: float
    rw_variance: float
    has_pure_read: bool
    has_pure_write: bool
    has_burst: bool


@dataclass 
class TestResult:
    scenario: str
    recommended: str
    actual_winner: str
    match: bool
    scores: Dict[str, float]
    fairness_values: Dict[str, float]


def run_sim(trace: str, scheduler: str, quantum: int = None) -> Dict[int, float]:
    """运行模拟器"""
    cmd = [".\\build\\Release\\ssd-fairness.exe", 
           "--trace", trace, "--scheduler", scheduler]
    if quantum and scheduler == "drr":
        cmd.extend(["--quantum", str(quantum)])
    
    subprocess.run(cmd, capture_output=True, text=True)
    
    user_latencies = {}
    if Path("results/results.csv").exists():
        with open("results/results.csv", 'r') as f:
            for row in csv.DictReader(f):
                user_latencies[int(row['user_id'])] = float(row['avg_latency_s'])
    return user_latencies


def calc_slowdown_fairness(trace: str, algo: str, quantum: int = None) -> float:
    """计算 slowdown fairness"""
    temp_dir = Path(tempfile.gettempdir()) / "ssd_report"
    temp_dir.mkdir(exist_ok=True)
    
    # Shared
    shared = run_sim(trace, algo, quantum)
    if not shared:
        return 0.0
    
    # Split trace
    user_rows = {}
    with open(trace, 'r') as f:
        for row in csv.DictReader(f):
            uid = int(row['user_id'])
            if uid not in user_rows:
                user_rows[uid] = []
            user_rows[uid].append(row)
    
    # Alone
    alone = {}
    for uid, rows in user_rows.items():
        trace_out = temp_dir / f"u{uid}.csv"
        with open(trace_out, 'w', newline='') as f:
            w = csv.DictWriter(f, ["timestamp", "process_id", "user_id", "type", "address", "size"])
            w.writeheader()
            for r in rows:
                r2 = dict(r)
                r2['user_id'] = 0
                w.writerow(r2)
        lat = run_sim(str(trace_out), algo, quantum)
        alone[uid] = lat.get(0, 0.0001)
    
    # Slowdowns
    slowdowns = {}
    for uid in shared:
        if alone.get(uid, 0) > 0:
            slowdowns[uid] = shared[uid] / alone[uid]
        else:
            slowdowns[uid] = 1.0
    
    if len(slowdowns) < 2:
        return 1.0
    
    return min(slowdowns.values()) / max(slowdowns.values())


def get_recommendation(trace: str) -> str:
    """获取自动推荐"""
    result = subprocess.run(
        [".\\build\\Release\\ssd-fairness.exe", "--trace", trace, "--scheduler", "auto"],
        capture_output=True, text=True
    )
    for line in result.stdout.split('\n'):
        if "Selected algorithm:" in line:
            return line.split(':')[1].strip()
    return "rr"


def analyze_trace(trace: str) -> WorkloadProfile:
    """分析 trace 特征"""
    users = {}
    sizes = []
    timestamps = {}
    
    with open(trace, 'r') as f:
        for row in csv.DictReader(f):
            uid = int(row['user_id'])
            size = int(row['size'])
            ts = int(row['timestamp'])
            is_read = row['type'].upper() == 'READ'
            
            sizes.append(size)
            if uid not in users:
                users[uid] = {'reads': 0, 'writes': 0}
            if is_read:
                users[uid]['reads'] += 1
            else:
                users[uid]['writes'] += 1
            timestamps[ts] = timestamps.get(ts, 0) + 1
    
    # Calculate metrics
    size_ratio = max(sizes) / min(sizes) if min(sizes) > 0 else 1.0
    
    total_reads = sum(u['reads'] for u in users.values())
    total_writes = sum(u['writes'] for u in users.values())
    read_ratio = total_reads / (total_reads + total_writes) if (total_reads + total_writes) > 0 else 0.5
    
    # Per-user read ratios
    ratios = []
    has_pure_read = False
    has_pure_write = False
    for u in users.values():
        total = u['reads'] + u['writes']
        r = u['reads'] / total if total > 0 else 0.5
        ratios.append(r)
        if r > 0.95: has_pure_read = True
        if r < 0.05: has_pure_write = True
    
    avg_ratio = sum(ratios) / len(ratios)
    rw_variance = sum((r - avg_ratio)**2 for r in ratios) / len(ratios)
    
    max_concurrent = max(timestamps.values()) if timestamps else 0
    has_burst = max_concurrent > len(users) * 2
    
    return WorkloadProfile(
        name=Path(trace).stem,
        num_users=len(users),
        total_requests=len(sizes),
        size_ratio=size_ratio,
        read_ratio=read_ratio,
        rw_variance=rw_variance,
        has_pure_read=has_pure_read,
        has_pure_write=has_pure_write,
        has_burst=has_burst
    )


def run_tests() -> List[TestResult]:
    """运行所有测试"""
    results = []
    
    # Find all test traces
    traces = list(Path("traces/competition").glob("*.csv"))
    traces.extend(Path("traces/contention").glob("*.csv"))
    traces.extend(Path("traces/validation").glob("*.csv"))
    
    print(f"找到 {len(traces)} 个测试场景")
    
    for trace in sorted(traces)[:25]:  # Test more traces
        print(f"\n测试: {trace.stem}")
        
        # Get recommendation
        recommended = get_recommendation(str(trace))
        print(f"  推荐: {recommended}")
        
        # Calculate sqrt quantum
        with open(trace) as f:
            sizes = [int(r['size']) for r in csv.DictReader(f)]
        quantum = int(math.sqrt(min(sizes) * max(sizes)))
        
        # Test all algorithms
        fairness = {}
        for algo in ["rr", "drr", "qfq", "flin"]:
            q = quantum if algo == "drr" else None
            F = calc_slowdown_fairness(str(trace), algo, q)
            fairness[algo] = F
            print(f"  {algo.upper()}: F={F:.4f}")
        
        # Find actual winner
        actual_winner = max(fairness.keys(), key=lambda k: fairness[k])
        
        # Check for ties
        best_F = fairness[actual_winner]
        winners = [a for a, f in fairness.items() if abs(f - best_F) < 0.001]
        
        match = recommended in winners
        
        results.append(TestResult(
            scenario=trace.stem,
            recommended=recommended,
            actual_winner="/".join(winners),
            match=match,
            scores={},
            fairness_values=fairness
        ))
        
        print(f"  实际胜者: {'/'.join(winners)} | {'OK' if match else 'MISS'}")
    
    return results


def generate_html_report(results: List[TestResult], profiles: Dict[str, WorkloadProfile]):
    """生成 HTML 报告"""
    
    # Calculate statistics
    total = len(results)
    matches = sum(1 for r in results if r.match)
    accuracy = matches / total * 100 if total > 0 else 0
    
    # Count wins per algorithm
    wins = {"rr": 0, "drr": 0, "qfq": 0, "flin": 0}
    recommendations = {"rr": 0, "drr": 0, "qfq": 0, "flin": 0}
    
    for r in results:
        recommendations[r.recommended] = recommendations.get(r.recommended, 0) + 1
        for algo in r.actual_winner.split('/'):
            if algo in wins:
                wins[algo] += 1
    
    # Prepare chart data
    scenarios = [r.scenario for r in results]
    rr_data = [r.fairness_values.get('rr', 0) for r in results]
    drr_data = [r.fairness_values.get('drr', 0) for r in results]
    qfq_data = [r.fairness_values.get('qfq', 0) for r in results]
    flin_data = [r.fairness_values.get('flin', 0) for r in results]
    
    html = f'''<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <title>SSD 调度算法测试报告</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body {{
            font-family: 'Segoe UI', Arial, sans-serif;
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #eee;
            min-height: 100vh;
        }}
        h1 {{
            text-align: center;
            color: #00d9ff;
            text-shadow: 0 0 20px rgba(0, 217, 255, 0.5);
            font-size: 2.5em;
            margin-bottom: 10px;
        }}
        .subtitle {{
            text-align: center;
            color: #888;
            margin-bottom: 30px;
        }}
        .summary {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 20px;
            margin-bottom: 30px;
        }}
        .card {{
            background: rgba(255,255,255,0.05);
            border-radius: 15px;
            padding: 20px;
            text-align: center;
            border: 1px solid rgba(255,255,255,0.1);
            backdrop-filter: blur(10px);
        }}
        .card h3 {{
            margin: 0;
            font-size: 2.5em;
            background: linear-gradient(45deg, #00d9ff, #00ff88);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        .card p {{
            margin: 10px 0 0;
            color: #aaa;
        }}
        .chart-container {{
            background: rgba(255,255,255,0.05);
            border-radius: 15px;
            padding: 20px;
            margin-bottom: 30px;
            border: 1px solid rgba(255,255,255,0.1);
        }}
        .chart-row {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            background: rgba(255,255,255,0.05);
            border-radius: 15px;
            overflow: hidden;
        }}
        th, td {{
            padding: 12px 15px;
            text-align: left;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }}
        th {{
            background: rgba(0, 217, 255, 0.2);
            color: #00d9ff;
        }}
        tr:hover {{
            background: rgba(255,255,255,0.05);
        }}
        .match {{ color: #00ff88; }}
        .miss {{ color: #ff6b6b; }}
        .algo-rr {{ color: #ff6b6b; }}
        .algo-drr {{ color: #4ecdc4; }}
        .algo-qfq {{ color: #ffe66d; }}
        .algo-flin {{ color: #95e1d3; }}
    </style>
</head>
<body>
    <h1>🚀 SSD 调度算法测试报告</h1>
    <p class="subtitle">生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} | 测试场景: {total}</p>
    
    <div class="summary">
        <div class="card">
            <h3>{accuracy:.1f}%</h3>
            <p>推荐准确率</p>
        </div>
        <div class="card">
            <h3>{matches}/{total}</h3>
            <p>匹配场景数</p>
        </div>
        <div class="card">
            <h3>{max(wins.keys(), key=lambda k: wins[k]).upper()}</h3>
            <p>最多胜出算法</p>
        </div>
        <div class="card">
            <h3>{max(recommendations.keys(), key=lambda k: recommendations[k]).upper()}</h3>
            <p>最多推荐算法</p>
        </div>
    </div>
    
    <div class="chart-row">
        <div class="chart-container">
            <h2>📊 Slowdown Fairness 对比</h2>
            <canvas id="fairnessChart"></canvas>
        </div>
        <div class="chart-container">
            <h2>🏆 算法胜出统计</h2>
            <canvas id="winsChart"></canvas>
        </div>
    </div>
    
    <div class="chart-container">
        <h2>📋 详细测试结果</h2>
        <table>
            <tr>
                <th>场景</th>
                <th>特征</th>
                <th>推荐</th>
                <th>实际胜者</th>
                <th>RR</th>
                <th>DRR</th>
                <th>QFQ</th>
                <th>FLIN</th>
                <th>匹配</th>
            </tr>
'''
    
    for r in results:
        profile = profiles.get(r.scenario)
        if profile:
            features = f"Size:{profile.size_ratio:.0f}x, RW:{profile.rw_variance:.2f}"
        else:
            features = "-"
        
        match_class = "match" if r.match else "miss"
        match_icon = "✓" if r.match else "✗"
        
        html += f'''            <tr>
                <td>{r.scenario}</td>
                <td>{features}</td>
                <td class="algo-{r.recommended}">{r.recommended.upper()}</td>
                <td>{r.actual_winner.upper()}</td>
                <td>{r.fairness_values.get('rr', 0):.4f}</td>
                <td>{r.fairness_values.get('drr', 0):.4f}</td>
                <td>{r.fairness_values.get('qfq', 0):.4f}</td>
                <td>{r.fairness_values.get('flin', 0):.4f}</td>
                <td class="{match_class}">{match_icon}</td>
            </tr>
'''
    
    html += f'''        </table>
    </div>
    
    <div class="chart-container">
        <h2>📖 选择规则说明</h2>
        <table>
            <tr><th>条件</th><th>RR</th><th>DRR</th><th>QFQ</th><th>FLIN</th></tr>
            <tr><td>size_ratio > 16</td><td>-</td><td>+3.0</td><td>+2.5</td><td>-</td></tr>
            <tr><td>size_ratio > 4</td><td>-</td><td>+2.0</td><td>+1.5</td><td>-</td></tr>
            <tr><td>size_ratio ≤ 4</td><td>+1.0</td><td>-</td><td>-</td><td>-</td></tr>
            <tr><td>rw_variance > 0.1</td><td>-</td><td>-</td><td>-</td><td>+3.0</td></tr>
            <tr><td>纯读+纯写用户</td><td>-</td><td>-</td><td>-</td><td>+2.0</td></tr>
            <tr><td>指定权重</td><td>-</td><td>-</td><td>+5.0</td><td>-</td></tr>
            <tr><td>突发+差异>2x</td><td>-</td><td>-</td><td>+2.0</td><td>-</td></tr>
            <tr><td>多用户(>4)+差异>4x</td><td>-</td><td>-</td><td>+1.5</td><td>-</td></tr>
        </table>
    </div>
    
    <script>
        // Fairness comparison chart
        new Chart(document.getElementById('fairnessChart'), {{
            type: 'bar',
            data: {{
                labels: {json.dumps(scenarios[:10])},
                datasets: [
                    {{ label: 'RR', data: {json.dumps(rr_data[:10])}, backgroundColor: 'rgba(255, 107, 107, 0.7)' }},
                    {{ label: 'DRR', data: {json.dumps(drr_data[:10])}, backgroundColor: 'rgba(78, 205, 196, 0.7)' }},
                    {{ label: 'QFQ', data: {json.dumps(qfq_data[:10])}, backgroundColor: 'rgba(255, 230, 109, 0.7)' }},
                    {{ label: 'FLIN', data: {json.dumps(flin_data[:10])}, backgroundColor: 'rgba(149, 225, 211, 0.7)' }}
                ]
            }},
            options: {{
                responsive: true,
                plugins: {{ legend: {{ labels: {{ color: '#eee' }} }} }},
                scales: {{
                    x: {{ ticks: {{ color: '#aaa' }}, grid: {{ color: 'rgba(255,255,255,0.1)' }} }},
                    y: {{ ticks: {{ color: '#aaa' }}, grid: {{ color: 'rgba(255,255,255,0.1)' }}, max: 1.1 }}
                }}
            }}
        }});
        
        // Wins pie chart
        new Chart(document.getElementById('winsChart'), {{
            type: 'doughnut',
            data: {{
                labels: ['RR', 'DRR', 'QFQ', 'FLIN'],
                datasets: [{{
                    data: [{wins['rr']}, {wins['drr']}, {wins['qfq']}, {wins['flin']}],
                    backgroundColor: ['#ff6b6b', '#4ecdc4', '#ffe66d', '#95e1d3']
                }}]
            }},
            options: {{
                responsive: true,
                plugins: {{ legend: {{ labels: {{ color: '#eee' }} }} }}
            }}
        }});
    </script>
</body>
</html>
'''
    
    # Save report
    report_path = Path("reports")
    report_path.mkdir(exist_ok=True)
    output_file = report_path / f"algorithm_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html)
    
    print(f"\n报告已保存: {output_file}")
    return str(output_file)


def main():
    print("=" * 70)
    print("     SSD 调度算法综合测试与可视化报告")
    print("=" * 70)
    
    # Run tests
    print("\n[1/3] 运行多场景测试...")
    results = run_tests()
    
    # Analyze traces
    print("\n[2/3] 分析工作负载特征...")
    profiles = {}
    for trace in Path("traces/competition").glob("*.csv"):
        profiles[trace.stem] = analyze_trace(str(trace))
    for trace in Path("traces/contention").glob("*.csv"):
        profiles[trace.stem] = analyze_trace(str(trace))
    for trace in Path("traces/validation").glob("*.csv"):
        profiles[trace.stem] = analyze_trace(str(trace))
    
    # Generate report
    print("\n[3/3] 生成可视化报告...")
    report_path = generate_html_report(results, profiles)
    
    # Summary
    matches = sum(1 for r in results if r.match)
    print("\n" + "=" * 70)
    print("                    测试总结")
    print("=" * 70)
    print(f"  测试场景: {len(results)}")
    print(f"  推荐匹配: {matches}/{len(results)} ({matches/len(results)*100:.1f}%)")
    print(f"  报告路径: {report_path}")
    print("=" * 70)
    
    # Try to open report
    import os
    os.startfile(report_path)


if __name__ == "__main__":
    main()

