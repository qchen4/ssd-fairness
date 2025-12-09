# SSD Fairness Scheduling Algorithms

Implementation of five scheduling algorithms for SSD fairness evaluation in both Lightweight Simulator and MQSim.

## Algorithms

1. **Round Robin (RR)** - Request-level round-robin scheduling
2. **Deficit Round Robin (DRR)** - Byte-level fairness with deficit counters
3. **Quick Fair Queueing (QFQ)** - Weighted fair queueing approximation
4. **MINMAX** - Minimizes worst-case slowdown disparity
5. **FLIN** - Slowdown-aware fairness scheduler

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
- `QFQ`, `MINMAX`, `FLIN` (RR and DRR not yet implemented in MQSim)

## Testing

Run automated tests:
```bash
./scripts/test_all_schedulers.sh
```

## Documentation

See `docs/README.md` for complete documentation index.

**Key Documents:**
- `docs/STATUS.md` - Current implementation status
- `docs/IMPLEMENTATION.md` - Implementation details
- `docs/BUILD.md` - Build instructions

## Status

✅ **Lightweight Simulator:** 5/5 schedulers implemented  
✅ **MQSim:** 3/5 schedulers implemented (QFQ, FLIN, MINMAX)  
✅ **Build:** Both simulators build successfully  
⏳ **Pending:** RR and DRR implementation in MQSim

## Citation

If you use this code, please cite the original papers for the algorithms and simulators.

