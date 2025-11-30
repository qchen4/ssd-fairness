#!/bin/bash
set -e

# Step 1: Build the simulator
mkdir -p build
cd build
cmake ..
make -j$(nproc)
cd ..

# Step 2: Generate a fresh demo trace (optional)
TRACE=${TRACE:-traces/small_mixed.csv}
if [ -f scripts/generate_traces.py ]; then
    echo "Generating demo trace..."
    python3 scripts/generate_traces.py --output-dir traces --workloads small_mixed
fi

# Step 3: Run the simulator
echo "Running simulation..."
./build/ssd-fairness --trace "$TRACE" --scheduler qfq --results results/demo.csv

# Step 4: Plot results (if plot_results.py exists)
RESULTS_FILE=results/demo.csv
if [ -f tools/plot_results.py ]; then
    echo "Plotting results..."
    if grep -q "process_id" "$RESULTS_FILE" 2>/dev/null; then
        python3 tools/plot_results.py "$RESULTS_FILE"
    else
        echo "Skipping plot: $RESULTS_FILE does not contain per-request data."
    fi
fi
