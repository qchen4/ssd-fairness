# SSD Fairness Scheduling Algorithms

Implementation of six scheduling algorithms for SSD fairness evaluation in both Lightweight Simulator and MQSim.

## Algorithms Implemented

1. **Round Robin (RR)** - Request-level round-robin scheduling
2. **Deficit Round Robin (DRR)** - Byte-level fairness with deficit counters
3. **Quick Fair Queueing (QFQ)** - Weighted fair queueing approximation
4. **MINMAX** - Minimizes worst-case slowdown disparity
5. **BFQ-Lite** - Budget-based proportional scheduling
6. **FLIN** - Slowdown-aware fairness scheduler

## Project Structure

```
ssd-fairness/
├── Lightweight_Simulator/    # C++17 lightweight simulator
├── MQSim/                     # MQSim SSD simulator
├── include/                   # Shared headers
├── docs/                      # Documentation
├── scripts/                   # Test and utility scripts
└── README.md                  # This file
```

## Quick Start

### Lightweight Simulator

```bash
cd Lightweight_Simulator/build
make
./ssd-fairness --trace ../test_data/traces/high_vs_low.csv --scheduler minmax
```

### MQSim

```bash
cd MQSim
make
./MQSim -i ssdconfig.xml -w workload.xml
```

Edit `ssdconfig.xml` to set `<Transaction_Scheduling_Policy>` to one of:
- `RR`, `DRR`, `QFQ`, `MINMAX`, `BFQ_LITE`, `FLIN`

## Testing

Run automated tests:
```bash
./scripts/test_all_schedulers.sh
```

## Documentation

See `docs/README.md` for complete documentation index.

**Key Documents:**
- `STATUS_REPORT.md` - Current implementation status
- `PERFORMANCE_EVALUATION.md` - Test results and analysis
- `IMPLEMENTATION_COMPLETE.md` - Detailed completion report

## Status

✅ **Implementation:** 100% Complete  
✅ **Lightweight Simulator Testing:** Complete  
⏳ **MQSim Testing:** Pending build completion  
⚠️ **Known Issue:** BFQ-Lite throughput needs optimization

## Citation

If you use this code, please cite the original papers for the algorithms and simulators.

