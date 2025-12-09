#!/usr/bin/env python3
"""
Create comprehensive visualizations for Lightweight Simulator test matrix results.

Usage:
    python3 tools/plot_matrix_results.py --summary results/matrix/summary.csv --output plots/
"""

import argparse
import pandas as pd
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import numpy as np

# Set style
sns.set_style("whitegrid")
plt.rcParams['figure.dpi'] = 100
plt.rcParams['savefig.dpi'] = 300
plt.rcParams['font.size'] = 10


def load_data(summary_path):
    """Load the summary CSV."""
    df = pd.read_csv(summary_path)
    # Convert numeric columns
    numeric_cols = ['fairness_index', 'throughput_fairness_index', 'throughput_MBps', 
                    'avg_latency_s', 'avg_slowdown', 'completed', 'runtime_s']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    return df


def plot_fairness_comparison(df, output_dir):
    """Plot fairness index comparison across schedulers."""
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    
    # Average fairness by scheduler
    scheduler_avg = df.groupby('scheduler')['fairness_index'].agg(['mean', 'std', 'min', 'max']).reset_index()
    scheduler_avg = scheduler_avg.sort_values('mean', ascending=False)
    
    ax = axes[0]
    x_pos = np.arange(len(scheduler_avg))
    bars = ax.bar(x_pos, scheduler_avg['mean'], yerr=scheduler_avg['std'], 
                  capsize=5, alpha=0.8, color=sns.color_palette("husl", len(scheduler_avg)))
    ax.set_xlabel('Scheduler', fontsize=12, fontweight='bold')
    ax.set_ylabel('Fairness Index (Jain\'s)', fontsize=12, fontweight='bold')
    ax.set_title('Average Fairness Index by Scheduler', fontsize=14, fontweight='bold')
    ax.set_xticks(x_pos)
    ax.set_xticklabels(scheduler_avg['scheduler'], rotation=45, ha='right')
    ax.set_ylim([0, 1.1])
    ax.grid(axis='y', alpha=0.3)
    
    # Add value labels on bars
    for i, (bar, mean_val) in enumerate(zip(bars, scheduler_avg['mean'])):
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height + scheduler_avg['std'].iloc[i] + 0.02,
                f'{mean_val:.3f}', ha='center', va='bottom', fontsize=9)
    
    # Fairness distribution (box plot)
    ax = axes[1]
    scheduler_order = scheduler_avg['scheduler'].tolist()
    df_ordered = df.copy()
    df_ordered['scheduler'] = pd.Categorical(df_ordered['scheduler'], categories=scheduler_order, ordered=True)
    sns.boxplot(data=df_ordered, x='scheduler', y='fairness_index', ax=ax, hue='scheduler', palette="husl", legend=False)
    ax.set_xlabel('Scheduler', fontsize=12, fontweight='bold')
    ax.set_ylabel('Fairness Index', fontsize=12, fontweight='bold')
    ax.set_title('Fairness Index Distribution by Scheduler', fontsize=14, fontweight='bold')
    ax.tick_params(axis='x', rotation=45)
    ax.grid(axis='y', alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(output_dir / 'fairness_comparison.png', bbox_inches='tight')
    plt.close()
    print(f"Created: {output_dir / 'fairness_comparison.png'}")


def plot_fairness_by_trace(df, output_dir):
    """Plot fairness index grouped by trace and scheduler."""
    fig, ax = plt.subplots(figsize=(16, 8))
    
    # Prepare data
    traces = sorted(df['trace'].unique())
    schedulers = sorted(df['scheduler'].unique())
    
    x = np.arange(len(traces))
    width = 0.13
    multiplier = 0
    
    colors = sns.color_palette("husl", len(schedulers))
    
    for scheduler in schedulers:
        offset = width * multiplier
        scheduler_data = df[df['scheduler'] == scheduler]
        values = [scheduler_data[scheduler_data['trace'] == trace]['fairness_index'].values[0] 
                 if len(scheduler_data[scheduler_data['trace'] == trace]) > 0 else 0 
                 for trace in traces]
        bars = ax.bar(x + offset, values, width, label=scheduler, alpha=0.8, color=colors[multiplier])
        multiplier += 1
    
    ax.set_xlabel('Trace', fontsize=12, fontweight='bold')
    ax.set_ylabel('Fairness Index', fontsize=12, fontweight='bold')
    ax.set_title('Fairness Index by Trace and Scheduler', fontsize=14, fontweight='bold')
    ax.set_xticks(x + width * (len(schedulers) - 1) / 2)
    ax.set_xticklabels([t.replace('.csv', '') for t in traces], rotation=45, ha='right')
    ax.legend(loc='upper left', ncol=3, frameon=True, fancybox=True, shadow=True)
    ax.set_ylim([0, 1.1])
    ax.grid(axis='y', alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(output_dir / 'fairness_by_trace.png', bbox_inches='tight')
    plt.close()
    print(f"Created: {output_dir / 'fairness_by_trace.png'}")


def plot_throughput_comparison(df, output_dir):
    """Plot throughput comparison."""
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    
    # Average throughput by scheduler
    scheduler_avg = df.groupby('scheduler')['throughput_MBps'].agg(['mean', 'std']).reset_index()
    scheduler_avg = scheduler_avg.sort_values('mean', ascending=False)
    
    ax = axes[0]
    x_pos = np.arange(len(scheduler_avg))
    bars = ax.bar(x_pos, scheduler_avg['mean'], yerr=scheduler_avg['std'], 
                  capsize=5, alpha=0.8, color=sns.color_palette("muted", len(scheduler_avg)))
    ax.set_xlabel('Scheduler', fontsize=12, fontweight='bold')
    ax.set_ylabel('Throughput (MB/s)', fontsize=12, fontweight='bold')
    ax.set_title('Average Throughput by Scheduler', fontsize=14, fontweight='bold')
    ax.set_xticks(x_pos)
    ax.set_xticklabels(scheduler_avg['scheduler'], rotation=45, ha='right')
    ax.grid(axis='y', alpha=0.3)
    
    # Add value labels
    for bar, mean_val in zip(bars, scheduler_avg['mean']):
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
                f'{mean_val:.1f}', ha='center', va='bottom', fontsize=9)
    
    # Throughput by trace (heatmap)
    ax = axes[1]
    pivot = df.pivot_table(values='throughput_MBps', index='trace', columns='scheduler', aggfunc='mean')
    pivot.index = [t.replace('.csv', '') for t in pivot.index]
    sns.heatmap(pivot, annot=True, fmt='.1f', cmap='YlOrRd', ax=ax, cbar_kws={'label': 'Throughput (MB/s)'})
    ax.set_xlabel('Scheduler', fontsize=12, fontweight='bold')
    ax.set_ylabel('Trace', fontsize=12, fontweight='bold')
    ax.set_title('Throughput Heatmap (Trace × Scheduler)', fontsize=14, fontweight='bold')
    plt.setp(ax.get_xticklabels(), rotation=45, ha='right')
    plt.setp(ax.get_yticklabels(), rotation=0)
    
    plt.tight_layout()
    plt.savefig(output_dir / 'throughput_comparison.png', bbox_inches='tight')
    plt.close()
    print(f"Created: {output_dir / 'throughput_comparison.png'}")


def plot_latency_comparison(df, output_dir):
    """Plot latency comparison."""
    fig, ax = plt.subplots(figsize=(12, 6))
    
    # Convert latency to microseconds for better readability
    df['avg_latency_us'] = df['avg_latency_s'] * 1e6
    
    scheduler_avg = df.groupby('scheduler')['avg_latency_us'].agg(['mean', 'std']).reset_index()
    scheduler_avg = scheduler_avg.sort_values('mean', ascending=False)
    
    x_pos = np.arange(len(scheduler_avg))
    bars = ax.bar(x_pos, scheduler_avg['mean'], yerr=scheduler_avg['std'], 
                  capsize=5, alpha=0.8, color=sns.color_palette("coolwarm", len(scheduler_avg)))
    ax.set_xlabel('Scheduler', fontsize=12, fontweight='bold')
    ax.set_ylabel('Average Latency (μs)', fontsize=12, fontweight='bold')
    ax.set_title('Average Latency by Scheduler', fontsize=14, fontweight='bold')
    ax.set_xticks(x_pos)
    ax.set_xticklabels(scheduler_avg['scheduler'], rotation=45, ha='right')
    ax.grid(axis='y', alpha=0.3)
    
    # Add value labels
    for bar, mean_val in zip(bars, scheduler_avg['mean']):
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
                f'{mean_val:.2f}', ha='center', va='bottom', fontsize=9)
    
    plt.tight_layout()
    plt.savefig(output_dir / 'latency_comparison.png', bbox_inches='tight')
    plt.close()
    print(f"Created: {output_dir / 'latency_comparison.png'}")


