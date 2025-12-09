# SSD Fairness Scheduling Algorithms

Implementation of five scheduling algorithms for SSD fairness evaluation in both Lightweight Simulator and MQSim.

## Algorithms

1. **Round Robin (RR)** - Request-level round-robin scheduling
2. **Deficit Round Robin (DRR)** - Byte-level fairness with deficit counters
3. **Quick Fair Queueing (QFQ)** - Weighted fair queueing approximation
4. **MINMAX** - Minimizes worst-case slowdown disparity
5. **FLIN** - Slowdown-aware fairness scheduler

## Project Structure

- [Lightweight_Simulator/](Lightweight_Simulator/) - C++17 lightweight simulator
  - `include/` - Simulator headers
  - `experiments/` - Experiment results and traces
- [MQSim/](MQSim/) - MQSim SSD simulator
- [docs/](docs/) - Documentation
- [scripts/](scripts/) - Test and utility scripts (integration tests for both simulators)
- [README.md](README.md) - This file

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
- `RR`, `DRR`, `QFQ`, `MINMAX`, `FLIN`

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
✅ **MQSim:** 5/5 schedulers implemented (RR, DRR, QFQ, FLIN, MINMAX)  
✅ **Build:** Both simulators build successfully  
✅ **Testing:** All schedulers tested and verified  
✅ **Results:** Fairness analysis complete with visualizations

## Latest Results

### Fairness Performance (MQSim)
- **Standard Workloads:** All schedulers achieve perfect fairness (Jain's Index = 1.0000)
- **Under Contention:** MINMAX achieves best fairness (0.4597 vs 0.4269 for others)
- **Average Fairness:** MINMAX leads with 0.8649, others at 0.8567

### Latency Performance
- **Standard Workloads:** 175μs average latency (all schedulers)
- **Contention Workloads:** 183μs average latency (all schedulers)
- **100% Request Completion:** All schedulers achieve perfect completion rates

See [MQSim/FAIRNESS_RESULTS.md](MQSim/FAIRNESS_RESULTS.md) and [MQSim/RESULTS_DESCRIPTION.md](MQSim/RESULTS_DESCRIPTION.md) for detailed analysis.

## Citation

If you use this code, please cite the original papers for the algorithms and simulators.

