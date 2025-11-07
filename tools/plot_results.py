#!/usr/bin/env python3

import argparse
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

def plot_latencies(results_file):
    """Plot latency distributions per process."""
    df = pd.read_csv(results_file)
    
    # Create latency distribution plot
    plt.figure(figsize=(10, 6))
    sns.boxplot(x='process_id', y='latency', data=df)
    plt.title('I/O Latency Distribution by Process')
    plt.xlabel('Process ID')
    plt.ylabel('Latency (µs)')
    plt.savefig('latency_distribution.png')
    plt.close()
    
    # Create fairness index over time plot
    plt.figure(figsize=(10, 6))
    df['fairness_index'].plot()
    plt.title('Fairness Index Over Time')
    plt.xlabel('Request Number')
    plt.ylabel('Jain\'s Fairness Index')
    plt.savefig('fairness_index.png')
    plt.close()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Plot SSD fairness results')
    parser.add_argument('results', type=str, help='Results CSV file')
    
    args = parser.parse_args()
    plot_latencies(args.results)