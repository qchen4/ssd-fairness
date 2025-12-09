# Visualization Summary

## Generated Visualizations

### Fairness Visualizations (`fairness_visualizations/`)

1. **jain_fairness_comparison.png**
   - Jain's Fairness Index comparison across all schedulers and workloads
   - Shows fairness performance for each scheduler
   - Highlights MINMAX's superior fairness under contention

2. **fairness_summary_comparison.png** (if generated)
   - Side-by-side comparison of average Jain's Index and Fairness Ratio
   - Horizontal bar charts showing scheduler rankings

3. **per_flow_distribution.png** (if generated)
   - Per-flow request distribution charts
   - Shows how requests are distributed across flows for each scheduler

### Performance Visualizations (`visualizations/`)

1. **latency_comparison.png**
   - Latency comparison across schedulers and workloads
   - Shows consistent 175μs latency for standard workloads
   - Shows 183μs latency for contention workloads

2. **summary_latency.png**
   - Summary latency chart by scheduler
   - Average latency visualization

## Key Visualizations to Review

### 1. Jain's Fairness Index Comparison
**File:** `fairness_visualizations/jain_fairness_comparison.png`

**What it shows:**
- Fairness performance across all schedulers
- Perfect fairness (1.0) for standard workloads
- Fairness degradation under contention
- MINMAX's superior performance (0.4597 vs 0.4269)

**Key insights:**
- All schedulers achieve perfect fairness for standard workloads
- MINMAX maintains 7.7% better fairness under contention
- Contention workload reveals true fairness characteristics

### 2. Latency Comparison
**File:** `visualizations/latency_comparison.png`

**What it shows:**
- Consistent latency across all schedulers
- 175μs for standard workloads
- 183μs for contention workloads

**Key insights:**
- Fairness-aware schedulers match baseline performance
- No performance penalty for fairness mechanisms

## Visualization Locations

- **Fairness:** `MQSim/fairness_visualizations/`
- **Performance:** `MQSim/visualizations/`

## Viewing Visualizations

The PNG files can be viewed in any image viewer or included in reports. All visualizations are high-resolution (300 DPI) suitable for publication.

