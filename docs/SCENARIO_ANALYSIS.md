# SSD 调度算法场景分析

本文档详细说明四种调度算法的最优应用场景及测试方案。

## 目录

1. [算法场景映射](#算法场景映射)
2. [场景详细说明](#场景详细说明)
3. [使用方法](#使用方法)
4. [预期结果](#预期结果)

---

## 算法场景映射

| 算法 | 最优场景 | 为什么最优 |
|------|---------|-----------|
| **RR** | 请求大小均匀 | 简单高效，大小相同时按请求数=按字节 |
| **DRR** | 请求大小差异大 | deficit 机制确保字节级公平 |
| **WFQ/QFQ** | 高竞争、需要精确比例 | 虚拟时间标签确保精确公平 |
| **FLIN** | 读写混合、需要保护读 | 读写感知 + 流量节流 |

---

## 场景详细说明

### 1. RR 最优场景

#### 场景 1a: `rr_optimal_uniform`
- **描述**: 4个用户，完全相同的请求大小(4KB)和到达率
- **为什么 RR 最优**:
  - 请求大小相同 → 按请求数公平 = 按字节公平
  - 无需复杂算法，RR 开销最低
  - DRR/WFQ 的额外机制无收益

```
用户0: [4KB] [4KB] [4KB] ...  间隔: 80-120μs
用户1: [4KB] [4KB] [4KB] ...  间隔: 80-120μs
用户2: [4KB] [4KB] [4KB] ...  间隔: 80-120μs
用户3: [4KB] [4KB] [4KB] ...  间隔: 80-120μs
```

#### 场景 1b: `rr_optimal_similar`
- **描述**: 4个用户，请求大小相同但到达率略有差异
- **预期**: RR 仍然表现最好

---

### 2. DRR 最优场景

#### 场景 2a: `drr_optimal_size_disparity`
- **描述**: 极端的请求大小差异
  - 用户0,1: 小请求 (4KB), 高频
  - 用户2,3: 大请求 (128KB), 低频
- **为什么 DRR 最优**:
  - RR 会让大请求用户获得 32x 带宽（不公平）
  - DRR 的 deficit 机制确保字节级公平
  
```
用户0: [4KB] [4KB] [4KB] ...     间隔: 10-30μs (高频)
用户1: [4KB] [4KB] [4KB] ...     间隔: 10-30μs (高频)
用户2: [128KB] [128KB] ...       间隔: 100-300μs (低频)
用户3: [128KB] [128KB] ...       间隔: 100-300μs (低频)
```

#### 场景 2b: `drr_optimal_mixed_sizes`
- **描述**: 某些用户请求大小混合
- **预期**: DRR 自动适应不同大小

#### 场景 2c: `drr_optimal_bandwidth_hog`
- **描述**: 一个"带宽霸占者" vs 多个轻量用户
- **预期**: DRR 抑制霸占者，保护轻量用户

---

### 3. WFQ 最优场景

#### 场景 3a: `wfq_optimal_high_contention`
- **描述**: 4个用户持续高负载竞争
- **为什么 WFQ 最优**:
  - 持续竞争需要精确公平分配
  - 虚拟时间确保延迟可预测
  - DRR 可能因量子大小导致延迟波动

```
所有用户: 高频请求，持续竞争带宽
          请求大小: 4KB-16KB 混合
          间隔: 5-20μs
```

#### 场景 3b: `wfq_optimal_burst_vs_steady`
- **描述**: 一个突发用户 vs 多个稳定用户
- **预期**: WFQ 不会让突发用户饿死其他人

#### 场景 3c: `wfq_optimal_latency_mix`
- **描述**: 6个用户的延迟敏感混合负载
- **预期**: WFQ 提供最可预测的延迟

---

### 4. FLIN 最优场景

#### 场景 4a: `flin_optimal_rw_asymmetry`
- **描述**: 读密集用户 vs 写密集用户
  - 用户0,1: 95% 读
  - 用户2,3: 90% 写
- **为什么 FLIN 最优**:
  - 写操作对 SSD 影响更大（触发 GC、更慢）
  - FLIN 自动惩罚写密集用户
  - 保护读用户的延迟

```
用户0: [READ 4KB] [READ 4KB] ...  95% 读
用户1: [READ 4KB] [READ 4KB] ...  95% 读
用户2: [WRITE 8KB] [WRITE 32KB] ... 90% 写
用户3: [WRITE 8KB] [WRITE 32KB] ... 90% 写
```

#### 场景 4b: `flin_optimal_protect_reads`
- **描述**: 一个"坏公民"（高流量写）vs 多个轻量读用户
- **预期**: FLIN 节流坏公民，保护读用户

#### 场景 4c: `flin_optimal_gc_scenario`
- **描述**: 模拟 GC 触发场景
  - 先大量写（触发 GC）
  - 后续读用户需要保护
- **预期**: FLIN 的流量追踪帮助恢复公平

#### 场景 4d: `flin_optimal_realistic_mix`
- **描述**: 真实混合工作负载
  - OLTP 用户: 小读
  - 分析用户: 大读
  - 日志用户: 顺序写
  - 备份用户: 大写
- **预期**: FLIN 综合处理最优

---

### 5. 挑战场景（测试算法弱点）

| 场景 | 描述 | 预期失败者 | 预期胜者 |
|------|------|-----------|---------|
| `challenge_rr_fail_size` | 4KB vs 512KB | RR | DRR |
| `challenge_drr_fail_latency` | 极高竞争需要精确延迟 | DRR | WFQ |
| `challenge_wfq_fail_rw` | 100% 写 vs 100% 读 | WFQ | FLIN |
| `challenge_flin_fail_uniform` | 完全均匀负载 | FLIN（复杂无收益） | RR |

---

## 使用方法

### 步骤 1: 生成场景 trace

```bash
python scripts/scenario_traces.py
```

生成的文件位于 `traces/scenarios/`

### 步骤 2: 编译模拟器

**Windows (Visual Studio):**
```powershell
mkdir build
cd build
cmake ..
cmake --build . --config Release
```

**Linux/Mac:**
```bash
mkdir -p build && cd build
cmake ..
make
```

### 步骤 3: 运行场景测试

```bash
python scripts/run_scenario_tests.py --traces traces/scenarios
```

### 步骤 4: 查看报告

- 文本报告: `results/scenario_analysis/report.txt`
- CSV 汇总: `results/scenario_analysis/summary.csv`

---

## 预期结果

理想情况下，每种算法应该在其最优场景中获胜：

| 场景类别 | 预期最优算法 | Fairness 预期 |
|---------|-------------|--------------|
| `rr_optimal_*` | RR | ~1.0 (完美公平) |
| `drr_optimal_*` | DRR | ~0.9-1.0 |
| `wfq_optimal_*` | QFQ | ~0.9-1.0 |
| `flin_optimal_*` | FLIN | ~0.8-1.0 |

### 如何解读报告

```
场景: drr_optimal_size_disparity
预期最优: DRR, 实际最优: DRR [✓]    ← 预期匹配
Fairness 得分:
  RR   : 0.6234                      ← RR 在此场景表现差
  DRR  : 0.9876 ★                    ← DRR 获胜
  QFQ  : 0.9654
  FLIN : 0.9123
```

### 结果分析建议

1. **匹配率 > 80%**: 算法行为符合预期
2. **匹配率 50-80%**: 需要分析不匹配的场景
3. **匹配率 < 50%**: 可能存在实现问题或场景设计问题

---

## 后续工作

1. **整合算法设计**: 基于场景测试结果，设计综合各算法优点的 Hybrid 调度器
2. **参数调优**: 为每种算法找到最优参数
3. **真实 trace 验证**: 使用真实 SSD trace 验证场景分析的准确性

