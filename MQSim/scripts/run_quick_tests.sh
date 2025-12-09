#!/usr/bin/env bash
# Quick test script that runs a subset of experiments for faster results

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MQSIM_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${MQSIM_ROOT}"

MQSIM_BIN="./MQSim"
BASE_CONFIG="configs/ssdconfig.xml"
TEST_WORKLOAD="workloads/workload_scenario_1.xml"
RESULTS_DIR="results/quick_test_$(date +%Y%m%d-%H%M%S)"

if [ ! -f "$MQSIM_BIN" ]; then
    echo "Building MQSim..."
    make -j4
fi

if [ ! -f "$MQSIM_BIN" ]; then
    echo "ERROR: MQSim executable not found"
    exit 1
fi

mkdir -p "$RESULTS_DIR"

echo "=== Running Quick Tests ==="
echo "Results will be saved to: $RESULTS_DIR"
echo ""

SCHEDULERS=("RR" "DRR" "QFQ" "MINMAX" "FLIN")

for sched in "${SCHEDULERS[@]}"; do
    echo "Testing scheduler: $sched"
    
    SCHED_DIR="$RESULTS_DIR/$sched"
    mkdir -p "$SCHED_DIR"
    
    TMP_CONFIG="$SCHED_DIR/config.xml"
    cp "$BASE_CONFIG" "$TMP_CONFIG"
    sed -i "s/<Transaction_Scheduling_Policy>.*<\/Transaction_Scheduling_Policy>/<Transaction_Scheduling_Policy>${sched}<\/Transaction_Scheduling_Policy>/" "$TMP_CONFIG"
    
    echo "  Running simulation..."
    ./MQSim -i "$TMP_CONFIG" -w "$TEST_WORKLOAD" 2>&1 | tee "$SCHED_DIR/run.log"
    
    # Move any result files
    if [ -f "MQSim_Results"*.xml ]; then
        mv MQSim_Results*.xml "$SCHED_DIR/" 2>/dev/null || true
    fi
    
    echo "  ✅ $sched: Completed"
    echo ""
done

echo "=== Quick Tests Complete ==="
echo "Results saved to: $RESULTS_DIR"

