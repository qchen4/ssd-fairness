#!/bin/bash
# Comprehensive results checking script

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║              MQSim Results Summary                           ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# Find latest results directory
LATEST=$(ls -td results/20* 2>/dev/null | head -1)

if [ -z "$LATEST" ]; then
    echo "❌ No results directory found!"
    exit 1
fi

echo "📁 Latest Results: $LATEST"
echo ""

# Count schedulers
SCHEDULERS=$(ls -d "$LATEST"/*/ 2>/dev/null | xargs -n1 basename)
SCHED_COUNT=$(echo "$SCHEDULERS" | wc -l)

echo "📊 Schedulers Completed: $SCHED_COUNT / 5"
echo "   Schedulers: $(echo $SCHEDULERS | tr '\n' ' ')"
echo ""

# Expected schedulers
EXPECTED=("RR" "DRR" "QFQ" "MINMAX" "FLIN")
MISSING=()

for sched in "${EXPECTED[@]}"; do
    if [ ! -d "$LATEST/$sched" ]; then
        MISSING+=("$sched")
    fi
done

if [ ${#MISSING[@]} -gt 0 ]; then
    echo "⚠️  Missing schedulers: ${MISSING[*]}"
    echo ""
fi

# Count workloads per scheduler
echo "📋 Workloads per Scheduler:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
for sched_dir in "$LATEST"/*/; do
    if [ -d "$sched_dir" ]; then
        sched=$(basename "$sched_dir")
        workload_count=$(ls -d "$sched_dir"/*/ 2>/dev/null | wc -l)
        echo "   $sched: $workload_count workloads"
        
        # List workloads
        for wl_dir in "$sched_dir"/*/; do
            if [ -d "$wl_dir" ]; then
                wl=$(basename "$wl_dir")
                # Check for result files
                has_xml=$(find "$wl_dir" -name "*.xml" | wc -l)
                has_log=$(test -f "$wl_dir/run.log" && echo "1" || echo "0")
                status=""
                if [ "$has_xml" -gt 0 ] || [ "$has_log" = "1" ]; then
                    status="✓"
                else
                    status="✗"
                fi
                echo "      $status $wl"
            fi
        done
    fi
done
echo ""

# Check for visualizations
echo "📈 Visualizations:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ -d "$LATEST/visualizations" ]; then
    viz_count=$(find "$LATEST/visualizations" -name "*.png" | wc -l)
    echo "   ✓ Performance visualizations: $viz_count files"
    find "$LATEST/visualizations" -name "*.png" -exec basename {} \; | sed 's/^/      - /'
else
    echo "   ✗ No performance visualizations found"
fi

if [ -d "$LATEST/fairness_visualizations" ]; then
    fair_viz_count=$(find "$LATEST/fairness_visualizations" -name "*.png" | wc -l)
    echo "   ✓ Fairness visualizations: $fair_viz_count files"
    find "$LATEST/fairness_visualizations" -name "*.png" -exec basename {} \; | sed 's/^/      - /'
else
    echo "   ✗ No fairness visualizations found"
fi
echo ""

# Check for parsed results
echo "📄 Parsed Results:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ -d "$LATEST/parsed" ]; then
    csv_count=$(find "$LATEST/parsed" -name "*.csv" | wc -l)
    echo "   ✓ CSV files: $csv_count"
    find "$LATEST/parsed" -name "*.csv" -exec basename {} \; | sed 's/^/      - /'
else
    echo "   ✗ No parsed results found"
fi

if [ -d "$LATEST/fairness" ]; then
    fair_csv_count=$(find "$LATEST/fairness" -name "*.csv" | wc -l)
    echo "   ✓ Fairness CSV files: $fair_csv_count"
    find "$LATEST/fairness" -name "*.csv" -exec basename {} \; | sed 's/^/      - /'
else
    echo "   ✗ No fairness analysis found"
fi
echo ""

# Summary
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                      Summary                                 ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "Results location: $LATEST"
echo ""

if [ ${#MISSING[@]} -eq 0 ]; then
    echo "✅ All 5 schedulers completed!"
else
    echo "⚠️  Only $SCHED_COUNT / 5 schedulers completed"
    echo "   Missing: ${MISSING[*]}"
    echo ""
    echo "💡 To complete all experiments, rerun:"
    echo "   sbatch run_experiments.slurm"
fi

echo ""
echo "📂 To view results:"
echo "   cd $LATEST"
echo "   ls -R"
echo ""

