# Lightweight Simulator Visualization Guide

This directory contains visualizations generated from the test matrix results.

## Generated Visualizations

### 1. `fairness_comparison.png`
**What it shows:** Comparison of fairness index across all schedulers
- **Left panel:** Average fairness index with error bars (showing standard deviation)
- **Right panel:** Box plot showing the distribution of fairness values for each scheduler
- **Key insights:** 
  - FLIN and DRR achieve the highest average fairness
  - Shows variability in fairness across different traces

### 2. `fairness_by_trace.png`
**What it shows:** Fairness index grouped by trace and scheduler
- **Format:** Grouped bar chart
- **X-axis:** Traces (9 different workload traces)
- **Y-axis:** Fairness Index (0-1)
- **Key insights:**
  - Shows how each scheduler performs on specific workload patterns
  - Identifies which traces cause fairness degradation
  - Highlights scheduler strengths for different workload types

### 3. `fairness_heatmap.png`
**What it shows:** Fairness index as a heatmap matrix
- **Format:** Heatmap (Trace × Scheduler)
- **Color scale:** Red-Yellow-Green (low to high fairness)
- **Key insights:**
  - Quick visual comparison of all scheduler-trace combinations
  - Identifies problematic combinations (red cells)
  - Shows patterns across schedulers and workloads

### 4. `throughput_comparison.png`
**What it shows:** Throughput performance comparison
- **Left panel:** Average throughput by scheduler with error bars
- **Right panel:** Throughput heatmap (Trace × Scheduler)
- **Key insights:**
  - Throughput differences between schedulers
  - How throughput varies across different traces
  - Trade-offs between fairness and throughput

### 5. `latency_comparison.png`
**What it shows:** Average latency comparison across schedulers
- **Format:** Bar chart with error bars
- **Y-axis:** Average latency in microseconds (μs)
- **Key insights:**
  - Latency performance of each scheduler
  - Impact of fairness mechanisms on latency
  - Scheduler efficiency comparison

### 6. `summary_metrics.png`
**What it shows:** Four-panel summary of key metrics
- **Top-left:** Average Fairness Index
- **Top-right:** Average Throughput Fairness Index
- **Bottom-left:** Average Slowdown (lower is better)
- **Bottom-right:** Average Throughput (MB/s)
- **Key insights:**
  - Comprehensive overview of all key performance metrics
  - Quick comparison across schedulers
  - Balanced view of fairness and performance

## Test Results Summary

- **Total Test Runs:** 54 (9 traces × 6 schedulers)
- **Schedulers Tested:** FIFO, RR, DRR, QFQ, FLIN, MINMAX
- **Traces Tested:** 9 different workload patterns

## Key Findings

1. **FLIN achieves the highest average fairness** (0.9783), demonstrating superior fairness characteristics
2. **DRR shows strong performance** (0.9709), providing excellent byte-level fairness
3. **Fairness varies significantly by workload:**
   - Simple balanced workloads achieve perfect fairness (1.0000) with all schedulers
   - Contention scenarios show fairness degradation
   - FLIN and DRR maintain better fairness under contention

## Generating New Visualizations

To regenerate these visualizations:

```bash
python3 tools/plot_matrix_results.py --summary results/matrix/summary.csv --output plots/
```

## Data Source

All visualizations are generated from: `results/matrix/summary.csv`

This CSV contains results from running all schedulers against all test traces, including:
- Fairness indices (Jain's fairness index)
- Throughput metrics
- Latency measurements
- Slowdown metrics

