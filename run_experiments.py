#!/usr/bin/env python3
"""
run_experiments.py
==================

Experimental harness for evaluating wear-leveling policies under multiple trace
workloads. The script:

  1. Generates traces with `tools/trace_gen.py`.
  2. Runs the simulator binary (wear scheduler) with different WL configs.
  3. Collects per-run metrics into a summary CSV for downstream analysis.

Example:
    ./run_experiments.py --binary build/ssd-fairness \
        --trace-dir experiments/traces \
        --results-dir experiments/results \
        --summary experiments/experiments_summary.csv
"""

from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

DEFAULT_WORKLOADS = [
    {"name": "U", "workload": "uniform", "zipf_alpha": None},
    {"name": "Z1.0", "workload": "zipf", "zipf_alpha": 1.0},
    {"name": "H", "workload": "hotset", "zipf_alpha": None},
    {"name": "A1", "workload": "singlehot", "zipf_alpha": None},
]

DEFAULT_WL_POLICIES = [
    # WL0: dynamic WL only (median/pool), no segment rebalance and no min-cap policy.
    {"name": "WL0", "num_segments": 1, "rebalance_interval": 0, "rebalance_fraction": 0.0,
     "enable_min_cap_wl": False},
    # WL1 (WL2 in the design): enable the global min-cap policy on top of the
    # existing segment-based rebalancing to aggressively cap wear of hot writes.
    {"name": "WL1", "num_segments": 8, "rebalance_interval": 1000, "rebalance_fraction": 0.05,
     "enable_min_cap_wl": True},
]


def run_trace_generator(args: argparse.Namespace, workload: Dict, trace_path: Path, seed: int) -> None:
    trace_cmd = [
        args.python, args.trace_gen,
        "--output", str(trace_path),
        "--processes", str(args.processes),
        "--requests", str(args.requests),
        "--max-lba-blocks", str(args.max_lba_blocks),
        "--write-fraction", str(args.write_fraction),
        "--interarrival-max", str(args.interarrival_max),
        "--seed", str(seed),
        "--workload", workload["workload"],
    ]
    if workload["workload"] == "zipf":
        trace_cmd += ["--zipf-alpha", str(workload.get("zipf_alpha", args.zipf_alpha))]
        if args.zipf_max_rank:
            trace_cmd += ["--zipf-max-rank", str(args.zipf_max_rank)]
    if workload["workload"] == "hotset":
        trace_cmd += [
            "--hotset-fraction", str(args.hotset_fraction),
            "--hotset-hot-prob", str(args.hotset_hot_prob),
        ]

    subprocess.run(trace_cmd, check=True)


def parse_metrics_csv(path: Path) -> Dict[str, float]:
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        try:
            row = next(reader)
        except StopIteration:
            return {}

    def _get_float(key: str) -> Optional[float]:
        value = row.get(key)
        if value is None or value == "":
            return None
        try:
            return float(value)
        except ValueError:
            return None

    return {
        "wear_min_erase": _get_float("wear_min_erase"),
        "wear_max_erase": _get_float("wear_max_erase"),
        "wear_variance": _get_float("wear_variance"),
        "avg_latency_user0": _get_float("avg_latency_s"),
        "slowdown_avg_user0": _get_float("slowdown_avg"),
    }


