# Visualization Viewing Guide

## 📊 Available Visualizations

All visualizations are PNG files ready to view. You currently have **5 visualization files** generated from MQSim experiments.

### Performance Visualizations (`visualizations/`)

1. **latency_comparison.png** (193 KB)
   - **What it shows:** Latency comparison across all schedulers and workloads
   - **Key insights:** 
     - Consistent ~175μs latency for standard workloads
     - ~183μs latency for contention workloads
     - All schedulers perform similarly
   - **File:** `/home/hice1/qchen438/Documents/ssd-fairness/MQSim/visualizations/latency_comparison.png`

2. **summary_latency.png** (144 KB)
   - **What it shows:** Summary latency chart by scheduler
   - **Key insights:** Average latency visualization across all workloads
   - **File:** `/home/hice1/qchen438/Documents/ssd-fairness/MQSim/visualizations/summary_latency.png`

### Fairness Visualizations (`fairness_visualizations/`)

1. **jain_fairness_comparison.png** (214 KB)
   - **What it shows:** Jain's Fairness Index comparison across all schedulers
   - **Key insights:**
     - Perfect fairness (1.0) for standard workloads
     - Fairness degradation under contention
     - MINMAX shows superior fairness (0.4597 vs 0.4269 for others)
   - **File:** `/home/hice1/qchen438/Documents/ssd-fairness/MQSim/fairness_visualizations/jain_fairness_comparison.png`

2. **fairness_summary_comparison.png** (187 KB)
   - **What it shows:** Side-by-side comparison of average Jain's Index and Fairness Ratio
   - **Key insights:** Horizontal bar charts showing scheduler rankings
   - **File:** `/home/hice1/qchen438/Documents/ssd-fairness/MQSim/fairness_visualizations/fairness_summary_comparison.png`

3. **per_flow_distribution.png** (337 KB)
   - **What it shows:** Per-flow request distribution charts
   - **Key insights:** Shows how requests are distributed across flows for each scheduler
   - **File:** `/home/hice1/qchen438/Documents/ssd-fairness/MQSim/fairness_visualizations/per_flow_distribution.png`

## 🖼️ How to View

### Method 1: In Your IDE (Easiest)
Since you're using Cursor/VS Code:
1. Open the file explorer sidebar
2. Navigate to `MQSim/visualizations/` or `MQSim/fairness_visualizations/`
3. Click on any `.png` file - it will open in the built-in image viewer
4. You can navigate between images using arrow keys

### Method 2: Quick View Script
Run the helper script:
```bash
cd /home/hice1/qchen438/Documents/ssd-fairness/MQSim
./view_visualizations.sh
```

### Method 3: Direct File Access
All files are located at:
- Performance: `/home/hice1/qchen438/Documents/ssd-fairness/MQSim/visualizations/`
- Fairness: `/home/hice1/qchen438/Documents/ssd-fairness/MQSim/fairness_visualizations/`

### Method 4: Copy to Local Machine
If you want to view on your local computer:
```bash
# From your local machine:
scp -r qchen438@login-ice-2:/home/hice1/qchen438/Documents/ssd-fairness/MQSim/visualizations ./
scp -r qchen438@login-ice-2:/home/hice1/qchen438/Documents/ssd-fairness/MQSim/fairness_visualizations ./
```

## 📝 Notes

- **Job Status:** The latest job run (3962274) encountered a parse error and stopped early
- **Visualizations:** Current visualizations are from previous complete runs
- **Script Fix:** The experiment script has been updated to continue on errors instead of stopping
- **Regeneration:** To regenerate visualizations from new results, run:
  ```bash
  cd /home/hice1/qchen438/Documents/ssd-fairness/MQSim
  ./run_experiments_with_viz.sh
  ```

## 🔍 Quick File List

```
visualizations/
├── latency_comparison.png (193 KB)
└── summary_latency.png (144 KB)

fairness_visualizations/
├── fairness_summary_comparison.png (187 KB)
├── jain_fairness_comparison.png (214 KB)
└── per_flow_distribution.png (337 KB)
```

