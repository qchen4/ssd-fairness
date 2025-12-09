#!/usr/bin/env bash

# Resume experiments from existing results directory
# Usage: ./run_experiments_resume.sh <existing_results_directory>

set -euo pipefail

if [ $# -lt 1 ]; then
    echo "Usage: $0 <existing_results_directory>"
    echo "Example: $0 results/20251208-215310"
    exit 1
fi

EXISTING_RESULTS="$1"
if [ ! -d "$EXISTING_RESULTS" ]; then
    echo "Error: Directory $EXISTING_RESULTS does not exist!"
    exit 1
fi

# Source the main experiment script configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MQSIM_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${MQSIM_ROOT}"

# Load workload and policy lists from run_experiments.sh
source <(grep -A 20 "^WORKLOADS=(" scripts/run_experiments.sh | head -21)
source <(grep -A 6 "^POLICIES=(" scripts/run_experiments.sh | head -7)

BASE_CONFIG="configs/ssdconfig.xml"
MQSIM_BIN="./MQSim"

# Check which experiments are already done
check_experiment_done() {
    local policy=$1
    local workload=$2
    local scenario_name
    scenario_name="$(basename "${workload}" .xml)"
    local result_dir="${EXISTING_RESULTS}/${policy}/${scenario_name}"
    
    if [ -f "${result_dir}/run.log" ]; then
        return 0  # Done
    else
        return 1  # Not done
    fi
}

# Run missing experiments
WORKLOAD_JOBS=${WORKLOAD_JOBS:-12}
mkdir -p "$EXISTING_RESULTS"

echo "Resuming experiments in: $EXISTING_RESULTS"
echo "Running with $WORKLOAD_JOBS parallel jobs"
echo ""

for policy in "${POLICIES[@]}"; do
    echo ""
    echo "== Policy ${policy} (concurrency: ${WORKLOAD_JOBS}) =="
    job_count=0
    for workload in "${WORKLOADS[@]}"; do
        # Skip if already done
        if check_experiment_done "$policy" "$workload"; then
            echo "Skipping ${policy}/${workload} (already done)"
            continue
        fi
        
        # Run the experiment
        scenario_name="$(basename "${workload}" .xml)"
        dest_dir="${EXISTING_RESULTS}/${policy}/${scenario_name}"
        tmp_config="$(mktemp "${dest_dir//\//_}.XXXX.xml")"
        
        cp "${BASE_CONFIG}" "${tmp_config}"
        sed -i -E "s#<Transaction_Scheduling_Policy>[^<]*</Transaction_Scheduling_Policy>#<Transaction_Scheduling_Policy>${policy}</Transaction_Scheduling_Policy>#" "${tmp_config}"
        
        mkdir -p "${dest_dir}"
        echo "=== ${policy} :: ${scenario_name} ==="
        
        set +e
        "${MQSIM_BIN}" -i "${tmp_config}" -w "${workload}" | tee "${dest_dir}/run.log"
        run_status=$?
        set -e
        rm -f "${tmp_config}"
        
        if [[ ${run_status} -ne 0 ]]; then
            echo "MQSim failed for ${policy}/${scenario_name} (continuing...)" >&2
        else
            # Collect outputs
            base_no_ext="${workload%.*}"
            shopt -s nullglob
            xmls=( "${base_no_ext}_scenario_"*.xml )
            for path in "${xmls[@]}"; do
                cp "${path}" "${dest_dir}/"
                rm -f "${path}"
            done
            shopt -u nullglob
        fi
        
        # Parallel execution control
        job_count=$((job_count + 1))
        if (( job_count >= WORKLOAD_JOBS )); then
            wait -n || true
            job_count=$((job_count - 1))
        fi
    done
    wait || true
done

echo ""
echo "Resume complete! Results in: $EXISTING_RESULTS"

