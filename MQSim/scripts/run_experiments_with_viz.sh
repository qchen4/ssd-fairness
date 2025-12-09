#!/usr/bin/env bash

# Complete workflow: Run experiments, parse results, analyze fairness, and generate visualizations

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MQSIM_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${MQSIM_ROOT}"

# Run the experiments
echo "=========================================="
echo "Step 1: Running MQSim experiments"
echo "=========================================="
bash scripts/run_experiments.sh

# Find the most recent results directory
LATEST_RESULTS=$(ls -td results/20* 2>/dev/null | head -1)

if [ -z "$LATEST_RESULTS" ]; then
    echo "ERROR: No results directory found!"
    exit 1
fi

echo ""
echo "Results directory: $LATEST_RESULTS"
echo ""

# Step 2: Parse results
echo "=========================================="
echo "Step 2: Parsing MQSim results"
echo "=========================================="

PARSED_DIR="${LATEST_RESULTS}/parsed"
mkdir -p "$PARSED_DIR"

if [ -f "tools/parse_results.py" ]; then
    python3 tools/parse_results.py "$LATEST_RESULTS" "$PARSED_DIR" || {
        echo "Warning: parse_results.py failed, continuing..."
    }
else
    echo "Warning: parse_results.py not found, skipping parsing step"
fi

# Step 3: Analyze fairness
echo ""
echo "=========================================="
echo "Step 3: Analyzing fairness metrics"
echo "=========================================="

FAIRNESS_DIR="${LATEST_RESULTS}/fairness"
mkdir -p "$FAIRNESS_DIR"

if [ -f "tools/analyze_fairness.py" ]; then
    python3 tools/analyze_fairness.py "$LATEST_RESULTS" "$FAIRNESS_DIR" || {
        echo "Warning: analyze_fairness.py failed, continuing..."
    }
else
    echo "Warning: analyze_fairness.py not found, skipping fairness analysis"
fi

# Step 4: Generate visualizations
echo ""
echo "=========================================="
echo "Step 4: Generating visualizations"
echo "=========================================="

# Generate performance visualizations
if [ -f "tools/create_visualizations.py" ] && [ -d "$PARSED_DIR" ]; then
    VIZ_DIR="${LATEST_RESULTS}/visualizations"
    mkdir -p "$VIZ_DIR"
    python3 tools/create_visualizations.py "$PARSED_DIR" "$VIZ_DIR" || {
        echo "Warning: create_visualizations.py failed"
    }
else
    echo "Warning: create_visualizations.py not found or parsed directory missing"
fi

# Generate fairness visualizations
if [ -f "tools/create_fairness_visualizations.py" ] && [ -d "$FAIRNESS_DIR" ]; then
    FAIRNESS_VIZ_DIR="${LATEST_RESULTS}/fairness_visualizations"
    mkdir -p "$FAIRNESS_VIZ_DIR"
    python3 tools/create_fairness_visualizations.py "$FAIRNESS_DIR" "$FAIRNESS_VIZ_DIR" || {
        echo "Warning: create_fairness_visualizations.py failed"
    }
else
    echo "Warning: create_fairness_visualizations.py not found or fairness directory missing"
fi

echo ""
echo "=========================================="
echo "All steps completed!"
echo "=========================================="
echo "Results: $LATEST_RESULTS"
echo "  - Parsed results: $PARSED_DIR"
echo "  - Fairness analysis: $FAIRNESS_DIR"
echo "  - Visualizations: ${LATEST_RESULTS}/visualizations"
echo "  - Fairness visualizations: ${LATEST_RESULTS}/fairness_visualizations"
echo ""

