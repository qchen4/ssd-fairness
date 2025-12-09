#!/bin/bash
# Test script for all schedulers in Lightweight Simulator

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LW_DIR="$PROJECT_ROOT/Lightweight_Simulator"
BUILD_DIR="$LW_DIR/build"
EXEC="$BUILD_DIR/ssd-fairness"

# Test trace
TEST_TRACE="$LW_DIR/test_data/traces/high_vs_low.csv"
if [ ! -f "$TEST_TRACE" ]; then
    # Create a simple test trace
    TEST_TRACE="/tmp/test_trace.csv"
    cat > "$TEST_TRACE" << 'EOF'
timestamp,process_id,user_id,type,address,size
0,proc0,0,READ,0x0,4096
1000,proc1,1,READ,0x1000,4096
2000,proc2,2,READ,0x2000,8192
3000,proc0,0,WRITE,0x4000,4096
4000,proc1,1,READ,0x5000,4096
EOF
fi

RESULTS_DIR="/tmp/scheduler_tests"
mkdir -p "$RESULTS_DIR"

echo "=== Testing Lightweight Simulator Schedulers ==="
echo ""

# List of schedulers to test
SCHEDULERS=("fifo" "rr" "drr" "qfq" "minmax" "bfq" "flin")

for sched in "${SCHEDULERS[@]}"; do
    echo "Testing scheduler: $sched"
    
    OUTPUT="$RESULTS_DIR/${sched}_results.csv"
    
    if [ "$sched" == "drr" ]; then
        # DRR needs quantum
        if [ -f "$EXEC" ]; then
            "$EXEC" --trace "$TEST_TRACE" --scheduler "$sched" --quantum 4096 --results "$OUTPUT" 2>&1 | head -5
        else
            echo "  ERROR: Executable not found at $EXEC"
        fi
    else
        if [ -f "$EXEC" ]; then
            "$EXEC" --trace "$TEST_TRACE" --scheduler "$sched" --results "$OUTPUT" 2>&1 | head -5
        else
            echo "  ERROR: Executable not found at $EXEC"
        fi
    fi
    
    if [ -f "$OUTPUT" ]; then
        echo "  ✓ Results saved to $OUTPUT"
        echo "  First few lines:"
        head -3 "$OUTPUT" | sed 's/^/    /'
    else
        echo "  ✗ No output file generated"
    fi
    echo ""
done

echo "=== Test Summary ==="
echo "Results directory: $RESULTS_DIR"
ls -lh "$RESULTS_DIR" 2>/dev/null | tail -10 || echo "No results found"

