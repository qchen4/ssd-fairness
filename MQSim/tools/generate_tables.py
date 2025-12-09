#!/usr/bin/env python3
"""
Generate metric tables from MQSim results (simplified version)
Creates tables even if XML parsing is incomplete
"""

import os
import csv
import json
from pathlib import Path
from collections import defaultdict
import re

def extract_metrics_from_log(log_file):
    """Extract metrics from log file"""
    metrics = {}
    try:
        with open(log_file, 'r') as f:
            content = f.read()
            
            # Look for throughput patterns
            throughput_patterns = [
                r'throughput[:\s]+([\d.]+)\s*(?:MB|GB)',
                r'([\d.]+)\s*(?:MB|GB)/s',
            ]
            for pattern in throughput_patterns:
                match = re.search(pattern, content, re.I)
                if match:
                    metrics['throughput_mbps'] = float(match.group(1))
                    break
            
            # Look for latency patterns (response time)
            latency_patterns = [
                r'device response time[:\s]+([\d.]+)\s*\(us\)',
                r'response time[:\s]+([\d.]+)',
                r'(?:avg|average).*latency[:\s]+([\d.]+)',
                r'latency[:\s]+([\d.]+)\s*(?:ns|us|ms)',
            ]
            for pattern in latency_patterns:
                match = re.search(pattern, content, re.I)
                if match:
                    latency_us = float(match.group(1))
                    metrics['avg_latency_ns'] = latency_us * 1000  # Convert to ns
                    break
            
            # Look for request counts
            request_patterns = [
                r'total requests generated[:\s]+(\d+).*total requests serviced[:\s]+(\d+)',
                r'(\d+)\s*total requests generated.*(\d+)\s*total requests serviced',
                r'(\d+)\s*(?:total|completed).*request',
            ]
            for pattern in request_patterns:
                matches = re.findall(pattern, content, re.I)
                if matches:
                    try:
                        if isinstance(matches[0], tuple):
                            metrics['total_requests'] = int(matches[0][0])
                            metrics['completed_requests'] = int(matches[0][1])
                        else:
                            metrics['total_requests'] = int(matches[0])
                            if len(matches) > 1:
                                metrics['completed_requests'] = int(matches[1])
                    except:
                        pass
                    break
    except Exception as e:
        print(f"Error reading {log_file}: {e}")
    
    return metrics

def collect_results(results_dir):
    """Collect all results"""
    all_results = []
    
    for scheduler_dir in Path(results_dir).iterdir():
        if not scheduler_dir.is_dir():
            continue
        
        scheduler = scheduler_dir.name
        
        for workload_dir in scheduler_dir.iterdir():
            if not workload_dir.is_dir():
                continue
            
            workload = workload_dir.name
            log_file = workload_dir / 'run.log'
            
            metrics = {}
            if log_file.exists():
                metrics = extract_metrics_from_log(str(log_file))
            
            # If no metrics from log, create placeholder
            if not metrics:
                metrics = {
                    'throughput_mbps': 'N/A',
                    'avg_latency_ns': 'N/A',
                    'total_requests': 'N/A',
                    'completed_requests': 'N/A'
                }
            
            all_results.append({
                'scheduler': scheduler,
                'workload': workload,
                **metrics
            })
    
    return all_results

def generate_tables(all_results, output_dir):
    """Generate CSV tables"""
    os.makedirs(output_dir, exist_ok=True)
    
    # Table 1: Throughput
    with open(f'{output_dir}/throughput_table.csv', 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['Scheduler', 'Workload', 'Throughput_MBps'])
        writer.writeheader()
        for r in all_results:
            writer.writerow({
                'Scheduler': r['scheduler'],
                'Workload': r['workload'],
                'Throughput_MBps': r.get('throughput_mbps', 'N/A')
            })
    
    # Table 2: Latency
    with open(f'{output_dir}/latency_table.csv', 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['Scheduler', 'Workload', 'Avg_Latency_ns'])
        writer.writeheader()
        for r in all_results:
            writer.writerow({
                'Scheduler': r['scheduler'],
                'Workload': r['workload'],
                'Avg_Latency_ns': r.get('avg_latency_ns', 'N/A')
            })
    
    # Table 3: Summary
    by_scheduler = defaultdict(list)
    for r in all_results:
        by_scheduler[r['scheduler']].append(r)
    
    summary_data = []
    for scheduler, results in by_scheduler.items():
        throughputs = [r.get('throughput_mbps') for r in results 
                      if isinstance(r.get('throughput_mbps'), (int, float))]
        latencies = [r.get('avg_latency_ns') for r in results 
                    if isinstance(r.get('avg_latency_ns'), (int, float))]
        
        summary_data.append({
            'Scheduler': scheduler,
            'Avg_Throughput_MBps': sum(throughputs) / len(throughputs) if throughputs else 'N/A',
            'Avg_Latency_ns': sum(latencies) / len(latencies) if latencies else 'N/A',
            'Num_Workloads': len(results)
        })
    
    with open(f'{output_dir}/summary_table.csv', 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['Scheduler', 'Avg_Throughput_MBps', 'Avg_Latency_ns', 'Num_Workloads'])
        writer.writeheader()
        writer.writerows(summary_data)
    
    # Save JSON
    with open(f'{output_dir}/all_results.json', 'w') as f:
        json.dump(all_results, f, indent=2)
    
    print(f"Generated tables in {output_dir}/")
    return output_dir

def main():
    import sys
    if len(sys.argv) < 2:
        print("Usage: python3 generate_tables.py <results_directory> [output_directory]")
        sys.exit(1)
    
    results_dir = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else 'parsed_results'
    
    print(f"Collecting results from: {results_dir}")
    all_results = collect_results(results_dir)
    print(f"Found {len(all_results)} result sets")
    
    generate_tables(all_results, output_dir)

if __name__ == '__main__':
    main()

