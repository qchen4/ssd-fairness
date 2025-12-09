#!/usr/bin/env bash
# Quick progress checker for MQSim SLURM jobs

# Find latest results directory
LATEST_RESULTS=$(ls -td results/20* 2>/dev/null | head -1)

if [ -z "$LATEST_RESULTS" ]; then
    echo "No results directory found!"
    exit 1
fi

# Find latest output file
LATEST_OUT=$(ls -t mqsim_experiments_*.out 2>/dev/null | head -1)

echo "=========================================="
echo "MQSim Experiment Progress"
echo "=========================================="
echo "Results directory: $LATEST_RESULTS"
echo "Output file: $LATEST_OUT"
echo ""

# Count completed experiments
COMPLETED=$(find "$LATEST_RESULTS" -name "run.log" 2>/dev/null | wc -l)
EXPECTED=70  # 14 workloads × 5 schedulers
PERCENT=$(echo "scale=1; $COMPLETED*100/$EXPECTED" | bc 2>/dev/null || echo "0")

echo "Overall Progress: $COMPLETED/$EXPECTED experiments ($PERCENT%)"
echo ""

# Progress by scheduler
echo "Progress by Scheduler:"
for sched in RR DRR QFQ MINMAX FLIN; do
    COUNT=$(find "$LATEST_RESULTS" -path "*/${sched}/*/run.log" 2>/dev/null | wc -l)
    echo "  $sched: $COUNT/14"
done
echo ""

# Latest activity
if [ -n "$LATEST_OUT" ]; then
    echo "Latest Activity:"
    tail -3 "$LATEST_OUT" | sed 's/^/  /'
    echo ""
    
    # Current experiment (if any)
    CURRENT=$(tail -20 "$LATEST_OUT" | grep -E "^===" | tail -1)
    if [ -n "$CURRENT" ]; then
        echo "Current: $CURRENT"
    fi
fi

echo "=========================================="

