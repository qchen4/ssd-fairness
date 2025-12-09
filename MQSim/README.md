# MQSim: SSD Fairness Scheduling Framework

This repository contains an enhanced version of MQSim with implementations of five fairness-aware scheduling algorithms for SSD evaluation. MQSim is a simulator that accurately captures the behavior of both modern multi-queue SSDs (NVMe) and conventional SATA-based SSDs.

## Table of Contents

- [Overview](#overview)
- [Project Structure](#project-structure)
- [Implemented Schedulers](#implemented-schedulers)
- [Quick Start](#quick-start)
- [Building](#building)
- [Running Experiments](#running-experiments)
- [Analysis Tools](#analysis-tools)
- [Configuration](#configuration)
- [Documentation](#documentation)
- [Citation](#citation)

## Overview

This project extends MQSim with five fairness-aware scheduling algorithms:

1. **Round Robin (RR)** - Request-level round-robin scheduling
2. **Deficit Round Robin (DRR)** - Byte-level fairness with deficit counters
3. **Quick Fair Queueing (QFQ)** - Weighted fair queueing approximation
4. **MINMAX** - Minimizes worst-case slowdown disparity
5. **FLIN** - Slowdown-aware fairness scheduler

All schedulers are fully integrated into MQSim and can be selected via the SSD configuration XML file.

## Project Structure

```
MQSim/
├── src/                    # Source code
│   ├── ssd/               # SSD components (schedulers in TSU_*.h/cpp)
│   ├── host/              # Host interface components
│   ├── nvm_chip/          # NAND flash memory models
│   ├── sim/               # Simulation engine
│   └── exec/              # Execution and device models
├── scripts/               # Shell scripts for experiments
│   ├── run_experiments.sh          # Main experiment runner
│   ├── run_experiments_with_viz.sh # Full workflow with visualization
│   ├── run_experiments_resume.sh   # Resume incomplete experiments
│   ├── test_schedulers.sh          # Quick scheduler tests
│   └── *.slurm            # SLURM job submission scripts
├── tools/                 # Python analysis and visualization tools
│   ├── parse_results.py              # Parse MQSim XML outputs
│   ├── analyze_fairness.py           # Calculate fairness metrics
│   ├── create_visualizations.py      # Generate performance plots
│   ├── create_fairness_visualizations.py  # Generate fairness plots
│   └── summarize_results.py          # Generate summary reports
├── configs/               # SSD configuration files
│   └── ssdconfig.xml      # Main SSD configuration template
├── workloads/             # Workload definition files
│   ├── workload_scenario_1.xml       # Write-heavy synthetic
│   ├── workload_scenario_2.xml       # Read-dominated synthetic
│   ├── workload_scenario_3.xml       # Mixed trace-based
│   └── workload_stress_*.xml         # Stress test workloads
├── results/               # Experiment results (generated)
│   └── <timestamp>/       # Timestamped experiment runs
│       └── <scheduler>/   # Results per scheduler
│           └── <workload>/ # Results per workload
├── docs/                  # Documentation
│   ├── README.md                    # This file
│   ├── RESULTS_DESCRIPTION.md       # Detailed results analysis
│   ├── EXPERIMENT_SETUP.md          # Experiment setup guide
│   └── *.md                         # Additional documentation
├── logs/                  # Log files from experiments
├── archives/              # Archived results (zip files)
├── traces/                # I/O trace files
├── fast18/                # FAST'18 artifact workloads
├── visualizations/        # Generated visualization outputs
├── fairness_visualizations/ # Generated fairness plots
├── build/                 # Build artifacts
├── Makefile               # Build configuration
└── MQSim                  # Compiled executable (after build)
```

## Implemented Schedulers

All schedulers are implemented in `src/ssd/`:

| Scheduler | Files | Description |
|-----------|-------|-------------|
| **RR** | `TSU_RR.h/cpp` | Round-robin scheduling at request level |
| **DRR** | `TSU_DRR.h/cpp` | Deficit Round Robin for byte-level fairness |
| **QFQ** | `TSU_QFQ.h/cpp` | Quick Fair Queueing with weighted fairness |
| **MINMAX** | `TSU_MinMax.h/cpp` | Min-max fairness to minimize slowdown disparity |
| **FLIN** | `TSU_FLIN.h/cpp` | Fairness via Latency Interference Neutralization |
| OUT_OF_ORDER | `TSU_OutofOrder.h/cpp` | Baseline out-of-order scheduler |
| PRIORITY_OUT_OF_ORDER | `TSU_Priority_OutOfOrder.h/cpp` | Priority-aware out-of-order |

To use a scheduler, set `<Transaction_Scheduling_Policy>` in `configs/ssdconfig.xml` to one of: `RR`, `DRR`, `QFQ`, `MINMAX`, `FLIN`, `OUT_OF_ORDER`, or `PRIORITY_OUT_OF_ORDER`.

## Quick Start

### Building MQSim

```bash
cd MQSim
make
```

This will compile the MQSim executable in the current directory.

### Running a Single Simulation

```bash
./MQSim -i configs/ssdconfig.xml -w workloads/workload_scenario_1.xml
```

### Testing All Schedulers

```bash
bash scripts/test_schedulers.sh
```

This runs a quick test of all schedulers to verify they compile and run correctly.

## Running Experiments

### Experiment Configuration

The experiment suite evaluates **5 scheduling policies** across **14 workloads**:

#### Scheduling Policies (5 total)
1. **RR** - Round Robin
2. **DRR** - Deficit Round Robin
3. **QFQ** - Quick Fair Queueing
4. **MINMAX** - Min-Max Fairness
5. **FLIN** - Fairness via Latency Interference Neutralization

#### Workloads (14 total)

**Standard Synthetic Workloads:**
1. `workloads/workload_scenario_1.xml` - Write-heavy synthetic stress (two NVMe flows)
2. `workloads/workload_scenario_2.xml` - Read-dominated synthetic workload for latency sensitivity
3. `workloads/workload_scenario_3.xml` - Mixed synthetic workload with random uniform address distribution

**FAST'18 Backend Contention Workloads:**
4. `fast18/backend-contention/workload-backend-contention-flow-1-flow-2.xml` - Two-flow backend contention study
5. `fast18/backend-contention/workload-backend-contention-flow-1.xml` - Single flow 1
6. `fast18/backend-contention/workload-backend-contention-flow-2.xml` - Single flow 2

**FAST'18 Data Cache Contention Workloads:**
7. `fast18/data-cache-contention/workload-datacache-contention-flow-1.xml` - Single flow 1
8. `fast18/data-cache-contention/workload-datacache-contention-flow-2.xml` - Single flow 2

**FAST'18 Queue Fetch Size Workloads:**
9. `fast18/queue-fetch-size/workload-queue-fetch-size-flow-1-flow-2.xml` - Two-flow study
10. `fast18/queue-fetch-size/workload-queue-fetch-size-flow-1.xml` - Single flow 1
11. `fast18/queue-fetch-size/workload-queue-fetch-size-flow-2.xml` - Single flow 2

**Stress Test Workloads:**
12. `workloads/workload_stress_bully_victim.xml` - Bully-victim fairness stress test
13. `workloads/workload_stress_multiqueue.xml` - Multi-queue contention stress test
14. `workloads/workload_stress_rw_interference.xml` - Read-write interference stress test

**Total Experiments:** 5 schedulers × 14 workloads = **70 experiment runs**

### Parallel Execution on PACE ICE

When running on PACE ICE (or any SLURM cluster), experiments are executed in parallel for efficiency:

#### Execution Strategy
- **Per-Scheduler Parallelization**: For each scheduler, workloads run in parallel
- **Parallel Workload Limit**: Up to 16 workloads run simultaneously (configurable via `WORKLOAD_JOBS`)
- **Sequential Scheduler Execution**: Schedulers run sequentially to avoid resource contention

#### PACE ICE Configuration
The SLURM scripts are configured for PACE ICE:
- **Partition**: `ice-cpu`
- **CPUs per task**: 16
- **Memory**: 48GB
- **Time limit**: 8 hours
- **Parallel workloads**: 16 (one per CPU core)

#### Execution Flow
```
For each scheduler (RR, DRR, QFQ, MINMAX, FLIN):
  ├─ Launch up to 16 workloads in parallel
  ├─ Wait for all workloads to complete
  └─ Move to next scheduler

Total: 5 scheduler iterations × 14 workloads = 70 experiments
```

#### Example Timeline
- **Sequential execution**: ~70 × average_simulation_time
- **Parallel execution (16 cores)**: ~5 × (14/16) × average_simulation_time ≈ **4.4× faster**

### Basic Experiment Suite

Run all schedulers across all workloads:

```bash
bash scripts/run_experiments.sh
```

This will:
- Compile MQSim if needed
- Run all 5 schedulers (RR, DRR, QFQ, MINMAX, FLIN) across all 14 workloads
- Execute workloads in parallel (default: 1, set `WORKLOAD_JOBS=16` for parallel execution)
- Store results in `results/<timestamp>/<scheduler>/<workload>/`
- Generate a summary CSV file
- Archive results in `results/<timestamp>.zip`

### Full Workflow with Analysis

Run experiments and generate visualizations:

```bash
bash scripts/run_experiments_with_viz.sh
```

This performs:
1. Runs all experiments
2. Parses XML results into structured data
3. Analyzes fairness metrics (Jain's index, per-flow statistics)
4. Generates performance visualizations
5. Generates fairness visualizations

### Resuming Incomplete Experiments

If experiments were interrupted, resume from an existing results directory:

```bash
bash scripts/run_experiments_resume.sh results/20251208-215310
```

This will skip completed experiments and only run missing ones.

### Running on PACE ICE (SLURM)

Submit jobs to PACE ICE cluster:

```bash
# Basic experiments (parallel execution with 16 cores)
sbatch scripts/run_experiments.slurm

# Full workflow with visualizations (parallel execution + analysis)
sbatch scripts/run_experiments_with_viz.slurm

# Resume incomplete experiments
# (Edit EXISTING_RESULTS path in the script first)
sbatch scripts/run_experiments_resume.slurm
```

**PACE ICE SLURM Configuration:**
- **Partition**: `ice-cpu`
- **CPUs**: 16 (enables parallel execution of 16 workloads)
- **Memory**: 48GB
- **Time**: 8 hours
- **Parallel Workloads**: 16 (set via `WORKLOAD_JOBS=16`)

The SLURM scripts automatically configure parallel execution. Each scheduler's workloads run in parallel (up to 16 at a time), while schedulers run sequentially. This maximizes CPU utilization while maintaining organized result storage.

**Expected Runtime:**
- Sequential: ~70 × simulation_time (e.g., 70 × 5 min = 5.8 hours)
- Parallel (16 cores): ~5 × (14/16) × simulation_time (e.g., 5 × 0.875 × 5 min = 22 min)
- **Speedup**: ~4.4× faster with 16 parallel workloads

## Analysis Tools

### Parse Results

Convert MQSim XML outputs to structured CSV:

```bash
python3 tools/parse_results.py results/<timestamp> results/<timestamp>/parsed
```

### Analyze Fairness

Calculate fairness metrics (Jain's index, per-flow statistics):

```bash
python3 tools/analyze_fairness.py results/<timestamp> results/<timestamp>/fairness
```

### Generate Visualizations

Create performance plots:

```bash
python3 tools/create_visualizations.py results/<timestamp>/parsed results/<timestamp>/visualizations
```

Create fairness plots:

```bash
python3 tools/create_fairness_visualizations.py results/<timestamp>/fairness results/<timestamp>/fairness_visualizations
```

### Generate Summary

Create a summary CSV of all results:

```bash
python3 tools/summarize_results.py --root results/<timestamp>
```

## Configuration

### SSD Configuration

Edit `configs/ssdconfig.xml` to configure:
- **Transaction_Scheduling_Policy**: Set to `RR`, `DRR`, `QFQ`, `MINMAX`, or `FLIN`
- SSD device parameters (channels, chips, dies, planes)
- Flash memory characteristics
- Host interface settings (NVMe/SATA)
- Garbage collection policies

### Workload Configuration

Workloads are defined in XML files in `workloads/`. Each workload can specify:
- Trace-based I/O flows (from files in `traces/`)
- Synthetic I/O flows (bandwidth, request size, address distribution)
- Multiple concurrent flows
- Priority classes

See the MQSim documentation in `docs/README.md` for detailed configuration options.

### Experiment Configuration

Edit `scripts/run_experiments.sh` to:
- Modify the `WORKLOADS` array to add/remove workloads
- Modify the `POLICIES` array to test different schedulers
- Adjust `WORKLOAD_JOBS` environment variable for parallel execution

## Documentation

- **[README.md](docs/README.md)** - Original MQSim documentation with full configuration reference
- **[RESULTS_DESCRIPTION.md](docs/RESULTS_DESCRIPTION.md)** - Detailed analysis of experiment results
- **[EXPERIMENT_SETUP.md](docs/EXPERIMENT_SETUP.md)** - Guide for setting up experiments
- **[RESULTS_CHECKING_GUIDE.md](docs/RESULTS_CHECKING_GUIDE.md)** - How to verify experiment results
- **[VISUALIZATIONS_SUMMARY.md](docs/VISUALIZATIONS_SUMMARY.md)** - Overview of generated visualizations

## Results

### Key Findings

Based on comprehensive testing across multiple workloads:

- **Latency Performance**: All fairness-aware schedulers achieve similar latency to baseline schedulers (~175μs for standard workloads, ~183μs under contention)
- **Fairness**: MINMAX achieves the best fairness metrics (Jain's Index = 0.8649 average) under contention scenarios
- **Request Completion**: All schedulers achieve 100% request completion across all workloads
- **Performance**: Fairness mechanisms do not significantly degrade performance

See `docs/RESULTS_DESCRIPTION.md` for detailed analysis.

## Citation

### MQSim Framework

If you use MQSim, please cite the original FAST 2018 paper:

```bibtex
@inproceedings{tavakkol2018mqsim,
  title={{MQSim: A Framework for Enabling Realistic Studies of Modern Multi-Queue SSD Devices}},
  author={Tavakkol, Arash and G{\'o}mez-Luna, Juan and Sadrosadati, Mohammad and Ghose, Saugata and Mutlu, Onur},
  booktitle={FAST},
  year={2018}
}
```

### Fairness Schedulers

If you use the fairness scheduler implementations, please cite the original papers for each algorithm:
- **RR/DRR**: Classic fair queueing algorithms
- **QFQ**: Quick Fair Queueing (see QFQ paper)
- **MINMAX**: Min-max fairness algorithms
- **FLIN**: Fairness via Latency Interference Neutralization

## Additional Resources

- **MQSim Paper**: [FAST 2018](https://people.inf.ethz.ch/omutlu/pub/MQSim-SSD-simulation-framework_fast18.pdf)
- **MQSim Slides**: [PPTX](https://people.inf.ethz.ch/omutlu/pub/MQSim-SSD-simulation-framework_fast18-talk.pptx) | [PDF](https://people.inf.ethz.ch/omutlu/pub/MQSim-SSD-simulation-framework_fast18-talk.pdf)
- **MQSim Talk**: [YouTube](http://www.youtube.com/watch?v=d40ekgmjM98)

## License

See [LICENSE](LICENSE) file for details.

## Support

For issues related to:
- **MQSim framework**: Refer to the original MQSim repository
- **Fairness schedulers**: Check implementation files in `src/ssd/TSU_*.h/cpp`
- **Experiments/scripts**: See documentation in `docs/` directory

