#!/bin/bash
# Quick script to check job status and show completion info

JOB_ID=${1:-3962274}

echo "Checking job status for job $JOB_ID..."
echo ""

# Check if job is still in queue
if squeue -j $JOB_ID &>/dev/null; then
    echo "Status: Job is still RUNNING"
    echo ""
    squeue -j $JOB_ID -o "%.18i %.9P %.8j %.8u %.2t %.10M %.6D %R"
    echo ""
    echo "To monitor progress: tail -f mqsim_experiments_${JOB_ID}.out"
else
    echo "Status: Job is NOT in queue (completed or failed)"
    echo ""
    
    # Check output file for completion message
    if [ -f "mqsim_experiments_${JOB_ID}.out" ]; then
        echo "=== Last 10 lines of output ==="
        tail -10 "mqsim_experiments_${JOB_ID}.out"
        echo ""
        
        if grep -q "All steps completed\|Job completed" "mqsim_experiments_${JOB_ID}.out" 2>/dev/null; then
            echo "✅ Job appears to have completed successfully!"
        fi
    fi
    
    # Check for errors
    if [ -f "mqsim_experiments_${JOB_ID}.err" ]; then
        ERROR_COUNT=$(grep -i "error\|fatal\|failed" "mqsim_experiments_${JOB_ID}.err" | wc -l)
        if [ "$ERROR_COUNT" -gt 0 ]; then
            echo "⚠️  Found $ERROR_COUNT potential errors in error log"
            echo "   Check: mqsim_experiments_${JOB_ID}.err"
        fi
    fi
    
    # Check for results
    LATEST_RESULTS=$(ls -td results/20* 2>/dev/null | head -1)
    if [ -n "$LATEST_RESULTS" ]; then
        echo ""
        echo "📁 Latest results directory: $LATEST_RESULTS"
        
        # Check for visualizations
        if [ -d "${LATEST_RESULTS}/visualizations" ] || [ -d "${LATEST_RESULTS}/fairness_visualizations" ]; then
            echo "✅ Visualizations found!"
            if [ -d "${LATEST_RESULTS}/visualizations" ]; then
                echo "   - Performance: ${LATEST_RESULTS}/visualizations"
            fi
            if [ -d "${LATEST_RESULTS}/fairness_visualizations" ]; then
                echo "   - Fairness: ${LATEST_RESULTS}/fairness_visualizations"
            fi
        fi
    fi
fi

