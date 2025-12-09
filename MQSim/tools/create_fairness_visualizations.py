#!/usr/bin/env python3
"""
Create fairness visualizations from fairness analysis results
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

def load_fairness_data(csv_dir):
    """Load fairness CSV tables"""
    data = {}
    for csv_file in Path(csv_dir).glob('*.csv'):
        name = csv_file.stem
        try:
            data[name] = pd.read_csv(csv_file)
        except Exception as e:
            print(f"Warning: Could not load {csv_file}: {e}")
    return data

def plot_jain_fairness_comparison(data, output_dir):
    """Create Jain's fairness index comparison chart"""
    if 'jain_fairness_table' not in data:
        print("No Jain fairness data available")
        return
    
    df = data['jain_fairness_table']
    df['Jain_Fairness_Index'] = pd.to_numeric(df['Jain_Fairness_Index'], errors='coerce')
    df = df.dropna(subset=['Jain_Fairness_Index'])
    
    if df.empty:
        print("No valid Jain fairness data")
        return
    
    plt.figure(figsize=(14, 7))
    df_pivot = df.pivot(index='Workload', columns='Scheduler', values='Jain_Fairness_Index')
    df_pivot.plot(kind='bar', ax=plt.gca(), width=0.8)
    plt.title("Jain's Fairness Index Comparison by Scheduler", fontsize=16, fontweight='bold')
    plt.xlabel('Workload', fontsize=12)
    plt.ylabel("Jain's Fairness Index", fontsize=12)
    plt.axhline(y=1.0, color='green', linestyle='--', alpha=0.5, label='Perfect Fairness (1.0)')
    plt.legend(title='Scheduler', bbox_to_anchor=(1.05, 1), loc='upper left', fontsize=10)
    plt.xticks(rotation=45, ha='right')
    plt.ylim(0, 1.1)
    plt.grid(axis='y', alpha=0.3)
    plt.tight_layout()
    plt.savefig(f'{output_dir}/jain_fairness_comparison.png', dpi=300, bbox_inches='tight')
    plt.close()
    print(f"Created: {output_dir}/jain_fairness_comparison.png")

def plot_fairness_summary(data, output_dir):
    """Create fairness summary chart"""
    if 'fairness_summary' not in data:
        print("No fairness summary data available")
        return
    
    df = data['fairness_summary']
    df['Avg_Jain_Fairness_Index'] = pd.to_numeric(df['Avg_Jain_Fairness_Index'], errors='coerce')
    df['Avg_Fairness_Ratio'] = pd.to_numeric(df['Avg_Fairness_Ratio'], errors='coerce')
    df = df.dropna(subset=['Avg_Jain_Fairness_Index'])
    
    if df.empty:
        print("No valid fairness summary data")
        return
    
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
    
    # Jain's Index
    df_sorted = df.sort_values('Avg_Jain_Fairness_Index', ascending=False)
    bars1 = ax1.barh(df_sorted['Scheduler'], df_sorted['Avg_Jain_Fairness_Index'], color='steelblue')
    ax1.axvline(x=1.0, color='green', linestyle='--', alpha=0.5, label='Perfect Fairness')
    ax1.set_xlabel("Average Jain's Fairness Index", fontsize=12)
    ax1.set_title("Average Jain's Fairness Index by Scheduler", fontsize=14, fontweight='bold')
    ax1.set_xlim(0, 1.1)
    ax1.grid(axis='x', alpha=0.3)
    ax1.legend()
    
    # Add value labels
    for i, (idx, row) in enumerate(df_sorted.iterrows()):
        ax1.text(row['Avg_Jain_Fairness_Index'] + 0.01, i, f"{row['Avg_Jain_Fairness_Index']:.4f}", 
                va='center', fontsize=9)
    
    # Fairness Ratio
    df_sorted2 = df.sort_values('Avg_Fairness_Ratio', ascending=False)
    bars2 = ax2.barh(df_sorted2['Scheduler'], df_sorted2['Avg_Fairness_Ratio'], color='coral')
    ax2.axvline(x=1.0, color='green', linestyle='--', alpha=0.5, label='Perfect Fairness')
    ax2.set_xlabel('Average Fairness Ratio (Min/Max)', fontsize=12)
    ax2.set_title('Average Fairness Ratio by Scheduler', fontsize=14, fontweight='bold')
    ax2.set_xlim(0, 1.1)
    ax2.grid(axis='x', alpha=0.3)
    ax2.legend()
    
    # Add value labels
    for i, (idx, row) in enumerate(df_sorted2.iterrows()):
        ax2.text(row['Avg_Fairness_Ratio'] + 0.01, i, f"{row['Avg_Fairness_Ratio']:.4f}", 
                va='center', fontsize=9)
    
    plt.tight_layout()
    plt.savefig(f'{output_dir}/fairness_summary_comparison.png', dpi=300, bbox_inches='tight')
    plt.close()
    print(f"Created: {output_dir}/fairness_summary_comparison.png")

