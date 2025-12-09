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
    random_access: bool = False,
) -> List[Dict]:
    ts = start_ts
    addr = 0
    rows = []
    label = process_label or f"tenant{user_id}"
    for _ in range(count):
        ts += rng.randint(gap_range[0], gap_range[1])
        size = rng.choice(list(size_choices))
        op = "READ" if rng.random() < read_ratio else "WRITE"
        if random_access:
            addr = rng.randint(0, 1 << 20) * 512
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


def write_blktrace(rows: List[Dict], path: Path) -> None:
    """
    Emit a minimal blktrace-like text file using queue (Q) events. This is only
    for testing the parser; fields are synthetic but formatted similarly to SNIA samples.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        seq = 0
        for row in rows:
            seq += 1
            # Pretend all I/Os hit device 8,0 on CPU 0.
            ts_seconds = row["timestamp"] / 1_000_000.0
            pid = row["process_id"]
            lba = int(row["address"], 16) // 512
            sectors = row["size"] // 512
            action = "Q"
            rwbs = "W" if row["type"].upper() == "WRITE" else "R"
            f.write(f"8,0 0 {seq} {ts_seconds:.6f} {pid} {action} {rwbs} {lba} + {sectors} [{pid}]\n")


def build_high_vs_low_pattern(repeats: int = 10) -> List[Dict]:
    """
    Deterministic high-vs-low workload following the user-specified pattern:
    four tenants (highrate, medrate, lowrate, background) with fixed user_ids
    0..3, sequential hex addresses, and hand-crafted timestamps.

    The base pattern below is repeated |repeats| times with a constant
    timestamp offset so the overall trace is longer but each block keeps the
    same relative structure.
    """
    base_rows = [
        # timestamp, process_id, user_id, type, address, size
        (0, "highrate", 0, "READ", "0x00000000", 4096),
        (1, "highrate", 0, "READ", "0x00001000", 4096),
        (2, "highrate", 0, "READ", "0x00002000", 4096),
        (3, "medrate", 1, "WRITE", "0x00100000", 8192),
        (5, "lowrate", 2, "READ", "0x10000000", 4096),
        (6, "background", 3, "WRITE", "0x20000000", 32768),
        (7, "highrate", 0, "READ", "0x00003000", 4096),
        (8, "highrate", 0, "READ", "0x00004000", 4096),
        (10, "highrate", 0, "WRITE", "0x00005000", 4096),
        (11, "medrate", 1, "READ", "0x00102000", 8192),
        (12, "highrate", 0, "READ", "0x00006000", 4096),
        (13, "highrate", 0, "READ", "0x00007000", 4096),
        (15, "lowrate", 2, "WRITE", "0x10002000", 4096),
        (16, "medrate", 1, "WRITE", "0x00104000", 8192),
        (17, "background", 3, "WRITE", "0x20008000", 65536),
        (20, "highrate", 0, "READ", "0x00008000", 4096),
        (21, "highrate", 0, "READ", "0x00009000", 4096),
        (22, "medrate", 1, "READ", "0x00106000", 8192),
        (23, "highrate", 0, "WRITE", "0x0000A000", 4096),
        (25, "lowrate", 2, "READ", "0x10004000", 4096),
        (26, "highrate", 0, "READ", "0x0000B000", 4096),
        (27, "background", 3, "WRITE", "0x20010000", 32768),
        (30, "highrate", 0, "READ", "0x0000C000", 4096),
        (31, "highrate", 0, "READ", "0x0000D000", 4096),
        (32, "highrate", 0, "READ", "0x0000E000", 4096),
        (33, "medrate", 1, "WRITE", "0x00108000", 8192),
        (35, "background", 3, "WRITE", "0x20020000", 65536),
        (36, "highrate", 0, "WRITE", "0x0000F000", 4096),
        (37, "lowrate", 2, "READ", "0x10006000", 4096),
        (40, "highrate", 0, "READ", "0x00010000", 4096),
        (41, "highrate", 0, "READ", "0x00011000", 4096),
        (42, "highrate", 0, "READ", "0x00012000", 4096),
        (43, "medrate", 1, "READ", "0x0010A000", 8192),
        (45, "medrate", 1, "WRITE", "0x0010C000", 8192),
        (46, "background", 3, "WRITE", "0x20030000", 32768),
        (47, "highrate", 0, "READ", "0x00013000", 4096),
        (48, "highrate", 0, "READ", "0x00014000", 4096),
        (50, "lowrate", 2, "WRITE", "0x10008000", 4096),
        (52, "highrate", 0, "WRITE", "0x00015000", 4096),
        (53, "background", 3, "WRITE", "0x20038000", 65536),
        (55, "highrate", 0, "READ", "0x00016000", 4096),
        (56, "medrate", 1, "READ", "0x0010E000", 8192),
        (58, "highrate", 0, "READ", "0x00017000", 4096),
        (60, "lowrate", 2, "READ", "0x1000A000", 4096),
        (61, "background", 3, "WRITE", "0x20040000", 32768),
        (62, "highrate", 0, "READ", "0x00018000", 4096),
        (63, "highrate", 0, "READ", "0x00019000", 4096),
        (65, "medrate", 1, "WRITE", "0x00110000", 16384),
        (67, "highrate", 0, "READ", "0x0001A000", 4096),
    ]

    rows: List[Dict] = []
    # Use a large timestamp offset so blocks don't overlap in time.
    ts_block = 100
    for rep in range(repeats):
        offset = rep * ts_block
        for ts, pid, uid, op, addr, size in base_rows:
            rows.append(
                {
                    "timestamp": ts + offset,
                    "process_id": pid,
                    "user_id": uid,
                    "type": op,
                    "address": addr,
                    "size": size,
                }
            )
    return rows


def build_workloads(seed: int, random_access: bool, inject_gc: bool) -> Dict[str, List[Dict]]:
    rng = random.Random(seed)
    workloads: Dict[str, List[Dict]] = {}

    workloads["small_mixed"] = []
    for uid in range(3):
        workloads["small_mixed"].extend(
            generate_stream(uid, 20, (50, 200), [4096, 8192], 0.6, rng, random_access=random_access)
        )

    workloads["medium_balanced"] = []
    for uid in range(4):
        workloads["medium_balanced"].extend(
            generate_stream(uid, 80, (20, 120), [4096, 4096 * 4], 0.5, rng, random_access=random_access)
        )

    workloads["large_bursty"] = []
    for uid in range(6):
        workloads["large_bursty"].extend(
            generate_stream(uid, 200, (5, 80), [4096, 8192, 16384], 0.55, rng, random_access=random_access)
        )

    # Skewed workload: four tenants with fixed labels and user_ids 0..3,
    # following a hand-crafted high/med/low/background pattern.
    workloads["high_vs_low"] = build_high_vs_low_pattern(repeats=25)

    workloads["read_heavy"] = []
    for uid in range(3):
        workloads["read_heavy"].extend(
            generate_stream(uid, 60, (30, 120), [4096, 8192], 0.9, rng, random_access=random_access)
        )

    workloads["write_heavy"] = []
    for uid in range(3):
        workloads["write_heavy"].extend(
            generate_stream(uid, 60, (30, 120), [4096, 8192, 32768], 0.1, rng, random_access=random_access)
        )

    workloads["balanced_rw"] = []
    for uid in range(4):
        workloads["balanced_rw"].extend(
            generate_stream(uid, 70, (40, 200), [4096, 12288], 0.5, rng, random_access=random_access)
        )

    # Adversarial: tenant0 issues tiny 4K ops rapidly, tenant1 issues large 128K
    # sequential writes slowly.
    workloads["adversarial"] = []
    workloads["adversarial"].extend(
        generate_stream(0, 160, (1, 10), [4096], 0.8, rng, process_label="tiny-ops", random_access=random_access)
    )
    workloads["adversarial"].extend(
        generate_stream(1, 40, (200, 600), [131072], 0.2, rng, process_label="bulk-ops", random_access=random_access)
    )

    for rows in workloads.values():
        if inject_gc:
            rows.append(
                {
                    "timestamp": rows[-1]["timestamp"] + 5000,
                    "process_id": "gc",
                    "user_id": 0,
                    "type": "WRITE",
                    "address": hex(rng.randint(0, 1 << 20) * 512),
                    "size": 256 * 1024,
                }
            )
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
    parser.add_argument(
        "--random-access",
        action="store_true",
        help="Randomize addresses to mimic random access workloads",
    )
    parser.add_argument(
        "--inject-gc",
        action="store_true",
        help="Inject periodic large writes to mimic GC interference",
    )
    parser.add_argument(
        "--blktrace",
        action="store_true",
        help="Also emit a blktrace-formatted file for each workload",
    )
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    workloads = build_workloads(args.seed, args.random_access, args.inject_gc)
    requested = set(args.workloads)
    if "all" in requested:
        requested = set(workloads.keys())

    for name, rows in workloads.items():
        if name not in requested:
            continue
        path = out_dir / f"{name}.csv"
        write_trace(rows, path)
        print(f"Wrote {path} ({len(rows)} requests)")
        if args.blktrace:
            bt_path = out_dir / f"{name}.blktrace"
            write_blktrace(rows, bt_path)
            print(f"Wrote {bt_path} ({len(rows)} requests as blktrace)")


if __name__ == "__main__":
    main()
