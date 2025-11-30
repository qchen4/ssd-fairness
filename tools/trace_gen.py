#!/usr/bin/env python3

"""
trace_gen.py — flexible synthetic workload generator for the SSD fairness simulator.

Generates CSV traces with columns:
    timestamp,process_id,type,address,size

Supports multiple workload shapes (uniform, zipf, hotset, singlehot) so we can
stress-test wear-leveling policies under different access patterns.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import random
from pathlib import Path
from typing import Callable

KB = 1024
BLOCK_SIZE = 4096  # 4 KiB IOs


class ZipfSampler:
    """Lightweight Zipf sampler without external dependencies."""

    def __init__(self, max_rank: int, alpha: float, rng: random.Random):
        if max_rank <= 0:
            raise ValueError("max_rank must be positive")
        if alpha <= 0:
            raise ValueError("zipf alpha must be positive")
        self._rng = rng
        weights = [1.0 / ((rank + 1) ** alpha) for rank in range(max_rank)]
        total = sum(weights)
        cdf = []
        cumsum = 0.0
        for w in weights:
            cumsum += w
            cdf.append(cumsum / total)
        self._cdf = cdf

    def sample(self) -> int:
        target = self._rng.random()
        idx = bisect.bisect_left(self._cdf, target)
        if idx >= len(self._cdf):
            idx = len(self._cdf) - 1
        return idx


def build_lba_sampler(args: argparse.Namespace, rng: random.Random) -> Callable[[], int]:
    max_blocks = max(1, args.max_lba_blocks)
    workload = args.workload.lower()

    if workload == "uniform":
        return lambda: rng.randrange(max_blocks)

    if workload == "zipf":
        max_rank = args.zipf_max_rank if args.zipf_max_rank else max_blocks
        max_rank = max(1, min(max_rank, max_blocks))
        sampler = ZipfSampler(max_rank, args.zipf_alpha, rng)

        def sample_zipf() -> int:
            # Map sampled rank (0-based) into block space.
            return sampler.sample() % max_blocks

        return sample_zipf

    if workload == "hotset":
        hotset_fraction = max(0.0, min(1.0, args.hotset_fraction))
        hotset_size = max(1, int(hotset_fraction * max_blocks))
        cold_size = max_blocks - hotset_size
        hot_prob = max(0.0, min(1.0, args.hotset_hot_prob))

        def sample_hotset() -> int:
            if cold_size <= 0 or rng.random() < hot_prob:
                return rng.randrange(hotset_size)
            return hotset_size + rng.randrange(cold_size)

        return sample_hotset

    if workload == "singlehot":
        return lambda: 0

    raise ValueError(f"Unsupported workload type: {args.workload}")


def generate_trace(args: argparse.Namespace) -> None:
    rng = random.Random(args.seed)
    sampler = build_lba_sampler(args, rng)
    max_blocks = max(1, args.max_lba_blocks)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "process_id", "type", "address", "size"])

        timestamp = 0
        for _ in range(args.requests):
            process_id = f"process{rng.randint(0, max(0, args.processes - 1))}"
            req_type = "WRITE" if rng.random() < args.write_fraction else "READ"
            block_index = sampler()
            block_index = max(0, min(block_index, max_blocks - 1))
            address = block_index * BLOCK_SIZE

            writer.writerow([timestamp, process_id, req_type, address, BLOCK_SIZE])
            timestamp += rng.randint(1, args.interarrival_max)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate synthetic I/O traces")
    parser.add_argument("--processes", type=int, default=4, help="Number of processes/users")
    parser.add_argument("--requests", type=int, default=1000, help="Total requests to emit")
    parser.add_argument("--output", type=str, required=True, help="Output CSV path")
    parser.add_argument("--max-lba-blocks", type=int, default=1 << 20,
                        help="Number of distinct 4KiB blocks (address = block * 4096)")
    parser.add_argument("--write-fraction", type=float, default=1.0,
                        help="Probability that a request is a WRITE (0..1)")
    parser.add_argument("--interarrival-max", type=int, default=1000,
                        help="Maximum timestamp delta between consecutive requests (microseconds)")
    parser.add_argument("--seed", type=int, default=12345, help="PRNG seed")

    parser.add_argument("--workload", choices=["uniform", "zipf", "hotset", "singlehot"],
                        default="uniform", help="Workload model to use")
    parser.add_argument("--zipf-alpha", type=float, default=1.0,
                        help="Exponent for the Zipf workload (zipf only)")
    parser.add_argument("--zipf-max-rank", type=int, default=None,
                        help="Maximum rank to include in the Zipf distribution")
    parser.add_argument("--hotset-fraction", type=float, default=0.01,
                        help="Fraction of address space considered 'hot'")
    parser.add_argument("--hotset-hot-prob", type=float, default=0.9,
                        help="Probability of choosing from the hot set")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    generate_trace(args)


if __name__ == "__main__":
    main()