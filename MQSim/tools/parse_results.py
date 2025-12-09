#!/usr/bin/env python3
"""
Parse MQSim XML results and generate metric tables
"""

import xml.etree.ElementTree as ET
import os
import sys
import csv
import json
from pathlib import Path
from collections import defaultdict

def find_xml_files(results_dir):
    """Find all MQSim_Results*.xml files"""
    xml_files = []
    for root, dirs, files in os.walk(results_dir):
        for file in files:
            if file.startswith('MQSim_Results') and file.endswith('.xml'):
                xml_files.append(os.path.join(root, file))
    return xml_files

def parse_mqsim_xml(xml_file):
    """Parse MQSim XML result file"""
    try:
        tree = ET.parse(xml_file)
        root = tree.getroot()
        
        metrics = {}
        total_bandwidth = 0.0
        total_requests = 0
        response_times = []
        
        # Extract metrics from Host.IO_Flow elements
        for io_flow in root.findall('.//Host.IO_Flow'):
            # Bandwidth (in bytes, convert to MB/s)
            bandwidth_elem = io_flow.find('Bandwidth')
            if bandwidth_elem is not None and bandwidth_elem.text:
                try:
                    # Bandwidth is in bytes, convert to MB/s (divide by 1e6)
                    total_bandwidth += float(bandwidth_elem.text) / 1e6
                except:
                    pass
            
            # Request count
            request_count_elem = io_flow.find('Request_Count')
            if request_count_elem is not None and request_count_elem.text:
                try:
                    total_requests += int(request_count_elem.text)
                except:
                    pass
            
            # Device response time (in microseconds, convert to nanoseconds)
            response_time_elem = io_flow.find('Device_Response_Time')
            if response_time_elem is not None and response_time_elem.text:
                try:
                    # Response time is in microseconds, convert to nanoseconds
                    response_times.append(float(response_time_elem.text) * 1000.0)
                except:
                    pass
        
        if total_bandwidth > 0:
            metrics['throughput_mbps'] = total_bandwidth
        
        if total_requests > 0:
            metrics['total_requests'] = total_requests
            metrics['completed_requests'] = total_requests  # Assume all are completed
        
        if response_times:
            metrics['avg_latency_ns'] = sum(response_times) / len(response_times)
        
        return metrics
    except Exception as e:
        print(f"Error parsing {xml_file}: {e}", file=sys.stderr)
        return {}

def extract_metrics_from_log(log_file):
    """Extract metrics from log file if XML parsing fails"""
    metrics = {}
    try:
        with open(log_file, 'r') as f:
            content = f.read()
            # Look for common patterns
            import re
            # Throughput patterns
            throughput_match = re.search(r'throughput[:\s]+([\d.]+)', content, re.I)
            if throughput_match:
                metrics['throughput_mbps'] = float(throughput_match.group(1))
            
            # Latency patterns
            latency_match = re.search(r'(?:avg|average).*latency[:\s]+([\d.]+)', content, re.I)
            if latency_match:
                metrics['avg_latency_ns'] = float(latency_match.group(1))
    except:
        pass
    return metrics

def collect_all_results(results_dir):
    """Collect all results from results directory"""
    all_results = defaultdict(dict)
    
    results_path = Path(results_dir)
    
    # Check if this is a timestamp directory (contains scheduler dirs directly)
    # or a parent directory containing timestamp directories
    first_level_dirs = [d for d in results_path.iterdir() if d.is_dir()]
    
    # If first level contains what looks like scheduler names (not timestamps),
    # treat this as a timestamp directory
    if first_level_dirs and not any(d.name.startswith('20') and len(d.name) > 10 for d in first_level_dirs):
        # This is a timestamp directory, process directly
        timestamp = results_path.name
        for scheduler_dir in first_level_dirs:
            scheduler = scheduler_dir.name
            for workload_dir in scheduler_dir.iterdir():
                if not workload_dir.is_dir():
                    continue
                
                workload = workload_dir.name
                
                # Find XML files (try MQSim_Results*.xml first, then any *.xml)
                xml_files = list(workload_dir.glob('MQSim_Results*.xml'))
                if not xml_files:
                    xml_files = list(workload_dir.glob('*.xml'))
                log_file = workload_dir / 'run.log'
                
                metrics = {}
                if xml_files:
                    # Use the first XML file found
                    metrics = parse_mqsim_xml(str(xml_files[0]))
                
                if not metrics and log_file.exists():
                    metrics = extract_metrics_from_log(str(log_file))
                
                if metrics:
                    key = f"{scheduler}_{workload}"
                    all_results[key] = {
                        'scheduler': scheduler,
                        'workload': workload,
                        'timestamp': timestamp,
                        **metrics
                    }
    else:
        # This is a parent directory containing timestamp directories
        # Expected: results/TIMESTAMP/SCHEDULER/WORKLOAD/
        for timestamp_dir in first_level_dirs:
            timestamp = timestamp_dir.name
            for scheduler_dir in timestamp_dir.iterdir():
                if not scheduler_dir.is_dir():
                    continue
                
                scheduler = scheduler_dir.name
                for workload_dir in scheduler_dir.iterdir():
                    if not workload_dir.is_dir():
                        continue
                    
                    workload = workload_dir.name
                    
                    # Find XML files (try MQSim_Results*.xml first, then any *.xml)
                    xml_files = list(workload_dir.glob('MQSim_Results*.xml'))
                    if not xml_files:
                        xml_files = list(workload_dir.glob('*.xml'))
                    log_file = workload_dir / 'run.log'
                    
                    metrics = {}
                    if xml_files:
                        # Use the first XML file found
                        metrics = parse_mqsim_xml(str(xml_files[0]))
                    
                    if not metrics and log_file.exists():
                        metrics = extract_metrics_from_log(str(log_file))
                    
                    if metrics:
                        key = f"{scheduler}_{workload}"
                        all_results[key] = {
                            'scheduler': scheduler,
                            'workload': workload,
                            'timestamp': timestamp,
                            **metrics
                        }
    
    return all_results

