# 四种 SSD 调度算法极端场景分析

## 概述

本文档总结了四种 SSD 调度算法在极端场景下的表现差异。

## 核心发现

### 1. DRR (Deficit Round Robin) - **明星场景**

**场景**: 请求大小差异极大 (4KB vs 256KB = 64倍差异)

| 算法 | Avg Latency | 改进 |
|------|-------------|------|
| RR   | 0.0540s     | 基准 |
| **DRR** | **0.0041s** | **↓92.3%** |
| QFQ  | 0.0042s     | ↓92.2% |
| FLIN | 0.0042s     | ↓92.2% |

**结论**: 当请求大小差异大时，DRR 的字节级公平机制可以显著降低平均延迟。

**原因**: RR 按请求轮转，小请求用户获得更多调度机会。DRR 按字节累积 deficit，确保大请求用户也能公平获得带宽。

### 2. QFQ (Quick Fair Queuing)

**当前状态**: 未能充分体现优势

**原因**: 
- 当前实现默认所有用户权重 = 1.0
- 没有命令行参数设置权重
- 因此 QFQ 与 DRR 表现相似

**优势场景** (需要实现):
- 不同用户不同权重 (如 VIP 用户权重 = 2)
- 需要精确比例分配的场景

### 3. FLIN (Fairness-aware Latency Interference Normalizer)

**场景**: 写风暴攻击 (3读用户 vs 1疯狂写用户)

| 算法 | Avg Latency | 改进 |
|------|-------------|------|
| RR   | 0.3690s     | 基准 |
| FLIN | 0.3480s     | ↓5.7% |

**注意**: 
- FLIN 优化的是**延迟**，不是**公平性**
- 用 `combined_fairness` 评估 FLIN 是**错误的**
- 应该用 `avg_latency` 或单独的 `read_latency` 评估

### 4. RR (Round Robin)

**最佳场景**: 请求完全均匀 (相同大小、相同到达率)

在此场景下，所有算法表现相同 (combined_fairness = 1.0)。RR 最简单高效。

## 评估指标选择

| 算法 | 正确评估指标 | 错误评估指标 |
|------|-------------|-------------|
| RR   | combined_fairness | - |
| DRR  | throughput_fairness, avg_latency | - |
| QFQ  | weighted_throughput (需实现) | - |
| FLIN | **avg_latency**, read_latency | combined_fairness ❌ |

## 极端场景 Trace

位置: `traces/contention/`

1. `contention_rr_uniform.csv` - RR 场景 (均匀请求)
2. `contention_drr_size_gap.csv` - DRR 场景 (256x 大小差异)
3. `contention_qfq_simultaneous.csv` - QFQ 场景 (同时突发)
4. `contention_flin_write_storm.csv` - FLIN 场景 (写风暴)

## 运行测试

```powershell
# DRR 场景 (sqrt quantum)
.\build\Release\ssd-fairness.exe --trace traces/contention/contention_drr_size_gap.csv --scheduler drr --quantum 32768

# FLIN 场景
.\build\Release\ssd-fairness.exe --trace traces/contention/contention_flin_write_storm.csv --scheduler flin
```

## 结论

1. **DRR 是最具区分度的场景** - 在大小差异场景下延迟改进 92%+
2. **FLIN 需要正确的评估指标** - 用延迟而非公平性
3. **QFQ 需要权重功能** - 当前实现未能体现优势
4. **RR 适用于均匀场景** - 简单高效

## 后续工作

1. 为 QFQ 添加权重命令行参数
2. 实现 read_latency 单独指标
3. 创建更多极端 FLIN 场景

