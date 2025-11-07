# SSD Fairness Simulator

An educational C++17 simulator for experimenting with multi-tenant Solid-State Drive (SSD) schedulers. The simulator ingests trace files, feeds requests through pluggable scheduling policies, models a multi-channel SSD, and reports fairness/latency metrics.

---

## Table of Contents

1. [Project Overview](#project-overview)  
2. [Repository Layout](#repository-layout)  
3. [Build & Run](#build--run)  
4. [Command-Line Interface](#command-line-interface)  
5. [Trace Format](#trace-format)  
6. [Scheduler Policies](#scheduler-policies)  
7. [Simulation Internals](#simulation-internals)  
8. [Metrics & Outputs](#metrics--outputs)  
9. [Plotting](#plotting)  
10. [Extending the Simulator](#extending-the-simulator)

---

## Project Overview

At a high level the simulator repeatedly:

1. Reads a CSV trace containing `(timestamp, process_id, op, address, size)` rows.  
2. Feeds requests into the selected scheduler policy.  
3. Dispatches requests onto the SSD model as channels become free.  
4. Records per-user metrics (latency, throughput) and Jain’s fairness index.  
5. Optionally plots results using the helper scripts in `tools/`.

This setup lets you compare fairness-focused schedulers (Round Robin, Deficit Round Robin, Weighted Fair Queuing, Start-Gap Fair Scheduling) under identical workloads.

---

## Repository Layout

| Path | Description |
| ---- | ----------- |
| `src/` | Implementations for the main driver, SSD model, schedulers, metrics, and utilities. |
| `include/` | Public headers describing the simulator interfaces. |
| `traces/` | Sample traces (e.g., `example.csv` and `synthetic.csv`). |
| `tools/` | Optional helpers (`trace_gen.py`, `plot_results.py`). |
| `run.sh` | Convenience script that builds, runs a trace, and performs plotting. |
| `uml.puml` | PlantUML diagram summarizing the architecture. |

---

## Build & Run

### Prerequisites

- CMake ≥ 3.10  
- A C++17 compiler (GCC, Clang, MSVC)  
- Python 3 if you plan to generate traces or plot results  
- (Optional) pandas, matplotlib, seaborn for plotting

### Quick Start

```bash
./run.sh
```

`run.sh` performs the following:
1. Configures and builds the simulator inside `build/`.  
2. Generates `traces/synthetic.csv` via `tools/trace_gen.py` when available.  
3. Runs the simulator with the generated trace.  
4. Attempts to plot results (skipped if the CSV lacks per-request data).

### Manual Invocation

```bash
mkdir -p build
cd build
cmake ..
make -j$(nproc)
./ssd-fairness --trace ../traces/example.csv --scheduler drr --quantum 8192
```

---

## Command-Line Interface

`ssd-fairness [options]`

| Option | Description |
| ------ | ----------- |
| `-t, --trace PATH` | CSV trace to load (`traces/example.csv` by default). |
| `-s, --scheduler NAME` | Scheduler policy: `rr`, `drr`, `qfq`, `sgfs`. |
| `-q, --quantum BYTES` | DRR quantum size; forwarded to schedulers that use it. |
| `-u, --users N` | Override number of users; inferred from trace otherwise. |
| `-c, --channels N` | Number of SSD channels (default 8). |
| `-r, --read-bw MBPS` | Aggregate read bandwidth (default 2000 MB/s). |
| `-w, --write-bw MBPS` | Aggregate write bandwidth (default 1200 MB/s). |
| `-W, --weights CSV` | Comma-separated per-user weights (applied to WFQ/DRR). |

Example:

```bash
./build/ssd-fairness \
  --trace traces/example.csv \
  --scheduler sgfs \
  --quantum 4096 \
  --channels 16 \
  --weights 1,1,2,4
```

---

## Trace Format

Traces are simple CSV files with a header row:

```
timestamp,process_id,type,address,size
0,process1,READ,0xdeadbeef,4096
...
```

- `timestamp`: arrival time in **microseconds** since start of simulation.  
- `process_id`: arbitrary string; mapped to integer user IDs on load.  
- `type`: `READ` or `WRITE` (case-insensitive).  
- `address`: unused by the current model but retained for compatibility.  
- `size`: request size in bytes.

`util::load_trace_csv` converts timestamps to seconds, assigns user IDs, and sorts requests by `(arrival_ts, user_id)`.

---

## Scheduler Policies

| Policy | File(s) | Description |
| ------ | ------- | ----------- |
| **RoundRobin** | `include/scheduler_impl.hpp` | Classic request-per-turn rotation among active users. |
| **DeficitRoundRobin (DRR)** | `include/scheduler_impl.hpp` | Adds byte-level fairness by granting quanta to each user until its head request fits. Supports per-user weights. |
| **WeightedFair (WFQ/QFQ)** | `include/scheduler_impl.hpp` | Approximates weighted fair queuing by tagging requests with virtual finish times and always selecting the smallest tag. |
| **StartGap (SGFS)** | `include/scheduler_impl.hpp` | Wraps another scheduler (WFQ by default) and rotates logical user IDs to mimic spatial fair sharing across SSD channels. |

All schedulers implement the `Scheduler` interface:

```cpp
class Scheduler {
 public:
  virtual void set_users(int n) = 0;
  virtual void set_weights(const std::vector<double>&);
  virtual void set_quantum(double);
  virtual void enqueue(const Request& r) = 0;
  virtual std::optional<int> pick_user(double virtual_time) = 0;
  virtual std::optional<Request> pop(int uid) = 0;
  virtual bool empty() const = 0;
};
```

Adding a new policy means subclassing `Scheduler` and wiring it into `main.cpp`.

---

## Simulation Internals

1. **Event Loop**: `src/main.cpp` advances simulation time by repeatedly admitting arrivals, dispatching ready work, and processing completion events stored in `ssd::EventQueue`.
2. **SSD Model**: `ssd::SSD` keeps track of per-channel availability via `ChannelState.free_at`. Dispatch time is `size / (per-channel BW)`, where per-channel bandwidth = aggregate BW / `num_channels`.
3. **Metrics**: `ssd::Metrics` accumulates per-user latency, throughput, and request counts, then computes Jain’s fairness index over non-idle users.

Key headers:
- `include/events.hpp`: priority-queue wrapper used for device completions.  
- `include/ssd.hpp`: SSD device contract.  
- `include/metrics.hpp`: statistics collector interface.  
- `include/types.hpp`: shared `Request`/`SimConfig` definitions.

---

## Metrics & Outputs

After each run the simulator writes `build/results.csv` with per-user summaries:

```
user_id,completed,avg_latency_s,total_bytes
0,500,0.000812,2097152
1,500,0.000809,2097152
```

It also prints to stdout:

```
Simulation complete.
Fairness Index: 0.994
Results saved to build/results.csv
```

### Jain’s Fairness Index

`Metrics::fairness_index()` computes:

```
(sum_i x_i)^2 / (n * sum_i x_i^2)
```

where `x_i` is the throughput (bytes) for user `i`, and `n` counts only users that transferred at least one byte (idle users are ignored to avoid skew).

If you need per-request latencies for plotting, extend `Metrics::save_csv` or instrument the event loop before completion to dump additional data.

---

## Plotting

`run.sh` optionally calls `tools/plot_results.py`. The current CSV contains summarized per-user data, so plotting is skipped by default (the script expects per-request columns like `process_id` and `latency`). To enable plots:

1. Modify `Metrics::save_csv` to emit per-request data.  
2. Update or wrap `tools/plot_results.py` to match the new schema.  
3. Re-run `./run.sh`.

The plotting script uses pandas/matplotlib/seaborn; install them via `pip install -r requirements.txt` (requirements file not yet provided).

---

## Extending the Simulator

**Add a Scheduler**
1. Create a new class in `include/scheduler_impl.hpp` or a dedicated file.  
2. Implement the `Scheduler` contract.  
3. Update `src/main.cpp` to recognize your scheduler via a CLI flag.  
4. (Optional) Add a unit test or trace scenario showcasing the policy.

**Change the SSD Model**
1. Edit `include/ssd.hpp`/`src/ssd.cpp` to incorporate additional device behavior (e.g., queue depths, wear leveling).  
2. Update calculations in `read_service_time_s` / `write_service_time_s`.  
3. Ensure `SSD::dispatch` still returns accurate completion timestamps for the event queue.

**Add Metrics**
1. Extend `ssd::Metrics::UserStats` with new fields.  
2. Update `on_finish`, `save_csv`, and any reporting code accordingly.  
3. Adjust plotting scripts / downstream consumers to read the new columns.

---

## Support & Contributions

Issues and pull requests are welcome. When contributing:

1. Run `./run.sh` (or at minimum rebuild and exercise the simulator with a representative trace).  
2. Include unit tests or trace-based reproductions where applicable.  
3. Document new features in this README so others can discover them.

Enjoy experimenting with SSD fairness algorithms!
