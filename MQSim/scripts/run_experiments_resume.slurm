#!/bin/bash
#SBATCH --job-name=mqsim_resume
#SBATCH --output=mqsim_resume_%j.out
#SBATCH --error=mqsim_resume_%j.err
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

# Set parallel workload execution
export WORKLOAD_JOBS=16

# Resume from existing results directory
# Update this path to your existing results directory
EXISTING_RESULTS="results/20251208-215310"

# Run resume script
bash scripts/run_experiments_resume.sh "$EXISTING_RESULTS"

# After experiments complete, run analysis
if [ -d "$EXISTING_RESULTS" ]; then
    echo ""
    echo "Running analysis on completed results..."
    
    # Parse results
    PARSED_DIR="${EXISTING_RESULTS}/parsed"
    mkdir -p "$PARSED_DIR"
    python3 tools/parse_results.py "$EXISTING_RESULTS" "$PARSED_DIR" || echo "Warning: parse_results.py failed"
    
    # Analyze fairness
    FAIRNESS_DIR="${EXISTING_RESULTS}/fairness"
    mkdir -p "$FAIRNESS_DIR"
    python3 tools/analyze_fairness.py "$EXISTING_RESULTS" "$FAIRNESS_DIR" || echo "Warning: analyze_fairness.py failed"
    
    # Generate visualizations
    if [ -d "$PARSED_DIR" ]; then
        VIZ_DIR="${EXISTING_RESULTS}/visualizations"
        mkdir -p "$VIZ_DIR"
        python3 tools/create_visualizations.py "$PARSED_DIR" "$VIZ_DIR" || echo "Warning: create_visualizations.py failed"
    fi
    
    if [ -d "$FAIRNESS_DIR" ]; then
        FAIRNESS_VIZ_DIR="${EXISTING_RESULTS}/fairness_visualizations"
        mkdir -p "$FAIRNESS_VIZ_DIR"
        python3 tools/create_fairness_visualizations.py "$FAIRNESS_DIR" "$FAIRNESS_VIZ_DIR" || echo "Warning: create_fairness_visualizations.py failed"
    fi
fi

echo "Job completed at $(date)"

