# MQSim Fairness Experiment Setup Documentation

## Overview

This document describes the experimental setup for evaluating fairness-oriented transaction schedulers in MQSim, a simulator for modern NVMe and SATA SSDs. The experiments compare five different scheduling policies across multiple workloads to assess their fairness characteristics and performance trade-offs.

## Experiment Structure

The experiment follows a systematic approach:
1. **Configuration**: Set up SSD hardware parameters and scheduler policy
2. **Execution**: Run MQSim simulations for each scheduler-workload combination
3. **Parsing**: Extract performance metrics from simulation outputs
4. **Analysis**: Calculate fairness metrics (Jain's index, per-flow statistics)
5. **Visualization**: Generate comparative charts and summaries

## SSD Configuration

The base SSD configuration is defined in `ssdconfig.xml`. Key parameters:

### Hardware Architecture
- **Host Interface**: NVMe (4 PCIe lanes, 1 GB/s per lane)
- **Flash Technology**: MLC (Multi-Level Cell)
- **Channels**: 8 flash channels
- **Chips per Channel**: 4
- **Dies per Chip**: 2
- **Planes per Die**: 2
- **Blocks per Plane**: 2048
- **Pages per Block**: 256
- **Page Capacity**: 8192 bytes (8 KB)

### Storage Configuration
- **Data Cache**: 256 MB DRAM cache with advanced caching mechanism
- **Cache Sharing**: Shared mode across all I/O flows
- **Address Mapping**: Page-level mapping
- **CMT Capacity**: 2 MB (Cached Mapping Table)
- **Overprovisioning Ratio**: 7%
- **Garbage Collection**: 
  - Execution threshold: 5%
  - Hard threshold: 0.5%
  - Block selection: RGA (Random Greedy Algorithm)
  - Preemptible GC: Disabled

### Wear Leveling
- **Dynamic Wear Leveling**: Enabled
- **Static Wear Leveling**: Enabled (threshold: 100 PE cycles)

### Flash Timing Parameters
- **Page Read Latency**: 75,000 ns (all bit types)
- **Page Program Latency**: 750,000 ns (all bit types)
- **Block Erase Latency**: 3,800,000 ns
- **PE Cycles Limit**: 10,000 cycles per block

## Schedulers Under Evaluation

Five transaction scheduling policies are evaluated:

### 1. Round Robin (RR)
- **Type**: Request-level fairness
- **Mechanism**: Simple rotation, one request per flow per turn
- **Characteristics**: 
  - Simple and lightweight
  - Fair when request sizes are uniform
  - Unfair when request sizes vary significantly

### 2. Deficit Round Robin (DRR)
- **Type**: Byte-level fairness
- **Mechanism**: Each flow receives a quantum (default: 4 KB) per round. Requests are serviced if they fit within the accumulated deficit counter
- **Characteristics**:
  - Provides byte-level fairness
  - Handles variable request sizes better than RR
  - Supports per-flow weights for proportional allocation

### 3. Quick Fair Queueing (QFQ)
- **Type**: Weighted fair queueing
- **Mechanism**: Tags each request with a virtual finish time based on size and flow weight. Always selects the request with the smallest virtual finish time
- **Characteristics**:
  - Precise proportional fairness
  - Handles high contention well
  - More computationally intensive than RR/DRR

### 4. MINMAX Fairness Scheduler
- **Type**: Min-max fairness optimization
- **Mechanism**: Computes a slowdown ratio estimate `r_i = (S_i + 1.0) / w_i` for each flow, where `S_i` is accumulated service and `w_i` is the weight. Selects the flow with the smallest ratio to minimize slowdown disparity
- **Characteristics**:
  - Optimizes for min-max fairness
  - Considers service history
  - Default weight: 1.0 per flow (configurable in `TSU_MinMax.h`)

### 5. FLIN (Fairness via Latency INterference)
- **Type**: Slowdown-aware fairness
- **Mechanism**: Favors flows receiving less than their fair share by tracking recent service history. Includes bias for read-heavy flows
- **Characteristics**:
  - Addresses interference between flows
  - Adapts to workload characteristics
  - Designed for device-level fairness

## Workloads

The experiment uses 14 different workloads covering various scenarios:

### Synthetic Workloads

1. **workload_scenario_1.xml**
   - Write-heavy synthetic stress test
   - Two NVMe flows with different bandwidths
   - Tests scheduler behavior under write contention

2. **workload_scenario_2.xml**
   - Read-dominated synthetic workload
   - Designed for latency sensitivity testing
   - Two flows with 100% read operations

3. **workload_scenario_3.xml**
   - Mixed trace-based workload
   - Uses `traces/tpcc-small.trace`
   - Represents realistic database workload patterns

### FAST'18 Artifact Workloads

4-6. **Backend Contention Workloads** (`fast18/backend-contention/`)
   - `workload-backend-contention-flow-1-flow-2.xml`: Two flows competing for backend resources
   - `workload-backend-contention-flow-1.xml`: Single flow baseline
   - `workload-backend-contention-flow-2.xml`: Single flow baseline
   - Tests scheduler behavior under backend resource contention

7-9. **Data Cache Contention Workloads** (`fast18/data-cache-contention/`)
   - `workload-datacache-contention-flow-1.xml`: Single flow
   - `workload-datacache-contention-flow-2.xml`: Single flow
   - Tests cache sharing behavior
   - Note: `workload-datacache-contention-flow-1-flow-2.xml` is excluded due to known FPE (Floating Point Exception) issues

10-12. **Queue Fetch Size Workloads** (`fast18/queue-fetch-size/`)
    - `workload-queue-fetch-size-flow-1-flow-2.xml`: Two flows
    - `workload-queue-fetch-size-flow-1.xml`: Single flow
    - `workload-queue-fetch-size-flow-2.xml`: Single flow
    - Tests impact of queue fetch size on fairness

### Stress Test Workloads

13. **workload_stress_bully_victim.xml**
    - Tests scheduler behavior when one flow dominates
    - Evaluates protection of victim flows

14. **workload_stress_multiqueue.xml**
    - Tests multi-queue scenarios
    - Evaluates scheduler scalability

15. **workload_stress_rw_interference.xml**
    - Tests read-write interference
    - Evaluates scheduler handling of mixed workloads

### Workload Characteristics

Each workload can define multiple I/O flows with the following parameters:
- **Priority Class**: URGENT, HIGH, MEDIUM, or LOW
- **Caching Mode**: WRITE_CACHE, READ_CACHE, WRITE_READ_CACHE, or TURNED_OFF
- **Resource Allocation**: Channel IDs, Chip IDs, Die IDs, Plane IDs
- **Request Generation**: 
  - Synthetic: Based on bandwidth or queue depth
  - Trace-based: From pre-recorded trace files
- **Request Characteristics**:
  - Read/Write percentage
  - Address distribution (streaming, random uniform, hot-cold, mixed)
  - Request size distribution (fixed or normal)
  - Working set percentage

## Experiment Execution

### Automated Execution Script

The experiment is executed using `run_experiments.sh`, which:

1. **Compiles MQSim** if the binary is not found
2. **Creates timestamped results directory**: `results/YYYYMMDD-HHMMSS/`
3. **Iterates over schedulers**: For each of the 5 schedulers (RR, DRR, QFQ, MINMAX, FLIN)
4. **Iterates over workloads**: For each of the 14 workloads
5. **Runs simulation**: 
   - Creates a temporary config file with the selected scheduler
   - Executes: `./MQSim -i <config> -w <workload>`
   - Captures output to `run.log`
6. **Collects outputs**: 
   - Copies `MQSim_Results*.xml` files
   - Copies any `*_results*` directories
   - Organizes by scheduler and workload

### Execution Model

- **Sequential by Scheduler**: All workloads for a scheduler complete before moving to the next
- **Parallel within Scheduler**: Multiple workloads can run in parallel (controlled by `WORKLOAD_JOBS` environment variable, default: 1)
- **Error Handling**: Failed experiments are logged but don't stop the entire run

### Total Experiment Count

- **5 schedulers** × **14 workloads** = **70 experiments** per run

## Results Structure

Results are organized in a hierarchical directory structure:

```
results/YYYYMMDD-HHMMSS/
├── RR/
│   ├── workload_scenario_1/
│   │   ├── run.log                    # Simulation log
│   │   └── MQSim_Results*.xml         # Detailed results
│   ├── workload_scenario_2/
│   └── ...
├── DRR/
├── QFQ/
├── MINMAX/
├── FLIN/
├── parsed/                            # Generated by parse_results.py
│   ├── all_results.json
│   ├── throughput_table.csv
│   ├── latency_table.csv
│   └── requests_table.csv
├── fairness/                          # Generated by analyze_fairness.py
│   ├── fairness_results.json
│   └── fairness_summary.csv
├── visualizations/                    # Generated by create_visualizations.py
│   ├── throughput_comparison.png
│   ├── latency_comparison.png
│   ├── summary_throughput.png
│   └── summary_latency.png
└── fairness_visualizations/           # Generated by create_fairness_visualizations.py
    └── jain_fairness_comparison.png
```

## Analysis Pipeline

### Step 1: Result Parsing (`parse_results.py`)

Extracts performance metrics from MQSim XML output files:

**Metrics Collected:**
- **Throughput**: Total bandwidth in MB/s (summed across all flows)
- **Latency**: Average device response time in nanoseconds
- **Request Count**: Total number of requests processed
- **Per-Flow Metrics**: Individual flow statistics

**Output Files:**
- `all_results.json`: Complete results in JSON format
- `throughput_table.csv`: Throughput comparison across schedulers/workloads
- `latency_table.csv`: Latency comparison
- `requests_table.csv`: Request count statistics

### Step 2: Fairness Analysis (`analyze_fairness.py`)

Calculates fairness metrics from simulation logs:

**Fairness Metrics:**
- **Jain's Fairness Index**: 
  - For request distribution (higher = more fair, range: 0-1)
  - For response time (inverse response times)
  - For completion rates
- **Fairness Ratio**: Min/Max ratio of requests serviced
- **Coefficient of Variation**: Standard deviation normalized by mean
- **Per-Flow Statistics**: 
  - Requests generated vs. serviced
  - Response times per flow
  - Completion rates

**Output Files:**
- `fairness_results.json`: Detailed fairness metrics per experiment
- `fairness_summary.csv`: Summary table of fairness indices

### Step 3: Visualization Generation

#### Performance Visualizations (`create_visualizations.py`)

Generates comparative charts:
- **Throughput Comparison**: Bar charts comparing schedulers across workloads
- **Latency Comparison**: Bar charts for average latency
- **Summary Charts**: Aggregated views across all workloads

#### Fairness Visualizations (`create_fairness_visualizations.py`)

Generates fairness-specific charts:
- **Jain's Fairness Index Comparison**: Heatmaps or bar charts showing fairness across schedulers and workloads

## Running the Complete Pipeline

### Option 1: Full Automated Run

```bash
cd MQSim
./run_experiments_with_viz.sh
```

This script:
1. Runs all experiments (`run_experiments.sh`)
2. Parses results
3. Analyzes fairness
4. Generates visualizations

### Option 2: Manual Step-by-Step

```bash
# Step 1: Run experiments
./run_experiments.sh

# Step 2: Find latest results
LATEST_RESULTS=$(ls -td results/20* | head -1)

# Step 3: Parse results
mkdir -p "$LATEST_RESULTS/parsed"
python3 parse_results.py "$LATEST_RESULTS" "$LATEST_RESULTS/parsed"

# Step 4: Analyze fairness
mkdir -p "$LATEST_RESULTS/fairness"
python3 analyze_fairness.py "$LATEST_RESULTS" "$LATEST_RESULTS/fairness"

# Step 5: Generate visualizations
mkdir -p "$LATEST_RESULTS/visualizations"
python3 create_visualizations.py "$LATEST_RESULTS/parsed" "$LATEST_RESULTS/visualizations"

mkdir -p "$LATEST_RESULTS/fairness_visualizations"
python3 create_fairness_visualizations.py "$LATEST_RESULTS/fairness" "$LATEST_RESULTS/fairness_visualizations"
```

### Option 3: SLURM Cluster Execution

For HPC environments, use the SLURM scripts:

```bash
# Submit job
sbatch run_experiments.slurm

# Or with visualization
sbatch run_experiments_with_viz.slurm

# Check progress
./check_progress.sh
./check_results.sh
```

## Key Metrics and Evaluation Criteria

### Performance Metrics
- **Throughput**: Total bandwidth delivered (MB/s)
- **Latency**: Average device response time (nanoseconds)
- **Request Completion**: Number of requests successfully processed

### Fairness Metrics
- **Jain's Fairness Index**: 
  - 1.0 = perfectly fair (all flows receive equal service)
  - Approaches 0 = highly unfair (one flow dominates)
- **Fairness Ratio**: Min/Max ratio (1.0 = perfect fairness)
- **Coefficient of Variation**: Lower values indicate more fairness

### Evaluation Goals
1. **Fairness**: Ensure all flows receive equitable service
2. **Performance**: Maintain high throughput and low latency
3. **Trade-offs**: Understand fairness vs. performance trade-offs
4. **Workload Sensitivity**: Evaluate scheduler behavior across different workload types

## Configuration Customization

### Adding New Workloads

Edit `run_experiments.sh` and add to the `WORKLOADS` array:

```bash
WORKLOADS=(
  "workload_scenario_1.xml"
  "your_new_workload.xml"
  # ...
)
```

### Changing Schedulers

Edit `run_experiments.sh` and modify the `POLICIES` array:

```bash
POLICIES=(
  "RR"
  "DRR"
  # Add or remove schedulers
)
```

### Adjusting SSD Configuration

Modify `ssdconfig.xml` to change:
- Flash technology (SLC, MLC, TLC)
- Channel/chip/die/plane counts
- Cache size and policies
- Garbage collection thresholds
- Wear leveling settings

### Parallel Execution

Control parallelism with environment variable:

```bash
WORKLOAD_JOBS=4 ./run_experiments.sh  # Run 4 workloads in parallel per scheduler
```

## Troubleshooting

### Common Issues

1. **MQSim Binary Not Found**: Run `make` to compile
2. **Missing Workload Files**: Check file paths in `WORKLOADS` array
3. **XML Parsing Errors**: Verify workload XML syntax
4. **Out of Memory**: Reduce `WORKLOAD_JOBS` or run sequentially
5. **Floating Point Exceptions**: Some workload combinations may cause FPE (e.g., `datacache-contention-flow-1-flow-2.xml`)

### Checking Results

```bash
# Check experiment progress
./check_progress.sh

# View detailed results summary
./check_results.sh

# Check job status (SLURM)
./check_job_status.sh
```

## References

- **MQSim Paper**: Tavakkol et al., "MQSim: A Framework for Enabling Realistic Studies of Modern Multi-Queue SSD Devices," FAST 2018
- **MQSim Repository**: Original MQSim implementation and documentation
- **Scheduler Algorithms**: See `docs/IMPLEMENTATION.md` for implementation details

## Notes

- Experiments are deterministic when using the same seed (321 in `ssdconfig.xml`)
- Results are archived as ZIP files after completion
- Partial results can be analyzed if some experiments fail
- Visualization scripts handle missing data gracefully

