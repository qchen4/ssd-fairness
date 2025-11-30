# SSD 调度算法自动选择逻辑

## 概述

本文档描述了 `--scheduler auto` 功能的算法选择逻辑。该功能会分析输入的工作负载特征，自动选择最适合的调度算法。

## 支持的算法

| 算法 | 全称 | 优化目标 | 最佳评估指标 |
|------|------|---------|-------------|
| **RR** | Round Robin | 请求级公平 | 请求数公平 |
| **DRR** | Deficit Round Robin | 字节级公平 | 吞吐量公平 (Jain Index) |
| **QFQ** | Quick Fair Queuing | 加权公平 | 加权吞吐比例 |
| **FLIN** | Fairness-aware Latency Interference Normalizer | Slowdown 平衡 | F = min(S)/max(S) |

## 工作负载特征分析

系统会分析以下特征：

```cpp
struct WorkloadProfile {
    int num_users;              // 用户数量
    size_t total_requests;      // 总请求数
    uint32_t min_size;          // 最小请求大小
    uint32_t max_size;          // 最大请求大小
    double size_ratio;          // 大小比例 (max/min)
    double overall_read_ratio;  // 整体读比例
    double read_ratio_variance; // 用户间读写差异
    bool has_pure_read_user;    // 是否有纯读用户 (>95% 读)
    bool has_pure_write_user;   // 是否有纯写用户 (<5% 读)
    bool has_burst;             // 是否有突发 (同时到达)
};
```

## 选择规则 (评分系统)

### 规则表

| # | 条件 | RR | DRR | QFQ | FLIN | 说明 |
|---|------|-----|-----|-----|------|------|
| 1 | `size_ratio > 16` | - | +3.0 | +2.5 | - | 极端大小差异 |
| 2 | `size_ratio > 4` | - | +2.0 | +1.5 | - | 中等大小差异 |
| 3 | `size_ratio ≤ 4` | +1.0 | - | - | - | 大小均匀 |
| 4 | `rw_variance > 0.1` | - | - | - | +3.0 | 读写差异大 |
| 5 | `rw_variance > 0.05` | - | - | - | +1.5 | 读写有差异 |
| 6 | 纯读+纯写用户 | - | - | - | +2.0 | 极端读写分离 |
| 7 | 简单场景 | +1.5 | - | - | - | 小差异+低方差 |
| 8 | 指定权重 | - | - | +5.0 | - | 需要加权服务 |
| 9 | 突发+大小差异>2x | - | - | +2.0 | - | 高竞争场景 |
| 10 | 多用户(>4)+差异>4x | - | - | +1.5 | - | 多流扩展 |

### 选择流程图

```
                    ┌─────────────────┐
                    │ 分析工作负载特征 │
                    └────────┬────────┘
                             │
         ┌───────────────────┼───────────────────┐
         ▼                   ▼                   ▼
    ┌─────────┐        ┌─────────┐        ┌─────────┐
    │指定权重?│        │大小差异?│        │读写差异?│
    └────┬────┘        └────┬────┘        └────┬────┘
         │                  │                  │
    Yes──┼──► QFQ      >16x─┼──► DRR      >0.1─┼──► FLIN
         │                  │                  │
         ▼             >4x──┼──► DRR/QFQ       ▼
    ┌─────────┐             │             ┌─────────┐
    │ 突发？  │        ≤4x──┼──► RR       │纯读/写? │
    └────┬────┘             │             └────┬────┘
         │                  │                  │
    Yes + 差异>2x ──► QFQ   │             Yes──┼──► FLIN
                            ▼                  │
                    ┌─────────────┐            ▼
                    │ 多用户(>4)? │       否──► 继续
                    └──────┬──────┘
                           │
                    Yes + 差异>4x ──► QFQ
```

## 使用方法

### 基本用法
```bash
# 自动选择算法
./ssd-fairness --trace workload.csv --scheduler auto
```

### 指定权重 (强制 QFQ)
```bash
# 用户0权重=2, 其他用户权重=1
./ssd-fairness --trace workload.csv --scheduler auto --weights 2,1,1,1
```

### 输出示例
```
=== Auto Algorithm Selection ===
Workload Analysis:
  Users: 4
  Requests: 10000
  Size range: 4096 - 262144 (64x)
  Read ratio: 50%
  R/W variance: 0.0001
  Pure read user: no
  Pure write user: no
  Burst detected: no

Selected algorithm: drr
Auto quantum for DRR: 32768 bytes
================================
```

## 各算法最佳场景

### RR (Round Robin)
- 请求大小均匀 (ratio < 2x)
- 用户负载对称
- 无需特殊配置

### DRR (Deficit Round Robin)
- 请求大小差异大 (ratio > 4x)
- 需要字节级公平
- 防止大请求用户霸占带宽

### QFQ (Quick Fair Queuing)
- 需要加权公平分配
- 高竞争突发场景
- 多用户 + 大小差异

### FLIN (Fairness-aware LIN)
- 读写比例不对称
- 需要保护读延迟
- 有纯读/纯写用户混合

## 参考文献

1. FLIN - "Enabling Fairness and Enhancing Performance in Modern NVMe SSDs", ISCA 2018
2. MQFQ - "Multi-Queue Fair Queueing", USENIX ATC 2019
3. D2FQ - "Device-Direct Fair Queueing for NVMe SSDs", FAST 2021

