#!/usr/bin/env python3
"""
Automation harness that runs all schedulers against all test traces and
collects summary metrics into a CSV file.
"""

import argparse
import csv
import subprocess
from pathlib import Path
from typing import Dict, List


def parse_stdout(stdout: str) -> Dict[str, float]:
    metrics: Dict[str, float] = {}
    for line in stdout.splitlines():
        if line.startswith("Fairness Index:"):
            metrics["fairness_index"] = float(line.split(":")[1].strip())
        elif line.startswith("Throughput Fairness Index:"):
            metrics["throughput_fairness_index"] = float(line.split(":")[1].strip())
        elif line.startswith("Throughput (MB/s):"):
            metrics["throughput_MBps"] = float(line.split(":")[1].strip())
        elif line.startswith("Average latency"):
            metrics["avg_latency_s"] = float(line.split(":")[1].strip())
        elif line.startswith("Completed requests:"):
            parts = line.split()
            if len(parts) >= 4:
                metrics["completed"] = float(parts[2])
                metrics["runtime_s"] = float(parts[4].rstrip("s"))
    return metrics


def run_case(binary: Path, trace: Path, scheduler: str, results_dir: Path) -> Dict:
    run_results = results_dir / f"{trace.stem}_{scheduler}.csv"
    run_results.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        str(binary),
        "--trace", str(trace),
        "--scheduler", scheduler,
        "--results", str(run_results),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    metrics = parse_stdout(proc.stdout)
    metrics.update(
        {
            "trace": trace.name,
            "trace_path": str(trace),
            "scheduler": scheduler,
            "results_path": str(run_results),
        }
    )
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Run schedulers across traces and collect metrics")
    parser.add_argument("--binary", default="build/ssd-fairness", help="Path to simulator binary")
    parser.add_argument("--traces", default="test_data/traces", help="Directory containing trace CSVs")
    parser.add_argument("--output-dir", default="results/matrix", help="Where to write per-run results")
    parser.add_argument(
        "--schedulers",
        nargs="*",
        default=["fifo", "rr", "drr", "qfq", "flin"],
        help="Scheduler policies to evaluate",
    )
    parser.add_argument(
        "--summary",
        default="results/matrix/summary.csv",
        help="Path to aggregated summary CSV",
    )
    args = parser.parse_args()

    binary = Path(args.binary)
    trace_dir = Path(args.traces)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    rows: List[Dict] = []
    traces = sorted(trace_dir.glob("*.csv"))
    if not traces:
        raise SystemExit(f"No traces found under {trace_dir}")

    for trace in traces:
        for scheduler in args.schedulers:
            print(f"Running {scheduler} on {trace.name}...")
            rows.append(run_case(binary, trace, scheduler, output_dir))

    summary_path = Path(args.summary)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "trace",
        "scheduler",
        "fairness_index",
        "throughput_fairness_index",
        "throughput_MBps",
        "avg_latency_s",
        "completed",
        "runtime_s",
        "results_path",
        "trace_path",
    ]
    with summary_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    print(f"Wrote summary to {summary_path}")


if __name__ == "__main__":
    main()
