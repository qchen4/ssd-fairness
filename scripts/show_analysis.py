#!/usr/bin/env python3
import json

with open('results/algorithm_analysis.json') as f:
    data = json.load(f)

interesting = ['s02_size_8x', 'flin_v1_pure_rw', 'drr_v2_size_256x']

for name in interesting:
    for a in data['analyses']:
        if a['trace'] == name:
            f = a['features']
            print(f'\n=== {name} ===')
            print(f"size_ratio={f['size_ratio']:.1f}x, rw_var={f['rw_variance']:.3f}")
            print(f"pure_read={f['has_pure_read']}, pure_write={f['has_pure_write']}")
            print()
            print('         Request    Byte       Latency    Slowdown')
            for algo in ['rr', 'drr', 'qfq', 'flin']:
                m = a['metrics'][algo]
                print(f"  {algo.upper():5} {m['request']:.4f}     {m['byte']:.4f}     {m['latency']:.4f}     {m['slowdown']:.4f}")
            print(f"\nBest: req={a['best_for']['request']}, byte={a['best_for']['byte']}, lat={a['best_for']['latency']}, slow={a['best_for']['slowdown']}")
            break