def parse_sim_stdout(stdout: str) -> Dict[str, float]:
    metrics: Dict[str, float] = {}
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith("Fairness Index:"):
            metrics["fairness_index"] = float(line.split(":")[1].strip())
        elif line.startswith("Throughput Fairness Index:"):
            metrics["throughput_fairness_index"] = float(line.split(":")[1].strip())
        elif line.startswith("Average slowdown:"):
            metrics["average_slowdown"] = float(line.split(":")[1].strip())
        elif line.startswith("Throughput (MB/s):"):
            metrics["throughput_MBps"] = float(line.split(":")[1].strip())
        elif line.startswith("Average latency (s):"):
            metrics["average_latency_s"] = float(line.split(":")[1].strip())
        elif line.startswith("Completed requests:"):
            parts = line.replace("Completed requests:", "").split("in")
            try:
                metrics["completed_requests"] = float(parts[0].strip())
                metrics["runtime_s"] = float(parts[1].rstrip("s").strip())
            except (IndexError, ValueError):
                pass
    return metrics


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def append_summary_row(summary_path: Path, fieldnames: List[str], row: Dict[str, object]) -> None:
    file_exists = summary_path.exists()
    ensure_parent(summary_path)
    with summary_path.open("a", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


def run_simulation(args: argparse.Namespace, trace_path: Path, results_path: Path,
                   policy: Dict[str, object], workload: Dict[str, object]) -> Dict[str, float]:
    sim_cmd = [
        args.binary,
        "--scheduler", "wear",
        "--trace", str(trace_path),
        "--results", str(results_path),
        "--channels", str(args.channels),
        "--users", str(args.users),
        "--wear-hot-threshold", str(args.wear_hot_threshold),
        "--wear-pool-size", str(args.wear_pool_size),
        "--wear-num-segments", str(policy["num_segments"]),
        "--wear-rebalance-interval", str(policy["rebalance_interval"]),
        "--wear-rebalance-fraction", str(policy["rebalance_fraction"]),
    ]
    if args.wear_read_balance:
        sim_cmd.append("--wear-read-balance")
    if policy.get("enable_min_cap_wl"):
        sim_cmd.append("--wear-enable-min-cap")
        sim_cmd += [
            "--wear-min-cap-delta", str(args.wear_min_cap_delta),
            "--wear-min-cap-pool-size", str(args.wear_min_cap_pool_size),
        ]

    proc = subprocess.run(sim_cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"Simulator failed for workload={workload['name']} policy={policy['name']}:\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
    sim_metrics = parse_sim_stdout(proc.stdout)
    csv_metrics = parse_metrics_csv(results_path)
    merged = {**csv_metrics, **sim_metrics}
    merged["stdout_log"] = proc.stdout.strip()
    return merged


def build_fieldnames() -> List[str]:
    return [
        "workload_name",
        "workload_type",
        "wl_policy",
        "num_segments",
        "rebalance_interval",
        "rebalance_fraction",
        "trace_path",
        "results_path",
        "wear_min_erase",
        "wear_max_erase",
        "wear_variance",
        "fairness_index",
        "throughput_fairness_index",
        "average_slowdown",
        "throughput_MBps",
        "average_latency_s",
        "completed_requests",
        "runtime_s",
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run SSD fairness experiments.")
    parser.add_argument("--binary", default="build/ssd-fairness", help="Simulator binary path")
    parser.add_argument("--trace-gen", default="tools/trace_gen.py", help="Trace generator script")
    parser.add_argument("--python", default=sys.executable, help="Python interpreter to use")
    parser.add_argument("--trace-dir", default="experiments/traces", help="Directory for generated traces")
    parser.add_argument("--results-dir", default="experiments/results", help="Directory for per-run CSV outputs")
    parser.add_argument("--summary", default="experiments/experiments_summary.csv",
                        help="Aggregated summary CSV")
    parser.add_argument("--processes", type=int, default=4, help="Number of processes/users in traces")
    parser.add_argument("--requests", type=int, default=5000, help="Requests per trace")
    parser.add_argument("--max-lba-blocks", type=int, default=1 << 18,
                        help="Address space for trace generation (in 4KiB blocks)")
    parser.add_argument("--write-fraction", type=float, default=1.0,
                        help="Probability that a request is a WRITE (0..1)")
    parser.add_argument("--interarrival-max", type=int, default=1000,
                        help="Maximum timestamp delta between requests")
    parser.add_argument("--zipf-alpha", type=float, default=1.0, help="Default Zipf alpha")
    parser.add_argument("--zipf-max-rank", type=int, default=None, help="Zipf max rank (optional)")
    parser.add_argument("--hotset-fraction", type=float, default=0.01, help="Hotset fraction")
    parser.add_argument("--hotset-hot-prob", type=float, default=0.9, help="Probability of selecting from hotset")
    parser.add_argument("--wear-hot-threshold", type=float, default=4.0, help="Wear hot threshold")
    parser.add_argument("--wear-pool-size", type=int, default=16, help="Wear candidate pool size")
    parser.add_argument("--wear-read-balance", action="store_true", help="Enable wear read balance flag")
    parser.add_argument("--channels", type=int, default=8, help="Number of SSD channels for the simulator")
    parser.add_argument("--users", type=int, default=4, help="Number of users to pass to simulator")
    parser.add_argument("--wear-min-cap-delta", type=int, default=8,
                        help="Allowed delta from global min erase for WL2 hot writes")
    parser.add_argument("--wear-min-cap-pool-size", type=int, default=32,
                        help="Candidate pool size for WL2 hot writes")
    parser.add_argument("--seed", type=int, default=12345, help="Base PRNG seed for trace generation")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    trace_dir = Path(args.trace_dir)
    results_dir = Path(args.results_dir)
    trace_dir.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)

    fieldnames = build_fieldnames()

    for w_idx, workload in enumerate(DEFAULT_WORKLOADS):
        trace_seed = args.seed + w_idx
        trace_path = trace_dir / f"trace_{workload['name']}_seed{trace_seed}.csv"
        print(f"[trace] Generating {workload['name']} -> {trace_path}")
        run_trace_generator(args, workload, trace_path, trace_seed)

        for policy in DEFAULT_WL_POLICIES:
            run_label = f"{workload['name']}_{policy['name']}"
            results_path = results_dir / f"results_{run_label}.csv"
            print(f"[sim ] Running {run_label} -> {results_path}")
            metrics = run_simulation(args, trace_path, results_path, policy, workload)

            summary_row = {
                "workload_name": workload["name"],
                "workload_type": workload["workload"],
                "wl_policy": policy["name"],
                "num_segments": policy["num_segments"],
                "rebalance_interval": policy["rebalance_interval"],
                "rebalance_fraction": policy["rebalance_fraction"],
                "trace_path": str(trace_path),
                "results_path": str(results_path),
                "wear_min_erase": metrics.get("wear_min_erase"),
                "wear_max_erase": metrics.get("wear_max_erase"),
                "wear_variance": metrics.get("wear_variance"),
                "fairness_index": metrics.get("fairness_index"),
                "throughput_fairness_index": metrics.get("throughput_fairness_index"),
                "average_slowdown": metrics.get("average_slowdown"),
                "throughput_MBps": metrics.get("throughput_MBps"),
                "average_latency_s": metrics.get("average_latency_s"),
                "completed_requests": metrics.get("completed_requests"),
                "runtime_s": metrics.get("runtime_s"),
            }
            append_summary_row(Path(args.summary), fieldnames, summary_row)


if __name__ == "__main__":
    main()
