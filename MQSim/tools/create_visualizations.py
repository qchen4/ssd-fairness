#!/usr/bin/env python3
"""
Create visualizations from parsed MQSim results
"""

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import sys
import os
from pathlib import Path

# Set style
sns.set_style("whitegrid")
plt.rcParams['figure.figsize'] = (12, 6)

def load_data(csv_dir):
    """Load CSV tables"""
    data = {}
    for csv_file in Path(csv_dir).glob('*.csv'):
        name = csv_file.stem
        try:
            data[name] = pd.read_csv(csv_file)
        except Exception as e:
            print(f"Warning: Could not load {csv_file}: {e}")
    return data

def plot_throughput_comparison(data, output_dir):
    """Create throughput comparison chart"""
    if 'throughput_table' not in data:
        print("No throughput data available")
        return
    
    df = data['throughput_table']
    df = df[df['Throughput_MBps'] != 'N/A']
    df['Throughput_MBps'] = pd.to_numeric(df['Throughput_MBps'], errors='coerce')
    df = df.dropna()
    
    if df.empty:
        print("No valid throughput data")
        return
    
    plt.figure(figsize=(12, 6))
    df_pivot = df.pivot(index='Workload', columns='Scheduler', values='Throughput_MBps')
    df_pivot.plot(kind='bar', ax=plt.gca())
    plt.title('Throughput Comparison by Scheduler', fontsize=14, fontweight='bold')
    plt.xlabel('Workload', fontsize=12)
    plt.ylabel('Throughput (MB/s)', fontsize=12)
    plt.legend(title='Scheduler', bbox_to_anchor=(1.05, 1), loc='upper left')
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    plt.savefig(f'{output_dir}/throughput_comparison.png', dpi=300, bbox_inches='tight')
    plt.close()
    print(f"Created: {output_dir}/throughput_comparison.png")

def plot_latency_comparison(data, output_dir):
    """Create latency comparison chart"""
    if 'latency_table' not in data:
        print("No latency data available")
        return
    
    df = data['latency_table']
    df = df[df['Avg_Latency_ns'] != 'N/A']
    df['Avg_Latency_ns'] = pd.to_numeric(df['Avg_Latency_ns'], errors='coerce')
    df = df.dropna()
    
    if df.empty:
        print("No valid latency data")
        return
    
    # Convert to microseconds for readability
    df['Avg_Latency_us'] = df['Avg_Latency_ns'] / 1000.0
    
    plt.figure(figsize=(12, 6))
    df_pivot = df.pivot(index='Workload', columns='Scheduler', values='Avg_Latency_us')
    df_pivot.plot(kind='bar', ax=plt.gca())
    plt.title('Average Latency Comparison by Scheduler', fontsize=14, fontweight='bold')
    plt.xlabel('Workload', fontsize=12)
    plt.ylabel('Average Latency (μs)', fontsize=12)
    plt.legend(title='Scheduler', bbox_to_anchor=(1.05, 1), loc='upper left')
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    plt.savefig(f'{output_dir}/latency_comparison.png', dpi=300, bbox_inches='tight')
    plt.close()
    print(f"Created: {output_dir}/latency_comparison.png")

def plot_summary_metrics(data, output_dir):
    """Create summary metrics chart"""
    if 'summary_table' not in data:
        print("No summary data available")
        return
    
    df = data['summary_table']
    
    # Throughput
    if 'Avg_Throughput_MBps' in df.columns:
        df['Avg_Throughput_MBps'] = pd.to_numeric(df['Avg_Throughput_MBps'], errors='coerce')
        df_throughput = df.dropna(subset=['Avg_Throughput_MBps'])
        
        if not df_throughput.empty:
            fig, ax = plt.subplots(figsize=(10, 6))
            df_throughput.plot(x='Scheduler', y='Avg_Throughput_MBps', kind='bar', ax=ax, color='steelblue')
            plt.title('Average Throughput by Scheduler', fontsize=14, fontweight='bold')
            plt.xlabel('Scheduler', fontsize=12)
            plt.ylabel('Average Throughput (MB/s)', fontsize=12)
            plt.xticks(rotation=45, ha='right')
            plt.tight_layout()
            plt.savefig(f'{output_dir}/summary_throughput.png', dpi=300, bbox_inches='tight')
            plt.close()
            print(f"Created: {output_dir}/summary_throughput.png")
    
    # Latency
    if 'Avg_Latency_ns' in df.columns:
        df['Avg_Latency_ns'] = pd.to_numeric(df['Avg_Latency_ns'], errors='coerce')
        df_latency = df.dropna(subset=['Avg_Latency_ns'])
        
        if not df_latency.empty:
            df_latency['Avg_Latency_us'] = df_latency['Avg_Latency_ns'] / 1000.0
            fig, ax = plt.subplots(figsize=(10, 6))
            df_latency.plot(x='Scheduler', y='Avg_Latency_us', kind='bar', ax=ax, color='coral')
            plt.title('Average Latency by Scheduler', fontsize=14, fontweight='bold')
            plt.xlabel('Scheduler', fontsize=12)
            plt.ylabel('Average Latency (μs)', fontsize=12)
            plt.xticks(rotation=45, ha='right')
            plt.tight_layout()
            plt.savefig(f'{output_dir}/summary_latency.png', dpi=300, bbox_inches='tight')
            plt.close()
            print(f"Created: {output_dir}/summary_latency.png")

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 create_visualizations.py <parsed_results_directory> [output_directory]")
        sys.exit(1)
    
    csv_dir = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else 'visualizations'
    
    os.makedirs(output_dir, exist_ok=True)
    
    print(f"Loading data from: {csv_dir}")
    data = load_data(csv_dir)
    
    if not data:
        print("No data files found!")
        sys.exit(1)
    
    print(f"Loaded {len(data)} data tables")
    
    print("\nCreating visualizations...")
    plot_throughput_comparison(data, output_dir)
    plot_latency_comparison(data, output_dir)
    plot_summary_metrics(data, output_dir)
    
    print(f"\nVisualizations saved to: {output_dir}/")

if __name__ == '__main__':
    main()

