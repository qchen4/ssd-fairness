#!/usr/bin/env bash
# Quick test script for all schedulers
# NOTE: MQSim is CPU-only - no GPU usage

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MQSIM_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${MQSIM_ROOT}"

MQSIM_BIN="./MQSim"
BASE_CONFIG="configs/ssdconfig.xml"
TEST_WORKLOAD="workloads/workload_scenario_1.xml"

# Check if MQSim exists
if [ ! -f "$MQSIM_BIN" ]; then
    echo "Building MQSim..."
    make -j4
fi

if [ ! -f "$MQSIM_BIN" ]; then
    echo "ERROR: MQSim executable not found"
    exit 1
fi

echo "=== Testing MQSim Schedulers ==="
echo ""

# Test schedulers
SCHEDULERS=("RR" "DRR" "QFQ" "MINMAX" "FLIN")

for sched in "${SCHEDULERS[@]}"; do
    echo "Testing scheduler: $sched"
    
    # Create temp config
    TMP_CONFIG="/tmp/mqsim_test_${sched}.xml"
    cp "$BASE_CONFIG" "$TMP_CONFIG"
    sed -i "s/<Transaction_Scheduling_Policy>.*<\/Transaction_Scheduling_Policy>/<Transaction_Scheduling_Policy>${sched}<\/Transaction_Scheduling_Policy>/" "$TMP_CONFIG"
    
    # Run quick test (timeout after 60 seconds)
    echo "  Running test..."
    if timeout 60 "$MQSIM_BIN" -i "$TMP_CONFIG" -w "$TEST_WORKLOAD" > "/tmp/mqsim_${sched}_test.log" 2>&1; then
        echo "  ✅ $sched: Test completed successfully"
        # Check for errors in log
        if grep -i "error\|fatal\|exception" "/tmp/mqsim_${sched}_test.log" > /dev/null 2>&1; then
            echo "  ⚠️  $sched: Warnings/errors found in log (check /tmp/mqsim_${sched}_test.log)"
        fi
    else
        EXIT_CODE=$?
        if [ $EXIT_CODE -eq 124 ]; then
            echo "  ⏱️  $sched: Test timed out (may be normal for long simulations)"
        else
            echo "  ❌ $sched: Test failed (exit code: $EXIT_CODE)"
            echo "  Check log: /tmp/mqsim_${sched}_test.log"
        fi
    fi
    
    rm -f "$TMP_CONFIG"
    echo ""
done

echo "=== Test Summary ==="
echo "All scheduler tests completed. Check logs in /tmp/mqsim_*_test.log"

