# Results Checking Guide

## Quick Status Check

Run this command to see a comprehensive summary:
```bash
cd /home/hice1/qchen438/Documents/ssd-fairness/MQSim
./check_results.sh
```

## Current Status

**Latest Run:** `results/20251208-210325`

**Status:** ⚠️ Only 1/5 schedulers completed (RR only)
- ✅ RR: 5 workloads completed
- ❌ DRR: Not completed
- ❌ QFQ: Not completed  
- ❌ MINMAX: Not completed
- ❌ FLIN: Not completed

## Viewing Results

### 1. Directory Structure
```
results/20251208-210325/
└── RR/
    ├── workload_scenario_1/
    │   ├── run.log
    │   └── workload_scenario_1_scenario_1.xml
    ├── workload_scenario_2/
    ├── workload_scenario_3/
    ├── workload-backend-contention-flow-1/
    └── workload-backend-contention-flow-1-flow-2/
```

### 2. View Individual Results

**View log file:**
```bash
cat results/20251208-210325/RR/workload_scenario_1/run.log
```

**View XML results:**
```bash
cat results/20251208-210325/RR/workload_scenario_1/workload_scenario_1_scenario_1.xml
```

**List all results:**
```bash
cd results/20251208-210325
find . -name "*.log" -o -name "*.xml" | sort
```

### 3. Check What Data You Have

**Count completed experiments:**
```bash
cd /home/hice1/qchen438/Documents/ssd-fairness/MQSim
find results/20251208-210325 -name "run.log" | wc -l
```

**List all schedulers:**
```bash
ls -d results/20251208-210325/*/
```

**List all workloads for a scheduler:**
```bash
ls -d results/20251208-210325/RR/*/
```

## Generate Visualizations from Current Results

Even with partial results, you can generate visualizations:

```bash
cd /home/hice1/qchen438/Documents/ssd-fairness/MQSim

# Parse results
python3 parse_results.py results/20251208-210325 parsed_results_temp/

# Analyze fairness
python3 analyze_fairness.py results/20251208-210325 fairness_temp/

# Generate visualizations
python3 create_visualizations.py parsed_results_temp/ visualizations_new/
python3 create_fairness_visualizations.py fairness_temp/ fairness_visualizations_new/
```

## Complete All Experiments

To run all 5 schedulers across all workloads:

```bash
cd /home/hice1/qchen438/Documents/ssd-fairness/MQSim
sbatch run_experiments.slurm
```

Then check status:
```bash
squeue -u $USER
./check_job_status.sh <JOB_ID>
```

## Existing Complete Results

You also have visualizations from previous complete runs:
- `visualizations/` - Performance charts
- `fairness_visualizations/` - Fairness charts

View them with:
```bash
./view_visualizations.sh
```

## Useful Commands

**Check job status:**
```bash
./check_job_status.sh <JOB_ID>
```

**View results summary:**
```bash
./check_results.sh
```

**View visualizations:**
```bash
./view_visualizations.sh
```

**Find all result directories:**
```bash
ls -ltr results/
```

