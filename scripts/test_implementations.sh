#!/bin/bash
# Test script for newly implemented schedulers
set -e

echo "=========================================="
echo "Testing Implemented Schedulers"
echo "=========================================="

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test Lightweight Simulator
echo -e "\n${YELLOW}Testing Lightweight Simulator${NC}"
echo "----------------------------------------"

cd Lightweight_Simulator

# Build
echo "Building simulator..."
mkdir -p build
cd build
cmake .. > /dev/null 2>&1
make -j$(nproc) > /dev/null 2>&1
cd ..

# Run unit tests
echo "Running unit tests..."
if ./build/ssd-fairness-tests > /tmp/test_output.txt 2>&1; then
    echo -e "${GREEN}✓ Unit tests passed${NC}"
    grep -E "TEST_CASE|PASSED|FAILED" /tmp/test_output.txt || true
else
    echo -e "${RED}✗ Unit tests failed${NC}"
    cat /tmp/test_output.txt
    exit 1
fi

# Test each scheduler with a simple trace
echo -e "\nTesting schedulers with sample trace..."

# Create a simple test trace if it doesn't exist
mkdir -p traces
if [ ! -f traces/test_trace.csv ]; then
    cat > traces/test_trace.csv << EOF
timestamp,process_id,user_id,type,address,size
0,proc0,0,READ,0x0,4096
1000,proc1,1,READ,0x1000,4096
2000,proc2,2,READ,0x2000,4096
3000,proc0,0,WRITE,0x3000,8192
4000,proc1,1,WRITE,0x4000,8192
EOF
fi

SCHEDULERS=("fifo" "rr" "drr" "qfq" "minmax")
for sched in "${SCHEDULERS[@]}"; do
    echo -n "  Testing $sched... "
    if ./build/ssd-fairness --trace traces/test_trace.csv --scheduler "$sched" --results /tmp/test_${sched}.csv > /dev/null 2>&1; then
        echo -e "${GREEN}✓${NC}"
    else
        echo -e "${RED}✗${NC}"
        echo "    Error running $sched scheduler"
    fi
done

cd ..

# Test MQSim (if available)
echo -e "\n${YELLOW}Testing MQSim${NC}"
echo "----------------------------------------"

if [ -d "MQSim" ] && [ -f "MQSim/Makefile" ]; then
    cd MQSim
    
    # Build MQSim
    echo "Building MQSim..."
    if make > /tmp/mqsim_build.log 2>&1; then
        echo -e "${GREEN}✓ MQSim built successfully${NC}"
    else
        echo -e "${RED}✗ MQSim build failed${NC}"
        echo "Check /tmp/mqsim_build.log for details"
        cd ..
        exit 1
    fi

    # Test schedulers (if config files exist)
    if [ -f "ssdconfig.xml" ]; then
        echo -e "\nTesting schedulers in MQSim..."
        
        # Test RR
        echo -n "  Testing RR... "
        sed -i.bak 's/<Transaction_Scheduling_Policy>.*<\/Transaction_Scheduling_Policy>/<Transaction_Scheduling_Policy>RR<\/Transaction_Scheduling_Policy>/' ssdconfig.xml
        if ./MQSim -i ssdconfig.xml -w workload.xml > /tmp/mqsim_rr.log 2>&1; then
            echo -e "${GREEN}✓${NC}"
        else
            echo -e "${RED}✗${NC}"
        fi
        mv ssdconfig.xml.bak ssdconfig.xml 2>/dev/null || true

        # Test DRR
        echo -n "  Testing DRR... "
        sed -i.bak 's/<Transaction_Scheduling_Policy>.*<\/Transaction_Scheduling_Policy>/<Transaction_Scheduling_Policy>DRR<\/Transaction_Scheduling_Policy>/' ssdconfig.xml
        if ./MQSim -i ssdconfig.xml -w workload.xml > /tmp/mqsim_drr.log 2>&1; then
            echo -e "${GREEN}✓${NC}"
        else
            echo -e "${RED}✗${NC}"
        fi
        mv ssdconfig.xml.bak ssdconfig.xml 2>/dev/null || true
    else
        echo "  No ssdconfig.xml found, skipping MQSim scheduler tests"
    fi
    
    cd ..
else
    echo "MQSim directory or Makefile not found, skipping MQSim tests"
fi

echo -e "\n${GREEN}=========================================="
echo "Testing Complete!"
echo "==========================================${NC}"

