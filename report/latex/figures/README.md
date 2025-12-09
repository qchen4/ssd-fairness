# Figures Directory

This directory contains all result figures from both Lightweight Simulator and MQSim experiments, with duplicates excluded.

## Contents

### Lightweight Simulator Results
- `fairness_comparison.png` - Fairness index comparison across schedulers
- `fairness_by_trace.png` - Fairness grouped by trace and scheduler
- `fairness_heatmap.png` - Fairness heatmap matrix
- `throughput_comparison.png` - Throughput comparison charts
- `latency_comparison.png` - Latency comparison across schedulers
- `summary_metrics.png` - Four-panel summary dashboard
- `wear_imbalance.png` - Wear leveling imbalance visualization
- `high_vs_low_metrics.png` - High vs low intensity metrics

### MQSim Results
- `jain_fairness_comparison.png` - Jain's fairness index comparison
- `fairness_analysis.png` - Detailed fairness analysis
- `performance_comparison.png` - Performance metrics comparison
- `workload_comparison.png` - Workload-specific comparisons
- `detailed_insights.png` - Detailed performance insights
- `summary_latency.png` - Summary latency visualization
- `summary_throughput.png` - Summary throughput visualization
- `fairness_summary_comparison.png` - Fairness summary comparison
- `per_flow_distribution.png` - Per-flow distribution analysis

## Note on Duplicates

When multiple versions of the same filename existed in different locations:
- Files already in `figures/` were kept (not overwritten)
- For new files, the version closest to the project root was copied
- This ensures we have one representative version of each figure

## Usage

These figures are referenced in:
- `report/Final_Report.tex` - Main research paper
- Documentation files
- Presentation materials

## Source Locations

- **Lightweight Simulator**: `Lightweight_Simulator/plots/` and `Lightweight_Simulator/results/`
- **MQSim**: `MQSim/visualizations/`, `MQSim/fairness_visualizations/`, and `MQSim/results/*/`

