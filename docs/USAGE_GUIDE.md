# SSD 调度算法选择使用指南

## 快速开始

### 方式一：使用 Python 选择器 (推荐)

```bash
# 分析工作负载并获取推荐
python scripts/algorithm_selector.py <trace.csv> [goal]

# 示例
python scripts/algorithm_selector.py traces/workload.csv          # 自动选择
python scripts/algorithm_selector.py traces/workload.csv byte     # 指定字节公平目标
```

### 方式二：使用模拟器 (编译后)

```bash
# 自动选择
./ssd-fairness --trace workload.csv --scheduler auto

# 指定公平性目标
./ssd-fairness --trace workload.csv --goal request    # 请求公平 → RR
./ssd-fairness --trace workload.csv --goal byte       # 字节公平 → DRR
./ssd-fairness --trace workload.csv --goal latency    # 延迟公平 → QFQ
./ssd-fairness --trace workload.csv --goal slowdown   # 减速公平 → FLIN

# 直接指定算法
./ssd-fairness --trace workload.csv --scheduler drr --quantum 65536
./ssd-fairness --trace workload.csv --scheduler qfq --weights 4,2,1,1
```

## 选择逻辑

### 决策树

```
                        开始
                          │
                ┌─────────▼─────────┐
                │ 用户指定 --goal?   │
                └─────────┬─────────┘
                      Yes │ No
                          │   │
    ┌─────────────────────┘   │
    │ request → RR            │
    │ byte    → DRR           │
    │ latency → QFQ           │
    │ slowdown → FLIN         │
    └─────────────────────────┘
                              │
                ┌─────────────▼─────────────┐
                │ 用户指定 --weights?        │
                └─────────────┬─────────────┘
                          Yes │ No
                    ┌─────────▼─┐    │
                    │   QFQ    │    │
                    └───────────┘    │
                                     ▼
                    ┌─────────────────────┐
                    │ 纯读 + 纯写用户?     │
                    └─────────┬───────────┘
                          Yes │ No
                    ┌─────────▼─┐    │
                    │   FLIN   │    │
                    └───────────┘    │
                                     ▼
                    ┌─────────────────────┐
                    │ 读写差异大?          │
                    │ (variance > 0.1)    │
                    └─────────┬───────────┘
                          Yes │ No
                    ┌─────────▼─┐    │
                    │   FLIN   │    │
                    └───────────┘    │
                                     ▼
                    ┌─────────────────────┐
                    │ 大小差异大?          │
                    │ (ratio > 4x)        │
                    └─────────┬───────────┘
                          Yes │ No
                    ┌─────────▼─┐    │
                    │   DRR    │    │
                    └───────────┘    │
                                     ▼
                    ┌─────────────────────┐
                    │ 突发流量?            │
                    └─────────┬───────────┘
                          Yes │ No
                    ┌─────────▼─┐    │
                    │   QFQ    │    │
                    └───────────┘    │
                                     ▼
                              ┌─────────┐
                              │   RR    │
                              └─────────┘
```

## 公平性目标与算法对应

| 目标 (--goal) | 算法 | 指标 | 适用场景 |
|---------------|------|------|---------|
| `request` | RR | Jain(requests/user) | Web 服务器，API 网关 |
| `byte` | DRR | Jain(bytes/user) | 文件服务器，CDN |
| `latency` | QFQ | Jain(1/latency) | 数据库，OLTP |
| `slowdown` | FLIN | min(S)/max(S) | 云存储，多租户 SSD |

## 工作负载特征检测

选择器会自动检测以下特征：

| 特征 | 检测方法 | 影响 |
|------|---------|------|
| **大小差异** | max_size / min_size | > 4x → DRR/QFQ |
| **读写差异** | per-user R/W variance | > 0.1 → FLIN |
| **纯读用户** | read_ratio > 95% | 存在 → FLIN |
| **纯写用户** | read_ratio < 5% | 存在 → FLIN |
| **突发流量** | 同时到达请求数 | 高 → QFQ |
| **多用户** | user_count > 4 | 多 → QFQ/DRR |

## 示例场景

### 场景 1: 云存储多租户

```bash
# 特征: 不同用户有不同的读写比例
# 推荐: FLIN (保护读延迟)
python scripts/algorithm_selector.py traces/cloud_storage.csv
```

### 场景 2: 大文件传输

```bash
# 特征: 请求大小差异大 (4KB ~ 1MB)
# 推荐: DRR (字节公平)
python scripts/algorithm_selector.py traces/file_transfer.csv
```

### 场景 3: 数据库 OLTP

```bash
# 特征: 需要低延迟，有优先级需求
# 推荐: QFQ (使用权重)
./ssd-fairness --trace traces/oltp.csv --scheduler qfq --weights 4,2,1,1
```

### 场景 4: 简单均匀负载

```bash
# 特征: 所有用户负载相似
# 推荐: RR (简单高效)
python scripts/algorithm_selector.py traces/uniform.csv
```

## 评估结果

运行完成后查看结果:

```bash
# 查看结果 CSV
cat results/results.csv

# 使用多指标评估
python scripts/multi_metric_eval.py

# 生成可视化报告
python scripts/comprehensive_report.py
```

## 参数说明

| 参数 | 说明 | 示例 |
|------|------|------|
| `--trace` | 输入 trace 文件 | `--trace workload.csv` |
| `--scheduler` | 调度算法 | `rr`, `drr`, `qfq`, `flin`, `auto` |
| `--goal` | 公平性目标 | `request`, `byte`, `latency`, `slowdown` |
| `--quantum` | DRR quantum | `--quantum 65536` |
| `--weights` | QFQ 权重 | `--weights 4,2,1,1` |
| `--results` | 输出路径 | `--results out.csv` |

