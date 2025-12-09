# Running MQSim Experiments with SLURM

## Scripts Overview

### `run_experiments.sh`
- **Purpose**: Runs MQSim experiments only
- **What it does**:
  - Loops through all workloads and schedulers
  - Executes MQSim simulations
  - Stores results in `results/<timestamp>/`
  - Creates a zip archive of results
- **Use when**: You only want to run experiments, no analysis

### `run_experiments_with_viz.sh`
- **Purpose**: Complete pipeline - experiments + analysis + visualizations
- **What it does**:
  1. Calls `run_experiments.sh` to run all experiments
  2. Parses results using `parse_results.py`
  3. Analyzes fairness metrics using `analyze_fairness.py`
  4. Generates performance visualizations
  5. Generates fairness visualizations
- **Use when**: You want the complete workflow (recommended)

## SLURM Usage

### Submit Job
```bash
cd /home/hice1/qchen438/Documents/ssd-fairness/MQSim
sbatch run_experiments.slurm
```

### Monitor Job
```bash
# Check status
squeue -u $USER

# View output (replace JOBID)
tail -f mqsim_experiments_JOBID.out

# View errors
tail -f mqsim_experiments_JOBID.err
```

### Current Configuration
- **Time**: 8 hours
- **CPUs**: 4 (for parallel workload execution)
- **Memory**: 16GB
- **Pipeline**: Uses `run_experiments_with_viz.sh` (complete workflow)

## Results Location

After completion, results will be in:
- `results/<timestamp>/` - Raw experiment results
- `results/<timestamp>/parsed/` - Parsed CSV tables
- `results/<timestamp>/fairness/` - Fairness analysis
- `results/<timestamp>/visualizations/` - Performance charts
- `results/<timestamp>/fairness_visualizations/` - Fairness charts

