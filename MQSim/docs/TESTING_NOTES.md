# Testing Notes - CPU vs GPU Usage

## Important: MQSim is CPU-Only

MQSim is a **CPU-based simulator** with **no GPU/CUDA code**. If you're seeing GPU usage, it's likely from:

1. **Other processes on the system** (not MQSim)
2. **Monitoring tool misidentification** (some tools may misreport CPU usage as GPU)
3. **System-level GPU processes** (unrelated to this project)

## Parallelization Design

The parallelization in `run_experiments.sh` is **CPU-based process parallelization**:

### How It Works

```bash
WORKLOAD_JOBS=${WORKLOAD_JOBS:-1}  # Default: 1 (sequential)
```

- **Default**: Runs experiments **sequentially** (one at a time)
- **With `WORKLOAD_JOBS=N`**: Runs **N MQSim processes in parallel** (CPU processes)

### Example Usage

```bash
# Sequential (one at a time) - uses 1 CPU core
./run_experiments.sh

# Parallel (4 jobs) - uses up to 4 CPU cores
WORKLOAD_JOBS=4 ./run_experiments.sh
```

### What Happens

1. Each `run_single_experiment` spawns a **separate MQSim process** (CPU)
2. Multiple processes run **concurrently** (not on GPU)
3. Each process uses **CPU cores** for simulation

## Build Parallelization

The `make -j4` command uses **4 parallel compilation jobs** (also CPU):
- Compiles multiple `.cpp` files simultaneously
- Uses CPU cores for compilation
- **Not GPU-related**

## If You're Seeing GPU Usage

1. **Check what's actually using GPU:**
   ```bash
   nvidia-smi  # Shows GPU processes
   ```

2. **Check CPU usage:**
   ```bash
   top
   htop
   ps aux --sort=-%cpu
   ```

3. **MQSim processes are CPU-only:**
   ```bash
   ps aux | grep MQSim  # Shows CPU usage, not GPU
   ```

## Recommendations

- **For testing**: Use `WORKLOAD_JOBS=1` (sequential) to avoid confusion
- **For performance**: Use `WORKLOAD_JOBS=$(nproc)` to use all CPU cores
- **GPU usage**: If you see GPU usage, it's **not from MQSim** - check other processes

