#!/usr/bin/env python3
"""
Analyze fairness metrics from MQSim results
Calculates Jain's fairness index, per-flow throughput, and fairness ratios
"""

import re
import csv
import json
import os
import sys
from pathlib import Path
from collections import defaultdict
import math

def jains_fairness_index(values):
    """Calculate Jain's fairness index"""
    if not values or len(values) == 0:
        return 0.0
    values = [float(v) for v in values if v and v != 'N/A']
    if not values:
        return 0.0
    numerator = sum(values) ** 2
    denominator = len(values) * sum(v ** 2 for v in values)
    if denominator == 0:
        return 0.0
    return numerator / denominator

def extract_flow_metrics(log_file):
    """Extract per-flow metrics from log file"""
    flows = []
    try:
        with open(log_file, 'r') as f:
            content = f.read()
            
            # Pattern: Flow Host.IO_Flow.Synth.No_X - total requests generated: Y total requests serviced:Z
            #          - device response time: T (us) end-to-end request delay:D (us)
            flow_pattern = r'Flow\s+Host\.IO_Flow\.Synth\.No_(\d+)\s+-\s+total requests generated:\s+(\d+)\s+total requests serviced:(\d+).*?device response time:\s+([\d.]+)\s*\(us\)'
            
            matches = re.findall(flow_pattern, content, re.DOTALL)
            
            for match in matches:
                flow_id = int(match[0])
                generated = int(match[1])
                serviced = int(match[2])
                response_time_us = float(match[3])
                
                flows.append({
                    'flow_id': flow_id,
                    'requests_generated': generated,
                    'requests_serviced': serviced,
                    'response_time_us': response_time_us,
                    'completion_rate': serviced / generated if generated > 0 else 0.0
                })
    except Exception as e:
        print(f"Error reading {log_file}: {e}", file=sys.stderr)
    
    return flows

def calculate_fairness_metrics(flows):
    """Calculate fairness metrics from flow data"""
    if not flows or len(flows) < 2:
        return {}
    
    # Per-flow request counts
    request_counts = [f['requests_serviced'] for f in flows]
    response_times = [f['response_time_us'] for f in flows]
    completion_rates = [f['completion_rate'] for f in flows]
    
    # Jain's fairness index for requests
    jain_requests = jains_fairness_index(request_counts)
    
    # Jain's fairness index for response time (inverse - lower is better, so we invert)
    # For fairness, we want similar response times, so we use inverse response times
    inv_response_times = [1.0 / rt if rt > 0 else 0 for rt in response_times]
    jain_response_time = jains_fairness_index(inv_response_times)
    
    # Request distribution fairness
    total_requests = sum(request_counts)
    if total_requests > 0:
        flow_ratios = [rc / total_requests for rc in request_counts]
        jain_distribution = jains_fairness_index(flow_ratios)
    else:
        jain_distribution = 0.0
    
    # Min/Max ratios (fairness ratio)
    if request_counts:
        min_requests = min(request_counts)
        max_requests = max(request_counts)
        fairness_ratio = min_requests / max_requests if max_requests > 0 else 0.0
    else:
        fairness_ratio = 0.0
    
    # Coefficient of variation (lower is more fair)
    if request_counts and len(request_counts) > 1:
        mean_requests = sum(request_counts) / len(request_counts)
        variance = sum((x - mean_requests) ** 2 for x in request_counts) / len(request_counts)
        std_dev = math.sqrt(variance)
        cv = std_dev / mean_requests if mean_requests > 0 else 0.0
    else:
        cv = 0.0
    
    return {
        'jain_fairness_index': jain_requests,
        'jain_response_time_fairness': jain_response_time,
        'jain_distribution_fairness': jain_distribution,
        'fairness_ratio': fairness_ratio,
        'coefficient_of_variation': cv,
        'min_requests': min(request_counts) if request_counts else 0,
        'max_requests': max(request_counts) if request_counts else 0,
        'num_flows': len(flows),
        'per_flow_requests': request_counts,
        'per_flow_response_times': response_times
    }

