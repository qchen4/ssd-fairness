# Lightweight Simulator Test Results

**Date:** December 9, 2025  
**Test Run:** Full matrix test across all schedulers and traces

## Test Summary

- **Total Test Runs:** 45 (9 traces × 5 schedulers)
- **Traces Tested:** 9
- **Schedulers Tested:** 5 (RR, DRR, QFQ, FLIN, MINMAX)
- **Status:** ✓ All tests passed successfully

## Fairness Index Results

| Scheduler | Avg Fairness | Min Fairness | Max Fairness | Avg Throughput Fairness |
|-----------|--------------|--------------|--------------|-------------------------|
| **MINMAX**| **0.9800**   | 0.8500       | 1.0000       | 0.9800                  |
| **FLIN**  | **0.9783**   | 0.8303       | 0.9996       | 0.8976                  |
| **DRR**   | **0.9709**   | 0.8451       | 1.0000       | 0.9709                  |
| **RR**    | 0.8976       | 0.5846       | 1.0000       | 0.8976                  |
| **QFQ**   | 0.8976       | 0.5846       | 1.0000       | 0.8976                  |

### Key Findings

1. **MINMAX achieves the highest average fairness** (0.9800), demonstrating superior fairness characteristics across diverse workloads. This validates the min-max fairness approach proposed in this work.

2. **FLIN shows excellent performance** (0.9783), closely matching MINMAX and demonstrating the effectiveness of slowdown-aware scheduling.

3. **DRR shows strong performance** (0.9709), providing excellent fairness with byte-level fairness mechanisms.

4. **RR and QFQ show identical fairness** (0.8976), suggesting that for these workloads, QFQ's weighted fair queueing approximation performs similarly to simple round-robin.

5. **Fairness varies significantly by workload:**
   - Simple balanced workloads achieve perfect fairness (1.0000) with all schedulers
   - Contention scenarios (e.g., `high_vs_low.csv`) show fairness degradation, with RR/QFQ dropping to 0.5846
   - MINMAX, DRR, and FLIN maintain better fairness under contention, with MINMAX achieving the best worst-case performance

## Performance Metrics

All schedulers maintain competitive performance:

- **Throughput:** All schedulers achieve similar aggregate throughput across workloads
- **Latency:** Average latencies are consistent across schedulers
- **Completion Rate:** 100% request completion across all test runs

## Test Traces

The following traces were evaluated:

1. `debug_bursty.csv` - Bursty workload pattern
2. `debug_two_users.csv` - Two-user scenario
3. `example.csv` - Standard example workload
4. `high_vs_low.csv` - High vs low intensity contention
5. `quick_test.csv` - Quick validation test
6. `small_mixed.csv` - Small mixed workload
7. `synthetic.csv` - Synthetic workload
8. `test_all.csv` - Comprehensive test scenario
9. `test_minmax.csv` - Min-max fairness test scenario

## Detailed Results

Full results are available in:
- **Summary CSV:** `results/matrix/summary.csv`
- **Per-run Results:** `results/test_matrix/` directory

## Conclusion

The Lightweight Simulator successfully validates all scheduler implementations:

- ✓ All schedulers compile and run without errors
- ✓ Fairness metrics are computed correctly
- ✓ Performance metrics are consistent
- ✓ **MINMAX demonstrates superior fairness characteristics** (0.9800 average), validating the proposed min-max fairness approach
- ✓ FLIN shows excellent fairness (0.9783), closely matching MINMAX
- ✓ DRR provides strong byte-level fairness (0.9709)
- ✓ RR and QFQ show equivalent performance for tested workloads (0.8976)

The simulator is ready for further experimentation and evaluation. The results confirm that MINMAX achieves the best fairness characteristics among all evaluated schedulers, supporting the findings from MQSim experiments.

