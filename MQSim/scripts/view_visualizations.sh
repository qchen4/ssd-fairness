#!/bin/bash
# Script to help view visualizations

VIZ_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=========================================="
echo "MQSim Visualization Viewer"
echo "=========================================="
echo ""

# Check if we're on a system with display
if [ -n "$DISPLAY" ] || [ -n "$SSH_CLIENT" ]; then
    echo "Display available: $DISPLAY"
    HAS_DISPLAY=true
else
    HAS_DISPLAY=false
    echo "No display available (running on headless server)"
fi

echo ""
echo "Available Visualizations:"
echo "=========================="
echo ""

# Performance Visualizations
if [ -d "$VIZ_DIR/visualizations" ]; then
    echo "📊 Performance Visualizations:"
    echo "   Location: $VIZ_DIR/visualizations/"
    echo ""
    for img in "$VIZ_DIR/visualizations"/*.png; do
        if [ -f "$img" ]; then
            name=$(basename "$img")
            size=$(ls -lh "$img" | awk '{print $5}')
            echo "   • $name ($size)"
        fi
    done
    echo ""
fi

# Fairness Visualizations
if [ -d "$VIZ_DIR/fairness_visualizations" ]; then
    echo "⚖️  Fairness Visualizations:"
    echo "   Location: $VIZ_DIR/fairness_visualizations/"
    echo ""
    for img in "$VIZ_DIR/fairness_visualizations"/*.png; do
        if [ -f "$img" ]; then
            name=$(basename "$img")
            size=$(ls -lh "$img" | awk '{print $5}')
            echo "   • $name ($size)"
        fi
    done
    echo ""
fi

echo "=========================================="
echo "How to View:"
echo "=========================================="
echo ""
echo "1. In your IDE/File Explorer:"
echo "   - Navigate to: $VIZ_DIR/visualizations/"
echo "   - Navigate to: $VIZ_DIR/fairness_visualizations/"
echo "   - Click on any .png file to view"
echo ""
echo "2. Copy to local machine:"
echo "   scp -r $VIZ_DIR/visualizations user@local:/path/to/destination"
echo "   scp -r $VIZ_DIR/fairness_visualizations user@local:/path/to/destination"
echo ""
echo "3. Using file paths:"
echo "   Performance:"
for img in "$VIZ_DIR/visualizations"/*.png; do
    [ -f "$img" ] && echo "     $img"
done
echo "   Fairness:"
for img in "$VIZ_DIR/fairness_visualizations"/*.png; do
    [ -f "$img" ] && echo "     $img"
done
echo ""

if [ "$HAS_DISPLAY" = true ]; then
    echo "4. Open with image viewer (if available):"
    if command -v xdg-open &> /dev/null; then
        echo "   xdg-open $VIZ_DIR/visualizations/latency_comparison.png"
    elif command -v eog &> /dev/null; then
        echo "   eog $VIZ_DIR/visualizations/latency_comparison.png"
    fi
fi

echo ""
echo "=========================================="

