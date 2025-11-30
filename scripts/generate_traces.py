#!/usr/bin/env python3
"""
Synthetic trace generator for the SSD fairness simulator.

Produces a suite of workloads with varied characteristics:
- Small/medium/large traces
- High-throughput vs. low-throughput mixes
- Read-heavy, write-heavy, and balanced mixes
- Adversarial patterns (tiny I/Os vs. large sequential I/Os)

Traces are emitted under test_data/traces by default for repeatable testing.
"""

import argparse
import csv
import random
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


def generate_stream(
    user_id: int,
    count: int,
    gap_range: Tuple[int, int],
    size_choices: Iterable[int],
    read_ratio: float,
    rng: random.Random,
    start_ts: int = 0,
    process_label: str = "",
) -> List[Dict]:
    ts = start_ts
    addr = 0
    rows = []
    label = process_label or f"tenant{user_id}"
    for _ in range(count):
        ts += rng.randint(gap_range[0], gap_range[1])
        size = rng.choice(list(size_choices))
        op = "READ" if rng.random() < read_ratio else "WRITE"
        rows.append(
            {
                "timestamp": ts,
                "process_id": label,
                "user_id": user_id,
                "type": op,
                "address": hex(addr),
                "size": size,
            }
        )
        addr += size
    return rows


def write_trace(rows: List[Dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["timestamp", "process_id", "user_id", "type", "address", "size"]
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def build_workloads(seed: int) -> Dict[str, List[Dict]]:
    rng = random.Random(seed)
    workloads: Dict[str, List[Dict]] = {}

    workloads["small_mixed"] = []
    for uid in range(3):
        workloads["small_mixed"].extend(
            generate_stream(uid, 20, (50, 200), [4096, 8192], 0.6, rng)
        )

    workloads["medium_balanced"] = []
    for uid in range(4):
        workloads["medium_balanced"].extend(
            generate_stream(uid, 80, (20, 120), [4096, 4096 * 4], 0.5, rng)
        )

    workloads["large_bursty"] = []
    for uid in range(6):
        workloads["large_bursty"].extend(
            generate_stream(uid, 200, (5, 80), [4096, 8192, 16384], 0.55, rng)
        )

    workloads["high_vs_low"] = []
    workloads["high_vs_low"].extend(
        generate_stream(0, 120, (2, 15), [4096], 0.7, rng, process_label="highrate")
    )
    workloads["high_vs_low"].extend(
        generate_stream(1, 40, (150, 400), [16384], 0.7, rng, process_label="lowrate")
    )

    workloads["read_heavy"] = []
    for uid in range(3):
        workloads["read_heavy"].extend(
            generate_stream(uid, 60, (30, 120), [4096, 8192], 0.9, rng)
        )

    workloads["write_heavy"] = []
    for uid in range(3):
        workloads["write_heavy"].extend(
            generate_stream(uid, 60, (30, 120), [4096, 8192, 32768], 0.1, rng)
        )

    workloads["balanced_rw"] = []
    for uid in range(4):
        workloads["balanced_rw"].extend(
            generate_stream(uid, 70, (40, 200), [4096, 12288], 0.5, rng)
        )

    # Adversarial: tenant0 issues tiny 4K ops rapidly, tenant1 issues large 128K
    # sequential writes slowly.
    workloads["adversarial"] = []
    workloads["adversarial"].extend(
        generate_stream(0, 160, (1, 10), [4096], 0.8, rng, process_label="tiny-ops")
    )
    workloads["adversarial"].extend(
        generate_stream(1, 40, (200, 600), [131072], 0.2, rng, process_label="bulk-ops")
    )

    for rows in workloads.values():
        rows.sort(key=lambda r: (r["timestamp"], r["user_id"]))
    return workloads


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic traces")
    parser.add_argument("--output-dir", default="test_data/traces", help="Directory for generated CSV traces")
    parser.add_argument("--seed", type=int, default=42, help="Base random seed")
    parser.add_argument(
        "--workloads",
        nargs="*",
        default=["all"],
        help="Subset of workloads to emit (default: all)",
    )
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    workloads = build_workloads(args.seed)
    requested = set(args.workloads)
    if "all" in requested:
        requested = set(workloads.keys())

    for name, rows in workloads.items():
        if name not in requested:
            continue
        path = out_dir / f"{name}.csv"
        write_trace(rows, path)
        print(f"Wrote {path} ({len(rows)} requests)")


if __name__ == "__main__":
    main()
