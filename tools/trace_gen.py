#!/usr/bin/env python3

import argparse
import csv
import random
from datetime import datetime

def generate_trace(num_processes, num_requests, output_file):
    """Generate a synthetic I/O trace file."""
    with open(output_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['timestamp', 'process_id', 'type', 'address', 'size'])
        
        timestamp = 0
        for _ in range(num_requests):
            process_id = f"process{random.randint(1, num_processes)}"
            req_type = random.choice(['READ', 'WRITE'])
            address = random.randint(0, (1 << 40)) // 4096 * 4096  # Align to 4KB
            size = 4096  # Fixed 4KB size
            
            writer.writerow([timestamp, process_id, req_type, address, size])
            timestamp += random.randint(1, 1000)  # Random time increment

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Generate synthetic I/O traces')
    parser.add_argument('--processes', type=int, default=4, help='Number of processes')
    parser.add_argument('--requests', type=int, default=1000, help='Number of requests')
    parser.add_argument('--output', type=str, required=True, help='Output file path')
    
    args = parser.parse_args()
    generate_trace(args.processes, args.requests, args.output)