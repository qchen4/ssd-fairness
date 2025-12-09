# Testing Guide for Implemented Schedulers

This guide explains how to test the newly implemented scheduling algorithms.

## Quick Test

Run the automated test script:

```bash
./test_implementations.sh
```

This will:
1. Build the Lightweight Simulator
2. Run unit tests
3. Test each scheduler with a sample trace
4. Build and test MQSim (if available)

## Manual Testing

### Lightweight Simulator

#### 1. Build and Run Unit Tests

```bash
cd Lightweight_Simulator
mkdir -p build
cd build
cmake ..
make -j$(nproc)
./ssd-fairness-tests
```

#### 2. Test Individual Schedulers

```bash
# Test Round Robin
./build/ssd-fairness --trace traces/test_trace.csv --scheduler rr --results results/rr_test.csv

# Test Deficit Round Robin
./build/ssd-fairness --trace traces/test_trace.csv --scheduler drr --quantum 4096 --results results/drr_test.csv

# Test MINMAX
./build/ssd-fairness --trace traces/test_trace.csv --scheduler minmax --results results/minmax_test.csv

# Test QFQ (existing)
./build/ssd-fairness --trace traces/test_trace.csv --scheduler qfq --results results/qfq_test.csv
```

#### 3. Compare Results

```bash
# View results
cat results/rr_test.csv
cat results/drr_test.csv
cat results/minmax_test.csv
```

### MQSim

#### 1. Build MQSim

```bash
cd MQSim
make
```

#### 2. Test RR Scheduler

Edit `ssdconfig.xml` and set:
```xml
<Transaction_Scheduling_Policy>RR</Transaction_Scheduling_Policy>
```

Then run:
```bash
./MQSim -i ssdconfig.xml -w workload.xml
```

#### 3. Test DRR Scheduler

Edit `ssdconfig.xml` and set:
```xml
<Transaction_Scheduling_Policy>DRR</Transaction_Scheduling_Policy>
```

Then run:
```bash
./MQSim -i ssdconfig.xml -w workload.xml
```

## Expected Behavior

### Round Robin (RR)
- Cycles through active flows in fixed order
- Each flow gets one transaction per turn
- Fair at request level, not byte level

### Deficit Round Robin (DRR)
- Provides byte-level fairness
- Larger requests consume more deficit
- Supports per-flow weights via `--weights` option

### MINMAX
- Selects flow with minimum `(service + 1.0) / weight` ratio
- Minimizes worst-case slowdown disparity
- Supports per-flow weights

## Verification Checklist

- [ ] Unit tests pass
- [ ] All schedulers run without errors
- [ ] Results CSV files are generated
- [ ] Fairness metrics are reasonable (Jain's index > 0.9 for equal workloads)
- [ ] MQSim compiles with new schedulers
- [ ] MQSim runs with RR and DRR policies

## Troubleshooting

### Lightweight Simulator Issues

**Build errors:**
- Ensure C++17 compiler is available
- Check that all source files are present

**Scheduler not found:**
- Verify scheduler name matches exactly: `rr`, `drr`, `minmax`
- Check `scheduler_factory.cpp` includes the new schedulers

### MQSim Issues

**Unknown scheduling policy:**
- Verify `TSU_Base.h` enum includes `RR` and `DRR`
- Check `Device_Parameter_Set.cpp` parses "RR" and "DRR"
- Ensure XML config uses exact string: `RR` or `DRR`

**Link errors:**
- Ensure `TSU_RR.cpp` and `TSU_DRR.cpp` are compiled
- Check `SSD_Device.cpp` includes the headers

## Next Steps

After successful testing:
1. Run with realistic workloads
2. Compare fairness metrics across schedulers
3. Validate cross-simulator consistency
4. Proceed with BFQ-Lite and FLIN implementation

