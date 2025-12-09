#!/usr/bin/env python3
"""
Plot scheduler metrics for a single trace (default: traces/ssdtrace-00).

For each scheduler, this script:
  - runs the ssd-fairness binary,
  - parses stdout to extract key metrics,
  - and generates bar charts comparing schedulers.
"""

import argparse
import subprocess
from pathlib import Path
from typing import Dict, List

import matplotlib.pyplot as plt


def parse_stdout(stdout: str) -> Dict[str, float]:
    """Parse metrics from the simulator's stdout."""
    metrics: Dict[str, float] = {}
    for line in stdout.splitlines():
        if line.startswith("Fairness Index:"):
            metrics["fairness_index"] = float(line.split(":")[1].strip())
        elif line.startswith("Throughput Fairness Index:"):
            metrics["throughput_fairness_index"] = float(line.split(":")[1].strip())
        elif line.startswith("Throughput (MB/s):"):
            metrics["throughput_MBps"] = float(line.split(":")[1].strip())
        elif line.startswith("Average slowdown"):
            metrics["avg_slowdown"] = float(line.split(":")[1].strip())
        elif line.startswith("Average latency"):
            metrics["avg_latency_s"] = float(line.split(":")[1].strip())
        elif line.startswith("Completed requests:"):
            parts = line.split()
            if len(parts) >= 4:
                metrics["completed"] = float(parts[2])
                metrics["runtime_s"] = float(parts[4].rstrip("s"))
    return metrics


def run_case(binary: Path, trace: Path, scheduler: str, results_dir: Path) -> Dict:
    """Run one scheduler on the given trace and return parsed metrics."""
    run_results = results_dir / f"{trace.stem}_{scheduler}.csv"
    run_results.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        str(binary),
        "--trace",
        str(trace),
        "--scheduler",
        scheduler,
        "--results",
        str(run_results),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    metrics = parse_stdout(proc.stdout)
    metrics.update(
        {
            "scheduler": scheduler,
            "trace": trace.name,
            "trace_path": str(trace),
            "results_path": str(run_results),
        }
    )
    return metrics


def plot_metrics(rows: List[Dict], output_path: Path) -> None:
    schedulers = [row["scheduler"] for row in rows]
    fairness = [row.get("fairness_index", 0.0) for row in rows]
    throughput = [row.get("throughput_MBps", 0.0) for row in rows]
    latency = [row.get("avg_latency_s", 0.0) for row in rows]

    fig, axes = plt.subplots(1, 3, figsize=(15, 4))

    axes[0].bar(schedulers, fairness, color="tab:blue")
    axes[0].set_title("Fairness Index")
    axes[0].set_ylabel("Jain's index")
    axes[0].set_xlabel("Scheduler")
    axes[0].set_ylim(0.0, max(fairness) * 1.1 if fairness else 1.0)

    axes[1].bar(schedulers, throughput, color="tab:green")
    axes[1].set_title("Throughput")
    axes[1].set_ylabel("MB/s")
    axes[1].set_xlabel("Scheduler")

    axes[2].bar(schedulers, latency, color="tab:red")
    axes[2].set_title("Average latency")
    axes[2].set_ylabel("Seconds")
    axes[2].set_xlabel("Scheduler")

    fig.suptitle(f"Scheduler comparison for {rows[0]['trace']}" if rows else "No data")
    fig.tight_layout(rect=[0, 0.03, 1, 0.95])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Plot scheduler metrics for a single trace"
    )
    parser.add_argument(
        "--binary",
        default="build/ssd-fairness",
        help="Path to simulator binary",
    )
    parser.add_argument(
        "--trace",
        default="traces/ssdtrace-00",
        help="Path to trace file (CSV or blktrace text)",
    )
    parser.add_argument(
        "--schedulers",
        nargs="*",
        default=["fifo", "rr", "drr", "qfq", "flin"],
        help="Scheduler policies to evaluate",
    )
    parser.add_argument(
        "--results-dir",
        default="results",
        help="Directory to write per-run CSVs into",
    )
    parser.add_argument(
        "--output",
        default="results/ssdtrace-00_metrics.png",
        help="Output PNG path for the plot",
    )
    args = parser.parse_args()

    binary = Path(args.binary)
    trace = Path(args.trace)
    results_dir = Path(args.results_dir)
    output_path = Path(args.output)

    rows: List[Dict] = []
    for sched in args.schedulers:
        print(f"Running {sched} on {trace}...")
        rows.append(run_case(binary, trace, sched, results_dir))

    if not rows:
        raise SystemExit("No runs completed; nothing to plot")

    plot_metrics(rows, output_path)
    print(f"Wrote plot to {output_path}")


if __name__ == "__main__":
    main()



