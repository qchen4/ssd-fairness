#!/bin/bash
#SBATCH --job-name=mqsim_viz
#SBATCH --output=mqsim_viz_%j.out
#SBATCH --error=mqsim_viz_%j.err
#SBATCH --time=8:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=48G
#SBATCH --partition=ice-cpu

# Change to the MQSim directory
cd "$SLURM_SUBMIT_DIR" || cd "$(dirname "$0")" || exit 1
MQSIM_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$MQSIM_ROOT"

# Set parallel workload execution (use 16 CPUs for parallel workloads)
export WORKLOAD_JOBS=16

# Run the experiments and generate visualizations
bash scripts/run_experiments_with_viz.sh

echo "Job completed at $(date)"