def plot_per_flow_distribution(data, output_dir):
    """Create per-flow request distribution chart"""
    if 'per_flow_distribution' not in data:
        print("No per-flow distribution data available")
        return
    
    df = data['per_flow_distribution']
    df['Requests_Serviced'] = pd.to_numeric(df['Requests_Serviced'], errors='coerce')
    df = df.dropna(subset=['Requests_Serviced'])
    
    if df.empty:
        print("No valid per-flow data")
        return
    
    # Group by scheduler and workload
    fig, axes = plt.subplots(2, 3, figsize=(18, 12))
    axes = axes.flatten()
    
    schedulers = df['Scheduler'].unique()
    for idx, scheduler in enumerate(schedulers[:6]):  # Limit to 6 for subplot layout
        if idx >= len(axes):
            break
        
        ax = axes[idx]
        scheduler_data = df[df['Scheduler'] == scheduler]
        
        # Create grouped bar chart for each workload
        workloads = scheduler_data['Workload'].unique()
        x_pos = range(len(workloads))
        width = 0.35
        
        for flow_id in sorted(scheduler_data['Flow_ID'].unique()):
            flow_data = scheduler_data[scheduler_data['Flow_ID'] == flow_id]
            flow_counts = [flow_data[flow_data['Workload'] == w]['Requests_Serviced'].sum() 
                          if len(flow_data[flow_data['Workload'] == w]) > 0 else 0 
                          for w in workloads]
            
            offset = (flow_id - min(scheduler_data['Flow_ID'].unique())) * width
            ax.bar([x + offset for x in x_pos], flow_counts, width, 
                  label=f'Flow {flow_id}', alpha=0.8)
        
        ax.set_xlabel('Workload', fontsize=10)
        ax.set_ylabel('Requests Serviced', fontsize=10)
        ax.set_title(f'{scheduler}', fontsize=11, fontweight='bold')
        ax.set_xticks(x_pos)
        ax.set_xticklabels(workloads, rotation=45, ha='right', fontsize=8)
        ax.legend(fontsize=8)
        ax.grid(axis='y', alpha=0.3)
    
    # Hide unused subplots
    for idx in range(len(schedulers), len(axes)):
        axes[idx].axis('off')
    
    plt.suptitle('Per-Flow Request Distribution by Scheduler', fontsize=16, fontweight='bold', y=0.995)
    plt.tight_layout()
    plt.savefig(f'{output_dir}/per_flow_distribution.png', dpi=300, bbox_inches='tight')
    plt.close()
    print(f"Created: {output_dir}/per_flow_distribution.png")

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 create_fairness_visualizations.py <fairness_results_directory> [output_directory]")
        sys.exit(1)
    
    csv_dir = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else 'fairness_visualizations'
    
    os.makedirs(output_dir, exist_ok=True)
    
    print(f"Loading fairness data from: {csv_dir}")
    data = load_fairness_data(csv_dir)
    
    if not data:
        print("No data files found!")
        sys.exit(1)
    
    print(f"Loaded {len(data)} data tables")
    
    print("\nCreating fairness visualizations...")
    plot_jain_fairness_comparison(data, output_dir)
    plot_fairness_summary(data, output_dir)
    plot_per_flow_distribution(data, output_dir)
    
    print(f"\nFairness visualizations saved to: {output_dir}/")

if __name__ == '__main__':
    main()

