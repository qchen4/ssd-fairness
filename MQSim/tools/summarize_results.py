#!/usr/bin/env python3
"""
Summarize MQSim experiment outputs into a CSV with throughput/latency/slowdown.

Inputs:
  --root <path>   Root results folder, e.g., results/20251208-033010
  --output <path> Output CSV path (default: <root>/summary.csv)

The script expects per-run XML files under <root>/<policy>/<workload>/
matching "*_scenario_*.xml" (MQSim's default output naming).
"""

import argparse
import csv
import sys
from pathlib import Path
import xml.etree.ElementTree as ET


def parse_args():
    p = argparse.ArgumentParser(description="Summarize MQSim results to CSV")
    p.add_argument("--root", required=True, help="Root results dir (timestamped)")
    p.add_argument("--output", help="Output CSV path (default: <root>/summary.csv)")
    return p.parse_args()


def read_flows(xml_path: Path):
    """Parse a MQSim result XML and return list of flow dicts."""
    tree = ET.parse(xml_path)
    flows = []
    for flow in tree.findall(".//Host.IO_Flow"):
        name = (flow.findtext("Name") or "").strip()
        try_int = lambda tag: int(flow.findtext(tag, "0"))
        try_float = lambda tag: float(flow.findtext(tag, "0"))
        flows.append(
            {
                "flow": name,
                "request_count": try_int("Request_Count"),
                "iops": try_float("IOPS"),
                "device_resp_us": try_float("Device_Response_Time"),
                "end_to_end_us": try_float("End_to_End_Request_Delay"),
                "max_device_resp_us": try_float("Max_Device_Response_Time"),
                "max_end_to_end_us": try_float("Max_End_to_End_Request_Delay"),
            }
        )
    return flows


def collect_records(root: Path):
    records = []
    for policy_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        policy = policy_dir.name
        for workload_dir in sorted(p for p in policy_dir.iterdir() if p.is_dir()):
            workload = workload_dir.name
            xml_files = sorted(workload_dir.glob("*_scenario_*.xml"))
            if not xml_files:
                # No XML captured; skip.
                continue
            xml_path = xml_files[0]
            for flow in read_flows(xml_path):
                records.append(
                    {
                        "policy": policy,
                        "workload": workload,
                        **flow,
                    }
                )
    return records


def add_slowdown(records):
    """Compute slowdown vs best (min device_resp_us) per (workload, flow)."""
    best = {}
    for r in records:
        key = (r["workload"], r["flow"])
        best[key] = min(best.get(key, float("inf")), r["device_resp_us"])
    for r in records:
        key = (r["workload"], r["flow"])
        baseline = best.get(key, 0.0) or 1.0
        r["slowdown_vs_best"] = r["device_resp_us"] / baseline
    # Tail (max) slowdown vs best tail
    best_tail = {}
    for r in records:
        key = (r["workload"], r["flow"])
        best_tail[key] = min(best_tail.get(key, float("inf")), r.get("max_device_resp_us", float("inf")))
    for r in records:
        key = (r["workload"], r["flow"])
        baseline = best_tail.get(key, 0.0) or 1.0
        r["slowdown_vs_best_tail"] = r.get("max_device_resp_us", 0.0) / baseline


def add_iops_share(records):
    """Compute per-workload IOPS share for each flow."""
    totals = {}
    for r in records:
        totals[r["workload"]] = totals.get(r["workload"], 0.0) + r["iops"]
    for r in records:
        total = totals.get(r["workload"], 0.0) or 1.0
        r["iops_share"] = r["iops"] / total


def write_csv(records, output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "policy",
        "workload",
        "flow",
        "request_count",
        "iops",
        "device_resp_us",
        "end_to_end_us",
        "max_device_resp_us",
        "max_end_to_end_us",
        "iops_share",
        "slowdown_vs_best",
        "slowdown_vs_best_tail",
    ]
    with output_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)


def main():
    args = parse_args()
    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        print(f"Root not found: {root}", file=sys.stderr)
        return 1
    output = Path(args.output).expanduser().resolve() if args.output else root / "summary.csv"

    records = collect_records(root)
    if not records:
        print("No records found; make sure results exist and XML files are captured.", file=sys.stderr)
        return 1
    add_slowdown(records)
    add_iops_share(records)
    write_csv(records, output)
    print(f"Wrote summary to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

