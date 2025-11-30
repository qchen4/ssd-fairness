#!/usr/bin/env python3
"""
plot_wear_results.py
====================

Reads experiments_summary.csv (produced by run_experiments.py) and generates:
  * A grouped bar chart comparing wear imbalance (max - min) for WL policies.
  * Optionally, a CDF plot of erase-count distributions if per-block dumps exist.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Dict, List

import matplotlib.pyplot as plt


def load_summary(path: Path) -> List[Dict[str, str]]:
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        return list(reader)


def compute_imbalance(rows: List[Dict[str, str]], workload: str, policy: str) -> float:
    for row in rows:
        if row["workload_name"] == workload and row["wl_policy"] == policy:
            try:
                wear_max = float(row["wear_max_erase"])
                wear_min = float(row["wear_min_erase"])
                return wear_max - wear_min
            except (TypeError, ValueError):
                return 0.0
    return 0.0


def plot_imbalance(rows: List[Dict[str, str]], output_path: Path) -> None:
    workloads = sorted({row["workload_name"] for row in rows})
    policies = sorted({row["wl_policy"] for row in rows})
    if not workloads or not policies:
        print("No data to plot.")
        return

    width = 0.8 / len(policies)
    x_positions = range(len(workloads))

    fig, ax = plt.subplots(figsize=(10, 5))
    for idx, policy in enumerate(policies):
        offsets = [x + idx * width for x in x_positions]
        heights = [compute_imbalance(rows, workload, policy) for workload in workloads]
        ax.bar(offsets, heights, width=width, label=policy)

    ax.set_xticks([x + width * (len(policies) - 1) / 2 for x in x_positions])
    ax.set_xticklabels(workloads)
    ax.set_ylabel("Wear imbalance (max - min erases)")
    ax.set_title("Wear imbalance across workloads")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(output_path)
    plt.close(fig)
    print(f"[plot] Saved imbalance plot to {output_path}")


def load_counts(path: Path) -> List[int]:
    counts: List[int] = []
    with path.open(newline="") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        for row in reader:
            try:
                count = int(row[-1])
                counts.append(count)
            except (ValueError, IndexError):
                continue
    return sorted(counts)


def plot_cdf(rows: List[Dict[str, str]], args: argparse.Namespace) -> None:
    if not args.cdf_dir or not args.cdf_workload:
        return
    cdf_dir = Path(args.cdf_dir)
    workload = args.cdf_workload
    policies = sorted({row["wl_policy"] for row in rows})

    fig, ax = plt.subplots(figsize=(8, 5))
    plotted = False

    for policy in policies:
        file_path = cdf_dir / f"{workload}_{policy}_wear_counts.csv"
        if not file_path.exists():
            continue
        counts = load_counts(file_path)
        if not counts:
            continue
        probs = [i / (len(counts) - 1) if len(counts) > 1 else 1.0 for i in range(len(counts))]
        ax.plot(counts, probs, label=policy)
        plotted = True

    if not plotted:
        print(f"[plot] Skipping CDF plot; no counts files found in {cdf_dir}")
        plt.close(fig)
        return

    ax.set_xlabel("Erase count")
    ax.set_ylabel("CDF")
    ax.set_title(f"Wear CDF for workload {workload}")
    ax.legend()
    ax.grid(alpha=0.3)

    output_path = Path(args.output_dir) / f"{workload}_cdf.png"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(output_path)
    plt.close(fig)
    print(f"[plot] Saved CDF plot to {output_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plot wear results from experiments_summary.csv")
    parser.add_argument("--summary", default="experiments/experiments_summary.csv",
                        help="Summary CSV produced by run_experiments.py")
    parser.add_argument("--output-dir", default="plots", help="Directory to store generated plots")
    parser.add_argument("--cdf-dir", default=None,
                        help="Directory containing per-block wear count dumps (optional)")
    parser.add_argument("--cdf-workload", default=None,
                        help="Workload name to use for CDF plots (requires --cdf-dir files)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = load_summary(Path(args.summary))
    if not rows:
        print(f"No rows found in {args.summary}")
        return
    plot_imbalance(rows, Path(args.output_dir) / "wear_imbalance.png")
    plot_cdf(rows, args)


if __name__ == "__main__":
    main()