def collect_fairness_results(results_dir):
    """Collect fairness metrics from all results"""
    all_fairness = []
    
    for scheduler_dir in Path(results_dir).iterdir():
        if not scheduler_dir.is_dir():
            continue
        
        scheduler = scheduler_dir.name
        
        for workload_dir in scheduler_dir.iterdir():
            if not workload_dir.is_dir():
                continue
            
            workload = workload_dir.name
            log_file = workload_dir / 'run.log'
            
            if not log_file.exists():
                continue
            
            flows = extract_flow_metrics(str(log_file))
            if flows:
                fairness_metrics = calculate_fairness_metrics(flows)
                fairness_metrics['scheduler'] = scheduler
                fairness_metrics['workload'] = workload
                fairness_metrics['flows'] = flows
                all_fairness.append(fairness_metrics)
    
    return all_fairness

def generate_fairness_tables(all_fairness, output_dir):
    """Generate fairness metric tables"""
    os.makedirs(output_dir, exist_ok=True)
    
    # Table 1: Jain's Fairness Index by Scheduler
    with open(f'{output_dir}/jain_fairness_table.csv', 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['Scheduler', 'Workload', 'Jain_Fairness_Index', 'Fairness_Ratio', 'Coefficient_of_Variation'])
        writer.writeheader()
        for result in all_fairness:
            writer.writerow({
                'Scheduler': result['scheduler'],
                'Workload': result['workload'],
                'Jain_Fairness_Index': f"{result['jain_fairness_index']:.4f}",
                'Fairness_Ratio': f"{result['fairness_ratio']:.4f}",
                'Coefficient_of_Variation': f"{result['coefficient_of_variation']:.4f}"
            })
    
    # Table 2: Per-Flow Request Distribution
    with open(f'{output_dir}/per_flow_distribution.csv', 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['Scheduler', 'Workload', 'Flow_ID', 'Requests_Serviced', 'Response_Time_us', 'Completion_Rate'])
        writer.writeheader()
        for result in all_fairness:
            for flow in result['flows']:
                writer.writerow({
                    'Scheduler': result['scheduler'],
                    'Workload': result['workload'],
                    'Flow_ID': flow['flow_id'],
                    'Requests_Serviced': flow['requests_serviced'],
                    'Response_Time_us': f"{flow['response_time_us']:.2f}",
                    'Completion_Rate': f"{flow['completion_rate']:.4f}"
                })
    
    # Table 3: Fairness Summary by Scheduler
    by_scheduler = defaultdict(list)
    for result in all_fairness:
        by_scheduler[result['scheduler']].append(result)
    
    summary_data = []
    for scheduler, results in by_scheduler.items():
        jain_indices = [r['jain_fairness_index'] for r in results]
        fairness_ratios = [r['fairness_ratio'] for r in results]
        cvs = [r['coefficient_of_variation'] for r in results]
        
        summary_data.append({
            'Scheduler': scheduler,
            'Avg_Jain_Fairness_Index': sum(jain_indices) / len(jain_indices) if jain_indices else 0.0,
            'Avg_Fairness_Ratio': sum(fairness_ratios) / len(fairness_ratios) if fairness_ratios else 0.0,
            'Avg_Coefficient_of_Variation': sum(cvs) / len(cvs) if cvs else 0.0,
            'Num_Workloads': len(results)
        })
    
    with open(f'{output_dir}/fairness_summary.csv', 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['Scheduler', 'Avg_Jain_Fairness_Index', 'Avg_Fairness_Ratio', 'Avg_Coefficient_of_Variation', 'Num_Workloads'])
        writer.writeheader()
        for row in summary_data:
            writer.writerow({
                'Scheduler': row['Scheduler'],
                'Avg_Jain_Fairness_Index': f"{row['Avg_Jain_Fairness_Index']:.4f}",
                'Avg_Fairness_Ratio': f"{row['Avg_Fairness_Ratio']:.4f}",
                'Avg_Coefficient_of_Variation': f"{row['Avg_Coefficient_of_Variation']:.4f}",
                'Num_Workloads': row['Num_Workloads']
            })
    
    # Save JSON
    with open(f'{output_dir}/fairness_results.json', 'w') as f:
        json.dump(all_fairness, f, indent=2)
    
    print(f"Generated fairness tables in {output_dir}/")
    return output_dir

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 analyze_fairness.py <results_directory> [output_directory]")
        sys.exit(1)
    
    results_dir = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else 'fairness_results'
    
    print(f"Analyzing fairness from: {results_dir}")
    all_fairness = collect_fairness_results(results_dir)
    
    print(f"Found {len(all_fairness)} result sets with flow data")
    generate_fairness_tables(all_fairness, output_dir)

if __name__ == '__main__':
    main()