def generate_metric_tables(all_results, output_dir):
    """Generate CSV tables for different metrics"""
    os.makedirs(output_dir, exist_ok=True)
    
    # Group by scheduler
    by_scheduler = defaultdict(list)
    for key, data in all_results.items():
        by_scheduler[data['scheduler']].append(data)
    
    # Table 1: Throughput by Scheduler
    throughput_data = []
    for scheduler, results in by_scheduler.items():
        for r in results:
            throughput_data.append({
                'Scheduler': scheduler,
                'Workload': r.get('workload', 'unknown'),
                'Throughput_MBps': r.get('throughput_mbps', 'N/A')
            })
    
    if throughput_data:
        with open(f'{output_dir}/throughput_table.csv', 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['Scheduler', 'Workload', 'Throughput_MBps'])
            writer.writeheader()
            writer.writerows(throughput_data)
    
    # Table 2: Latency by Scheduler
    latency_data = []
    for scheduler, results in by_scheduler.items():
        for r in results:
            latency_data.append({
                'Scheduler': scheduler,
                'Workload': r.get('workload', 'unknown'),
                'Avg_Latency_ns': r.get('avg_latency_ns', 'N/A')
            })
    
    if latency_data:
        with open(f'{output_dir}/latency_table.csv', 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['Scheduler', 'Workload', 'Avg_Latency_ns'])
            writer.writeheader()
            writer.writerows(latency_data)
    
    # Table 3: Request Statistics
    request_data = []
    for scheduler, results in by_scheduler.items():
        for r in results:
            request_data.append({
                'Scheduler': scheduler,
                'Workload': r.get('workload', 'unknown'),
                'Total_Requests': r.get('total_requests', 'N/A'),
                'Completed_Requests': r.get('completed_requests', 'N/A')
            })
    
    if request_data:
        with open(f'{output_dir}/requests_table.csv', 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['Scheduler', 'Workload', 'Total_Requests', 'Completed_Requests'])
            writer.writeheader()
            writer.writerows(request_data)
    
    # Table 4: Summary by Scheduler
    summary_data = []
    for scheduler, results in by_scheduler.items():
        throughputs = [r.get('throughput_mbps') for r in results if r.get('throughput_mbps')]
        latencies = [r.get('avg_latency_ns') for r in results if r.get('avg_latency_ns')]
        
        summary_data.append({
            'Scheduler': scheduler,
            'Avg_Throughput_MBps': sum(throughputs) / len(throughputs) if throughputs else 'N/A',
            'Avg_Latency_ns': sum(latencies) / len(latencies) if latencies else 'N/A',
            'Num_Workloads': len(results)
        })
    
    if summary_data:
        with open(f'{output_dir}/summary_table.csv', 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['Scheduler', 'Avg_Throughput_MBps', 'Avg_Latency_ns', 'Num_Workloads'])
            writer.writeheader()
            writer.writerows(summary_data)
    
    # Save raw JSON for reference
    with open(f'{output_dir}/all_results.json', 'w') as f:
        json.dump(all_results, f, indent=2)
    
    print(f"Generated metric tables in {output_dir}/")
    return output_dir

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 parse_results.py <results_directory> [output_directory]")
        sys.exit(1)
    
    results_dir = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else 'parsed_results'
    
    print(f"Parsing results from: {results_dir}")
    all_results = collect_all_results(results_dir)
    
    print(f"Found {len(all_results)} result sets")
    generate_metric_tables(all_results, output_dir)

if __name__ == '__main__':
    main()

