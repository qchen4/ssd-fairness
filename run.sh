#!/bin/bash
set -e

# Step 1: Build the simulator
mkdir -p build
cd build
cmake ..
make -j$(nproc)
cd ..

# Step 2: Generate trace (if tools/trace_gen.py exists)
TRACE=traces/synthetic.csv
if [ -f tools/trace_gen.py ]; then
    echo "Generating synthetic trace..."
    python3 tools/trace_gen.py --processes 4 --requests 1000 --output "$TRACE"
fi

# Step 3: Run the simulator
echo "Running simulation..."
./build/ssd-fairness "$TRACE"

# Step 4: Plot results (if plot_results.py exists)
RESULTS_FILE=build/results.csv
if [ -f tools/plot_results.py ]; then
    echo "Plotting results..."
    if grep -q "process_id" "$RESULTS_FILE" 2>/dev/null; then
        python3 tools/plot_results.py "$RESULTS_FILE"
    else
        echo "Skipping plot: $RESULTS_FILE does not contain per-request data."
    fi
fi