def plot_summary_metrics(df, output_dir):
    """Plot summary metrics comparison."""
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    
    schedulers = sorted(df['scheduler'].unique())
    
    # 1. Fairness Index (top-left)
    ax = axes[0, 0]
    fairness_avg = df.groupby('scheduler')['fairness_index'].mean().sort_values(ascending=False)
    bars = ax.bar(range(len(fairness_avg)), fairness_avg.values, 
                 color=sns.color_palette("husl", len(fairness_avg)), alpha=0.8)
    ax.set_xlabel('Scheduler', fontsize=11, fontweight='bold')
    ax.set_ylabel('Fairness Index', fontsize=11, fontweight='bold')
    ax.set_title('Average Fairness Index', fontsize=12, fontweight='bold')
    ax.set_xticks(range(len(fairness_avg)))
    ax.set_xticklabels(fairness_avg.index, rotation=45, ha='right')
    ax.set_ylim([0, 1.1])
    ax.grid(axis='y', alpha=0.3)
    for i, (bar, val) in enumerate(zip(bars, fairness_avg.values)):
        ax.text(bar.get_x() + bar.get_width()/2., bar.get_height() + 0.02,
                f'{val:.3f}', ha='center', va='bottom', fontsize=9)
    
    # 2. Throughput Fairness (top-right)
    ax = axes[0, 1]
    tp_fairness_avg = df.groupby('scheduler')['throughput_fairness_index'].mean().sort_values(ascending=False)
    bars = ax.bar(range(len(tp_fairness_avg)), tp_fairness_avg.values,
                 color=sns.color_palette("muted", len(tp_fairness_avg)), alpha=0.8)
    ax.set_xlabel('Scheduler', fontsize=11, fontweight='bold')
    ax.set_ylabel('Throughput Fairness Index', fontsize=11, fontweight='bold')
    ax.set_title('Average Throughput Fairness Index', fontsize=12, fontweight='bold')
    ax.set_xticks(range(len(tp_fairness_avg)))
    ax.set_xticklabels(tp_fairness_avg.index, rotation=45, ha='right')
    ax.set_ylim([0, 1.1])
    ax.grid(axis='y', alpha=0.3)
    for i, (bar, val) in enumerate(zip(bars, tp_fairness_avg.values)):
        ax.text(bar.get_x() + bar.get_width()/2., bar.get_height() + 0.02,
                f'{val:.3f}', ha='center', va='bottom', fontsize=9)
    
    # 3. Average Slowdown (bottom-left)
    ax = axes[1, 0]
    slowdown_avg = df.groupby('scheduler')['avg_slowdown'].mean().sort_values(ascending=True)
    bars = ax.bar(range(len(slowdown_avg)), slowdown_avg.values,
                 color=sns.color_palette("coolwarm", len(slowdown_avg)), alpha=0.8)
    ax.set_xlabel('Scheduler', fontsize=11, fontweight='bold')
    ax.set_ylabel('Average Slowdown', fontsize=11, fontweight='bold')
    ax.set_title('Average Slowdown (lower is better)', fontsize=12, fontweight='bold')
    ax.set_xticks(range(len(slowdown_avg)))
    ax.set_xticklabels(slowdown_avg.index, rotation=45, ha='right')
    ax.grid(axis='y', alpha=0.3)
    for i, (bar, val) in enumerate(zip(bars, slowdown_avg.values)):
        if val > 0:
            ax.text(bar.get_x() + bar.get_width()/2., bar.get_height() + 0.01,
                    f'{val:.3f}', ha='center', va='bottom', fontsize=9)
    
    # 4. Throughput (bottom-right)
    ax = axes[1, 1]
    tp_avg = df.groupby('scheduler')['throughput_MBps'].mean().sort_values(ascending=False)
    bars = ax.bar(range(len(tp_avg)), tp_avg.values,
                 color=sns.color_palette("viridis", len(tp_avg)), alpha=0.8)
    ax.set_xlabel('Scheduler', fontsize=11, fontweight='bold')
    ax.set_ylabel('Throughput (MB/s)', fontsize=11, fontweight='bold')
    ax.set_title('Average Throughput', fontsize=12, fontweight='bold')
    ax.set_xticks(range(len(tp_avg)))
    ax.set_xticklabels(tp_avg.index, rotation=45, ha='right')
    ax.grid(axis='y', alpha=0.3)
    for i, (bar, val) in enumerate(zip(bars, tp_avg.values)):
        ax.text(bar.get_x() + bar.get_width()/2., bar.get_height() + 10,
                f'{val:.1f}', ha='center', va='bottom', fontsize=9)
    
    plt.tight_layout()
    plt.savefig(output_dir / 'summary_metrics.png', bbox_inches='tight')
    plt.close()
    print(f"Created: {output_dir / 'summary_metrics.png'}")


