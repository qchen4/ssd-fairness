#!/usr/bin/env python3
"""
Plot MQSim summary CSV into bar charts.

Usage:
  python3 plot_results.py --summary results/<timestamp>/summary.csv --outdir results/<timestamp>/plots

Outputs:
  - latency_device_us.png: device_resp_us per flow/policy/workload
  - slowdown_vs_best.png: slowdown_vs_best per flow/policy/workload
"""

import argparse
import csv
from collections import defaultdict, OrderedDict
from pathlib import Path

import matplotlib.pyplot as plt


def parse_args():
    p = argparse.ArgumentParser(description="Plot MQSim summary CSV")
    p.add_argument("--summary", required=True, help="Path to summary.csv")
    p.add_argument("--outdir", help="Output dir for plots (default: summary dir)")
    return p.parse_args()


def read_records(summary_path: Path):
    with summary_path.open() as f:
        reader = csv.DictReader(f)
        rows = [r for r in reader]
    # ensure numeric
    for r in rows:
        r["device_resp_us"] = float(r["device_resp_us"])
        r["end_to_end_us"] = float(r["end_to_end_us"])
        r["max_device_resp_us"] = float(r.get("max_device_resp_us", 0.0))
        r["max_end_to_end_us"] = float(r.get("max_end_to_end_us", 0.0))
        r["iops"] = float(r["iops"])
        r["iops_share"] = float(r.get("iops_share", 0.0))
        r["slowdown_vs_best"] = float(r["slowdown_vs_best"])
        r["slowdown_vs_best_tail"] = float(r.get("slowdown_vs_best_tail", 0.0))
    return rows


def ensure_outdir(outdir: Path):
    outdir.mkdir(parents=True, exist_ok=True)


def sort_policies(policies):
    order = ["OUT_OF_ORDER", "PRIORITY_OUT_OF_ORDER", "FLIN", "QFQ", "MINMAX"]
    seen = OrderedDict()
    for p in order:
        if p in policies:
            seen[p] = True
    for p in policies:
        if p not in seen:
            seen[p] = True
    return list(seen.keys())


def plot_metric(rows, metric, ylabel, title, out_path):
    # Group by workload then flow
    grouped = defaultdict(list)
    policies = set()
    for r in rows:
        key = (r["workload"], r["flow"])
        grouped[key].append(r)
        policies.add(r["policy"])
    policy_list = sort_policies(policies)

    n_groups = len(grouped)
    n_policies = len(policy_list)
    bar_width = 0.12
    spacing = bar_width * (n_policies + 1)
    x_ticks = []
    labels = []

    plt.figure(figsize=(max(6, n_groups * 0.9), 5))

    for idx, ((workload, flow), items) in enumerate(sorted(grouped.items())):
        base_x = idx * spacing
        values_by_policy = {r["policy"]: r for r in items}
        for pi, policy in enumerate(policy_list):
            x = base_x + pi * bar_width
            val = values_by_policy.get(policy, {}).get(metric, 0)
            plt.bar(x, val, width=bar_width, label=policy if idx == 0 else None)
        x_ticks.append(base_x + (n_policies - 1) * bar_width / 2)
        labels.append(f"{workload}\n{flow}")

    plt.xticks(x_ticks, labels, rotation=30, ha="right")
    plt.ylabel(ylabel)
    plt.title(title)
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_path)
    plt.close()


def plot_stacked_share(rows, metric, ylabel, title, out_path):
    grouped = defaultdict(list)
    policies = set()
    for r in rows:
        key = (r["workload"], r["flow"])
        grouped[key].append(r)
        policies.add(r["policy"])
    policy_list = sort_policies(policies)

    n_groups = len(grouped)
    plt.figure(figsize=(max(6, n_groups * 0.9), 5))

    x = range(n_groups)
    bottoms = [0.0] * n_groups
    labels = []

    # Sum shares per policy across flows of same workload? We plot per (workload,flow)
    for idx, ((workload, flow), items) in enumerate(sorted(grouped.items())):
        labels.append(f"{workload}\n{flow}")
        share_by_policy = {r["policy"]: r.get(metric, 0.0) for r in items}
        for policy in policy_list:
            val = share_by_policy.get(policy, 0.0)
            if idx == 0:
                plt.bar(idx, val, bottom=bottoms[idx], label=policy)
            else:
                plt.bar(idx, val, bottom=bottoms[idx])
            bottoms[idx] += float(val)

    plt.xticks(list(x), labels, rotation=30, ha="right")
    plt.ylabel(ylabel)
    plt.title(title)
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_path)
    plt.close()


def main():
    args = parse_args()
    summary_path = Path(args.summary).expanduser().resolve()
    if not summary_path.exists():
        raise SystemExit(f"summary not found: {summary_path}")
    outdir = Path(args.outdir).expanduser().resolve() if args.outdir else summary_path.parent / "plots"
    ensure_outdir(outdir)

    rows = read_records(summary_path)
    if not rows:
        raise SystemExit("No rows in summary CSV")

    plot_metric(
        rows,
        metric="device_resp_us",
        ylabel="Device response time (us)",
        title="Device response per workload/flow/policy",
        out_path=outdir / "latency_device_us.png",
    )
    plot_metric(
        rows,
        metric="slowdown_vs_best",
        ylabel="Slowdown vs best (lower is better)",
        title="Slowdown per workload/flow/policy",
        out_path=outdir / "slowdown_vs_best.png",
    )
    plot_metric(
        rows,
        metric="max_device_resp_us",
        ylabel="Max device response time (us)",
        title="Tail (max) device response per workload/flow/policy",
        out_path=outdir / "latency_device_us_max.png",
    )
    plot_metric(
        rows,
        metric="slowdown_vs_best_tail",
        ylabel="Tail slowdown vs best (lower is better)",
        title="Tail slowdown per workload/flow/policy",
        out_path=outdir / "slowdown_vs_best_tail.png",
    )
    plot_stacked_share(
        rows,
        metric="iops_share",
        ylabel="IOPS share",
        title="IOPS share per workload/flow/policy",
        out_path=outdir / "iops_share.png",
    )

    print(f"Wrote plots to {outdir}")


if __name__ == "__main__":
    main()

