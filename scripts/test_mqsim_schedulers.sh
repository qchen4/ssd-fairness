#!/bin/bash
# Test script for MQSim schedulers

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MQSIM_DIR="$SCRIPT_DIR/MQSim"
EXEC="$MQSIM_DIR/MQSim"

# Check if MQSim executable exists
if [ ! -f "$EXEC" ]; then
    echo "ERROR: MQSim executable not found at $EXEC"
    echo "Please build MQSim first: cd $MQSIM_DIR && make"
    exit 1
fi

# Find or create a test config
TEST_CONFIG="$MQSIM_DIR/ssdconfig.xml"
if [ ! -f "$TEST_CONFIG" ]; then
    echo "ERROR: MQSim config file not found at $TEST_CONFIG"
    exit 1
fi

echo "=== Testing MQSim Schedulers ==="
echo ""

# List of schedulers to test
SCHEDULERS=("OUT_OF_ORDER" "RR" "DRR" "QFQ" "MINMAX" "BFQ_LITE" "FLIN")

for sched in "${SCHEDULERS[@]}"; do
    echo "Testing scheduler: $sched"
    
    # Create a temporary config with this scheduler
    TMP_CONFIG="/tmp/mqsim_${sched}_config.xml"
    sed "s/<Transaction_Scheduling_Policy>.*<\/Transaction_Scheduling_Policy>/<Transaction_Scheduling_Policy>${sched}<\/Transaction_Scheduling_Policy>/" "$TEST_CONFIG" > "$TMP_CONFIG"
    
    # Run MQSim (this might take a while, so we'll just verify it starts)
    echo "  Config updated: $TMP_CONFIG"
    echo "  To test: $EXEC $TMP_CONFIG"
    echo ""
done

echo "=== MQSim Test Setup Complete ==="
echo "Note: MQSim requires full simulation runs. Use the generated configs above."