def plot_fairness_heatmap(df, output_dir):
    """Plot fairness index as a heatmap."""
    fig, ax = plt.subplots(figsize=(12, 8))
    
    pivot = df.pivot_table(values='fairness_index', index='trace', columns='scheduler', aggfunc='mean')
    pivot.index = [t.replace('.csv', '') for t in pivot.index]
    
    sns.heatmap(pivot, annot=True, fmt='.3f', cmap='RdYlGn', vmin=0, vmax=1, 
                ax=ax, cbar_kws={'label': 'Fairness Index'}, linewidths=0.5)
    ax.set_xlabel('Scheduler', fontsize=12, fontweight='bold')
    ax.set_ylabel('Trace', fontsize=12, fontweight='bold')
    ax.set_title('Fairness Index Heatmap (Trace × Scheduler)', fontsize=14, fontweight='bold')
    plt.setp(ax.get_xticklabels(), rotation=45, ha='right')
    plt.setp(ax.get_yticklabels(), rotation=0)
    
    plt.tight_layout()
    plt.savefig(output_dir / 'fairness_heatmap.png', bbox_inches='tight')
    plt.close()
    print(f"Created: {output_dir / 'fairness_heatmap.png'}")


def main():
    parser = argparse.ArgumentParser(description='Plot Lightweight Simulator test matrix results')
    parser.add_argument('--summary', default='results/matrix/summary.csv',
                       help='Path to summary CSV file')
    parser.add_argument('--output', default='plots',
                       help='Output directory for plots')
    args = parser.parse_args()
    
    summary_path = Path(args.summary)
    if not summary_path.exists():
        raise SystemExit(f"Summary file not found: {summary_path}")
    
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Loading data from {summary_path}...")
    df = load_data(summary_path)
    print(f"Loaded {len(df)} test results")
    
    print("\nGenerating visualizations...")
    try:
        plot_fairness_comparison(df, output_dir)
    except Exception as e:
        print(f"Error in plot_fairness_comparison: {e}")
        import traceback
        traceback.print_exc()
    
    try:
        plot_fairness_by_trace(df, output_dir)
    except Exception as e:
        print(f"Error in plot_fairness_by_trace: {e}")
        import traceback
        traceback.print_exc()
    
    try:
        plot_fairness_heatmap(df, output_dir)
    except Exception as e:
        print(f"Error in plot_fairness_heatmap: {e}")
        import traceback
        traceback.print_exc()
    
    try:
        plot_throughput_comparison(df, output_dir)
    except Exception as e:
        print(f"Error in plot_throughput_comparison: {e}")
        import traceback
        traceback.print_exc()
    
    try:
        plot_latency_comparison(df, output_dir)
    except Exception as e:
        print(f"Error in plot_latency_comparison: {e}")
        import traceback
        traceback.print_exc()
    
    try:
        plot_summary_metrics(df, output_dir)
    except Exception as e:
        print(f"Error in plot_summary_metrics: {e}")
        import traceback
        traceback.print_exc()
    
    print(f"\n✓ All visualizations saved to: {output_dir}/")


if __name__ == '__main__':
    main()

