# SSD 调度算法学术参考文献

## 核心论文

### 1. DRR (Deficit Round Robin)
**原始论文**: Shreedhar & Varghese, "Efficient Fair Queuing Using Deficit Round-Robin", IEEE/ACM Transactions on Networking, 1996

**核心思想**:
- 每个流维护一个 deficit counter
- 每轮增加 quantum 到 deficit
- 只有当 deficit >= packet_size 时才能发送
- 发送后从 deficit 中减去 packet_size

**评估指标**:
- **Byte Fairness**: 每用户传输字节数应相等
- **公式**: `Jain_Index(bytes_per_user)`

**验证方法**:
```
场景: 用户A发送1000个4KB请求，用户B发送100个40KB请求
预期: 两用户最终传输字节数相近 (4MB vs 4MB)
DRR应该: 字节公平 (Jain > 0.9)
RR应该: 请求公平但字节不公平
```

### 2. WFQ/QFQ (Weighted Fair Queuing)
**原始论文**: 
- Demers et al., "Analysis and Simulation of a Fair Queueing Algorithm", ACM SIGCOMM 1989
- Fabio Checconi et al., "QFQ: Efficient Packet Scheduling with Tight Guarantees", IEEE/ACM ToN 2013

**核心思想**:
- 使用虚拟时间 (virtual time) 调度
- 每个包计算 finish_tag = start_tag + size/weight
- 选择 finish_tag 最小的包发送

**评估指标**:
- **Weighted Fair Share**: 实际吞吐与权重成比例
- **公式**: `actual_throughput[i] / weight[i]` 应该相等

**验证方法**:
```
场景: 用户A权重=2，用户B权重=1，相同请求
预期: 用户A吞吐量 ≈ 2 × 用户B吞吐量
```

### 3. FLIN (Fairness-aware Latency Interference Normalizer)
**论文**: Tavakkol et al., "FLIN: Enabling Fairness and Enhancing Performance in Modern NVMe SSDs", ISCA 2018

**核心思想**:
- 三阶段调度: Queue Insertion → Queue Arbitration → Transaction Selection
- 基于 slowdown 估计进行公平调度
- 保护读延迟免受写干扰

**评估指标**:
- **Slowdown Fairness**: `F = min(S_i) / max(S_i)`
- 其中 `S_i = RT_shared / RT_alone`

**验证方法**:
```
场景: 纯读用户 vs 纯写用户
预期: 所有用户的 slowdown 应该相近
FLIN应该: F 接近 1
RR应该: 读用户 slowdown 远大于写用户
```

### 4. MQFQ (Multi-Queue Fair Queueing)
**论文**: Hedayati et al., "Multi-Queue Fair Queueing", USENIX ATC 2019

**核心思想**:
- 扩展 Start-time Fair Queueing 到 NVMe 多队列
- 处理多队列的公平性问题

### 5. D2FQ (Device-Direct Fair Queueing)
**论文**: Woo et al., "D2FQ: Device-Direct Fair Queueing for NVMe SSDs", FAST 2021

**核心思想**:
- 在设备端实现公平调度
- 无需主机参与

## 评估指标对照表

| 算法 | 主要指标 | 公式 | 目标值 |
|------|---------|------|--------|
| RR | Request Fairness | `Jain(requests/user)` | → 1.0 |
| DRR | Byte Fairness | `Jain(bytes/user)` | → 1.0 |
| QFQ | Weighted Share | `throughput[i]/weight[i]` | 各用户相等 |
| FLIN | Slowdown Fairness | `min(S)/max(S)` | → 1.0 |

## 验证测试场景

### 场景1: DRR 验证 (字节公平)
```
用户0: 10000 × 4KB = 40MB
用户1: 1000 × 40KB = 40MB
用户2: 400 × 100KB = 40MB
用户3: 100 × 400KB = 40MB

预期结果:
- DRR: 所有用户吞吐相近 (Jain > 0.95)
- RR: 用户0吞吐最高 (获得最多请求机会)
```

### 场景2: QFQ 验证 (加权公平)
```
权重: [4, 2, 1, 1]
相同请求模式

预期结果:
- QFQ: 吞吐比例 ≈ 4:2:1:1
- 其他: 吞吐比例 ≈ 1:1:1:1
```

### 场景3: FLIN 验证 (Slowdown 公平)
```
用户0,1: 纯读 (100% READ)
用户2,3: 纯写 (100% WRITE, 大请求)

预期结果:
- FLIN: 所有用户 slowdown 相近 (F > 0.5)
- RR: 读用户 slowdown >> 写用户 slowdown
```

## 参考资料

1. [FLIN Paper](https://loisorosa.github.io/files/pdf/flin.pdf)
2. [MQFQ Paper](https://www.cs.rochester.edu/u/scott/papers/2019_ATC_MQFQ.pdf)
3. [D2FQ Paper](https://www.usenix.org/system/files/fast21-woo.pdf)
4. [DRR RFC 2697](https://tools.ietf.org/html/rfc2697)

