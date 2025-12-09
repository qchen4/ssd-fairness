# Scheduler Implementation Comparison: Lightweight Simulator vs MQSim

This document provides a high-level overview of how five fairness-oriented schedulers (RR, DRR, QFQ, FLIN, and MINMAX) are implemented in both the Lightweight Simulator and MQSim.

---

## Table of Contents

1. [Round Robin (RR)](#1-round-robin-rr)
2. [Deficit Round Robin (DRR)](#2-deficit-round-robin-drr)
3. [Quick Fair Queueing (QFQ)](#3-quick-fair-queueing-qfq)
4. [FLIN](#4-flin-fairness-via-latency-interference-neutralization)
5. [MinMax Fairness](#5-minmax-fairness-scheduler)

---

## 1. Round Robin (RR)

### Algorithm Overview
Round Robin cycles through flows in a fixed order, serving one request per flow per turn. It provides request-level fairness but can be unfair when request sizes vary significantly.

### Lightweight Simulator Implementation

**Key Components:**
- `RoundRobinScheduler` class
- Per-user FIFO queues (`std::vector<std::deque<Request>>`)
- Round-robin pointer (`next_`) tracking the next user to check

**High-Level Flow:**
1. **Enqueue**: Requests are added to the queue of their user ID
2. **Pick User**: Starting from `next_`, cycle through all users until finding one with pending requests
3. **Pop**: Remove and return the front request from the selected user's queue
4. **Update**: Advance `next_` to the next user position

**Key Code Structure:**
```cpp
class RoundRobinScheduler {
    std::vector<std::deque<Request>> queues_;
    int next_ = 0;  // Next user to check
    
    std::optional<int> pick_user(double) {
        // Cycle through users starting from next_
        // Return first user with non-empty queue
    }
};
```

**Characteristics:**
- Simple and lightweight
- O(n) selection where n is number of users
- No state tracking beyond queue occupancy

### MQSim Implementation

**Key Components:**
- `TSU_RR` class (Transaction Scheduling Unit)
- Separate queues per channel/chip: `UserReadTRQueue`, `UserWriteTRQueue`
- Per-channel/chip round-robin counters: `current_stream_read`, `current_stream_write`
- Additional queues for GC and mapping operations

**High-Level Flow:**
1. **Schedule**: Receives transactions and routes them to appropriate queues (read/write/GC/mapping)
2. **Service Transactions**: For each idle channel/chip:
   - Try to service read transaction
   - If no read, try write transaction
   - If no write, try erase transaction
3. **Round-Robin Selection**: `pick_next_rr_transaction()` cycles through streams in the queue

**Key Code Structure:**
```cpp
class TSU_RR {
    Flash_Transaction_Queue** UserReadTRQueue;  // Per channel/chip
    Flash_Transaction_Queue** UserWriteTRQueue;
    unsigned int** current_stream_read;  // Per channel/chip
    unsigned int** current_stream_write;
    
    NVM_Transaction_Flash* pick_next_rr_transaction(
        Flash_Transaction_Queue& queue, 
        unsigned int& current_stream);
};
```

**Characteristics:**
- More complex due to channel/chip-level parallelism
- Separate tracking for reads and writes
- Handles GC and mapping operations
- Per-channel/chip round-robin state

### Key Differences

| Aspect | Lightweight Simulator | MQSim |
|--------|----------------------|-------|
| **Queue Structure** | Single queue per user | Separate read/write queues per channel/chip |
| **State Tracking** | Single `next_` pointer | Per-channel/chip counters |
| **Complexity** | Simple user-level rotation | Channel/chip-level parallelism |
| **Additional Features** | None | GC, mapping, suspension support |

---

## 2. Deficit Round Robin (DRR)

### Algorithm Overview
DRR provides byte-level fairness by allocating each flow a quantum (default 4KB) per round. A deficit counter accumulates unused credits, allowing larger requests to be serviced when sufficient credit is available.

**Algorithm:**
```
For each flow i in round-robin order:
    D_i = D_i + Q_i  (add quantum to deficit)
    While D_i >= size(next_request(i)):
        schedule request from i
        D_i = D_i - size(request)
```

### Lightweight Simulator Implementation

**Key Components:**
- `DeficitRoundRobinScheduler` class
- Per-user queues and deficit counters (`std::vector<int64_t> deficit_`)
- Per-user weights (`std::vector<double> weights_`)
- Quantum size (default 4096 bytes)
- Round-robin pointer (`next_`)

**High-Level Flow:**
1. **Enqueue**: Add request to user's queue
2. **Pick User**: 
   - Starting from `next_`, cycle through users
   - For each user: add `quantum * weight` to deficit
   - If deficit >= size of front request, select that user
3. **Pop**: Remove request and subtract its size from deficit

**Key Code Structure:**
```cpp
class DeficitRoundRobinScheduler {
    std::vector<std::deque<Request>> queues_;
    std::vector<int64_t> deficit_;  // Byte credits
    std::vector<double> weights_;
    double quantum_ = 4096.0;
    int next_ = 0;
    
    std::optional<int> pick_user(double) {
        for each user starting from next_:
            deficit[uid] += quantum * weights[uid]
            if deficit[uid] >= request.size:
                return uid
    }
};
```

**Characteristics:**
- Byte-level fairness
- Supports per-user weights
- Deficit carries over across rounds
- O(n) selection per scheduling decision

### MQSim Implementation

**Key Components:**
- `TSU_DRR` class
- `FlowState` structure with `deficit` and `weight` per stream
- Separate state for reads and writes: `flow_state_read`, `flow_state_write`
- Per-channel/chip next stream pointers: `next_stream_read`, `next_stream_write`
- Separate queues per channel/chip

**High-Level Flow:**
1. **Schedule**: Route transactions to appropriate queues
2. **Service Transactions**: For each channel/chip:
   - Use `pick_next_drr_transaction()` to select from user queue
   - Add quantum to deficit, find transaction that fits
3. **State Management**: Maintain separate deficit counters for read and write streams

**Key Code Structure:**
```cpp
class TSU_DRR {
    struct FlowState {
        int64_t deficit;
        double weight;
    };
    std::vector<FlowState> flow_state_read;
    std::vector<FlowState> flow_state_write;
    unsigned int** next_stream_read;  // Per channel/chip
    unsigned int** next_stream_write;
    
    NVM_Transaction_Flash* pick_next_drr_transaction(
        Flash_Transaction_Queue& queue,
        std::vector<FlowState>& flow_state,
        unsigned int& next_stream);
};
```

**Characteristics:**
- Separate deficit tracking for reads and writes
- Per-channel/chip state management
- Handles channel-level parallelism
- More complex state management than Lightweight Simulator

### Key Differences

| Aspect | Lightweight Simulator | MQSim |
|--------|----------------------|-------|
| **State Separation** | Unified deficit per user | Separate read/write deficits |
| **Scope** | User-level | Channel/chip-level with stream tracking |
| **Complexity** | Single deficit counter per user | Per-channel/chip state |

---

## 3. Quick Fair Queueing (QFQ)

### Algorithm Overview
QFQ approximates Weighted Fair Queueing (WFQ) by tagging each request with a virtual finish time based on its size and the flow's weight. The scheduler always selects the request with the smallest virtual finish tag, approximating Generalized Processor Sharing (GPS).

**Virtual Finish Time Calculation:**
```
start_tag = max(last_finish[flow], virtual_time)
finish_tag = start_tag + request_size / weight
```

### Lightweight Simulator Implementation

**Key Components:**
- `WeightedFairScheduler` class
- `TaggedRequest` structure (request + finish_tag)
- Per-user tagged queues
- Virtual time tracking (`virtual_time_`)
- Per-user weights and last finish tags

**High-Level Flow:**
1. **Enqueue**: 
   - Calculate virtual start tag = max(last_finish[user], virtual_time)
   - Calculate finish_tag = start_tag + size / weight
   - Store tagged request in user's queue
2. **Pick User**: Select user with smallest front request finish_tag
3. **Pop**: Remove request and advance virtual_time to the finish_tag

**Key Code Structure:**
```cpp
class WeightedFairScheduler {
    struct TaggedRequest {
        Request req;
        double finish_tag;
    };
    std::vector<std::deque<TaggedRequest>> queues_;
    std::vector<double> weights_;
    std::vector<double> last_finish_;
    double virtual_time_ = 0.0;
    
    void enqueue(const Request& r) {
        double start_tag = max(last_finish_[uid], virtual_time_);
        double finish_tag = start_tag + size / weight;
        queues_[uid].push_back({r, finish_tag});
    }
    
    std::optional<int> pick_user(double now) {
        // Find user with minimum finish_tag
    }
};
```

**Characteristics:**
- O(n) selection to find minimum finish tag
- Virtual time advances with each service
- Precise proportional fairness
- Tag calculated at enqueue time

### MQSim Implementation

**Key Components:**
- `TSU_QFQ` class
- `FlowState` structure with `weight`, `service`, and `last_finish_tag`
- Single `virtual_time` for the system
- `apply_qfq_if_user_queue()` to tag transactions in queues

**High-Level Flow:**
1. **Schedule**: Route transactions to queues
2. **Apply QFQ**: When servicing, apply QFQ tagging to user queues
3. **Selection**: `pick_next_user_transaction()` finds transaction with minimum finish tag
4. **Virtual Time**: Updated based on selected transaction

**Key Code Structure:**
```cpp
class TSU_QFQ {
    struct FlowState {
        double weight;
        double service;
        double last_finish_tag;
    };
    std::vector<FlowState> flow_state;
    double virtual_time;
    
    void apply_qfq_if_user_queue(
        Flash_Transaction_Queue* queue,
        flash_channel_ID_type channel_id,
        flash_chip_ID_type chip_id);
    
    NVM_Transaction_Flash* pick_next_user_transaction(
        Flash_Transaction_Queue& queue);
};
```

**Characteristics:**
- Tags applied during scheduling (not at enqueue)
- Per-channel/chip queue management
- Separate handling for read/write queues
- More complex due to channel parallelism

### Key Differences

| Aspect | Lightweight Simulator | MQSim |
|--------|----------------------|-------|
| **Tagging Time** | At enqueue | During scheduling |
| **Queue Structure** | Pre-tagged requests | Tags applied on-the-fly |
| **Virtual Time** | Single global | Single global (similar) |
| **Complexity** | Simpler tagging | Channel/chip-aware |

---

## 4. FLIN (Fairness via Latency Interference Neutralization)

### Algorithm Overview
FLIN is a slowdown-aware scheduler that tracks recent service per flow and prioritizes under-served flows. It addresses interference between flows by equalizing slowdown ratios.

**Core Concept:**
- Track recent service using EWMA (Exponential Weighted Moving Average)
- Calculate fairness ratio = actual_service / fair_share
- Select flow with minimum fairness ratio (most under-served)
- Apply read bias and starvation detection

### Lightweight Simulator Implementation

**Key Components:**
- `FlinScheduler` class
- `FlowStats` structure per flow:
  - `served_bytes` (EWMA of recent service)
  - `fairness_ewma` (smoothed fairness ratio)
  - `read_fraction` (read intensity)
  - `last_finish` (starvation detection)
- `FlinConfig` with tunable parameters

**High-Level Flow:**
1. **Enqueue**: 
   - Insert request with parallelism-aware ordering
   - If `outstanding >= parallelism_trigger`, insert smaller requests earlier
2. **Decay Service**: Exponential decay of `served_bytes` based on time elapsed
3. **Pick User**:
   - Update totals (decay all flows, compute active flows)
   - Calculate fair_share = total_served / active_flows
   - For each flow: fairness_ratio = served_bytes / fair_share
   - Apply read bias and starvation bias
   - Select flow with minimum score
4. **On Finish**: 
   - Add request size to served_bytes
   - Update fairness_ewma
   - Update read_fraction

**Key Code Structure:**
```cpp
class FlinScheduler {
    struct FlowStats {
        std::deque<Request> queue;
        double served_bytes;      // EWMA
        double fairness_ewma;
        double read_fraction;
        double last_finish;
    };
    
    std::optional<int> pick_user(double now) {
        auto [total, active] = update_totals(now);  // Decay all flows
        double share = total / active;
        for each flow:
            double ratio = served_bytes / share;
            double bias = read_bias * starvation_bias;
            score = ratio * bias;
        return flow with minimum score;
    }
};
```

**Characteristics:**
- Continuous EWMA-based service tracking
- No explicit flow classification
- Simpler than original FLIN paper
- Uses fairness ratio as slowdown proxy

### MQSim Implementation

**Key Components:**
- `TSU_FLIN` class
- `FLIN_Flow_Monitoring_Unit` per flow:
  - Separate read/write request counts
  - `Sum_read_slowdown`, `Sum_write_slowdown`
- Periodic flow classification epochs
- Queue reordering mechanism (`reorder_for_fairness()`)
- Alone waiting time estimation

**High-Level Flow:**
1. **Flow Classification**: Periodic epochs classify flows as high/low intensity
2. **Queue Reordering**: `reorder_for_fairness()` inserts transactions at positions maximizing fairness
3. **Slowdown Calculation**: Uses `T_shared / T_alone` (actual slowdown)
4. **Selection**: Based on average slowdown per flow
5. **Barrier Mechanism**: Prevents high-intensity flows from jumping ahead

**Key Code Structure:**
```cpp
class TSU_FLIN {
    struct FLIN_Flow_Monitoring_Unit {
        unsigned int Serviced_read_requests_recent;
        unsigned int Serviced_write_requests_recent;
        double Sum_read_slowdown;
        double Sum_write_slowdown;
    };
    
    void reorder_for_fairness(
        Flash_Transaction_Queue* queue,
        iterator start, iterator end);
    
    void estimate_alone_waiting_time(
        Flash_Transaction_Queue* queue,
        iterator position);
    
    double fairness_based_on_average_slowdown(
        channel_id, chip_id, priority_class, is_read);
};
```

**Characteristics:**
- Periodic flow classification (high/low intensity)
- Queue reordering for fairness
- Actual slowdown calculation (T_shared / T_alone)
- Separate read/write tracking
- Barrier mechanism
- More complex, closer to original paper

### Key Differences

| Aspect | Lightweight Simulator | MQSim |
|--------|----------------------|-------|
| **Service Tracking** | Continuous EWMA | Periodic classification epochs |
| **Slowdown Calculation** | Fairness ratio proxy | Actual T_shared/T_alone |
| **Queue Management** | Flow selection | Queue reordering |
| **Read/Write Handling** | Unified (read_fraction) | Separate tracking |
| **Complexity** | Simplified | Full FLIN algorithm |

---

## 5. MinMax Fairness Scheduler

### Algorithm Overview
MinMax scheduler minimizes worst-case slowdown disparity by selecting the flow with the minimum service-to-weight ratio. This directly optimizes for min-max fairness.

**Algorithm:**
```
For each flow i:
    r_i = (S_i + ε) / w_i
Select flow k = arg min_i r_i
```

Where:
- `S_i` = total service (bytes) given to flow i
- `w_i` = weight of flow i
- `ε` = small constant (typically 1.0) to prevent division by zero

### Lightweight Simulator Implementation

**Key Components:**
- `MinMaxScheduler` class
- `FlowState` structure per flow:
  - `weight` (default 1.0)
  - `service_bytes` (total bytes served)
- Per-user queues

**High-Level Flow:**
1. **Enqueue**: Add request to user's queue
2. **Pick User**:
   - For each flow with pending requests:
     - Calculate metric = (service_bytes + 1.0) / weight
   - Select flow with minimum metric
3. **Pop**: Remove request and add its size to `service_bytes`

**Key Code Structure:**
```cpp
class MinMaxScheduler {
    struct FlowState {
        double weight = 1.0;
        uint64_t service_bytes = 0;
    };
    std::vector<std::deque<Request>> queues_;
    std::vector<FlowState> flow_state_;
    
    std::optional<int> pick_user(double) {
        for each flow:
            double metric = (service_bytes + 1.0) / weight;
        return flow with minimum metric;
    }
    
    std::optional<Request> pop(int uid) {
        Request r = queues_[uid].front();
        flow_state_[uid].service_bytes += r.size_bytes;
        return r;
    }
};
```

**Characteristics:**
- Simple and direct implementation
- O(n) selection per scheduling decision
- Direct min-max optimization
- Service accumulates over time

### MQSim Implementation

**Key Components:**
- `TSU_MinMax` class
- `FlowState` structure:
  - `weight` (default 1.0)
  - `service` (total bytes served)
- Separate queues per channel/chip
- `pick_minmax_user_transaction()` for selection

**High-Level Flow:**
1. **Schedule**: Route transactions to appropriate queues
2. **Service Transactions**: For each channel/chip:
   - Use `pick_minmax_user_transaction()` to select from user queue
   - Calculate metric = (service + 1.0) / weight for each stream
   - Select transaction from stream with minimum metric
3. **Update Service**: Add transaction size to flow's service counter

**Key Code Structure:**
```cpp
class TSU_MinMax {
    struct FlowState {
        double weight;
        double service;
    };
    std::vector<FlowState> flow_state;
    
    NVM_Transaction_Flash* pick_minmax_user_transaction(
        Flash_Transaction_Queue& queue) {
        // For each transaction in queue:
        //   metric = (flow_state[stream_id].service + 1.0) / weight
        // Return transaction with minimum metric
    }
};
```

**Characteristics:**
- Per-channel/chip queue management
- Service tracking per stream
- Similar algorithm to Lightweight Simulator
- Handles channel-level parallelism

### Key Differences

| Aspect | Lightweight Simulator | MQSim |
|--------|----------------------|-------|
| **Algorithm** | Identical | Identical |
| **Scope** | User-level | Channel/chip-level |
| **Complexity** | Simpler | Channel parallelism handling |
| **State Management** | Per-user | Per-stream across channels |

---

## Summary Comparison

### Implementation Complexity

| Scheduler | Lightweight Simulator | MQSim |
|-----------|----------------------|-------|
| **RR** | Simple user-level rotation | Channel/chip parallelism |
| **DRR** | Single deficit per user | Separate read/write deficits |
| **QFQ** | Pre-tagged requests | On-the-fly tagging |
| **FLIN** | Simplified EWMA-based | Full algorithm with reordering |
| **MINMAX** | Direct implementation | Channel-aware |

### Key Architectural Differences

1. **Queue Structure**:
   - **Lightweight**: Single queue per user
   - **MQSim**: Separate read/write queues per channel/chip

2. **State Management**:
   - **Lightweight**: User-level state
   - **MQSim**: Channel/chip-level state with stream tracking

3. **Complexity**:
   - **Lightweight**: Simplified for educational purposes
   - **MQSim**: Full-featured with channel parallelism, GC, mapping operations

4. **Algorithm Fidelity**:
   - **Lightweight**: Core algorithms preserved, some simplifications
   - **MQSim**: More complete implementations, especially for FLIN

### When to Use Which

- **Lightweight Simulator**: 
  - Educational purposes
  - Algorithm understanding
  - Quick prototyping
  - Fairness evaluation at high level

- **MQSim**:
  - Detailed SSD modeling
  - Channel/chip parallelism studies
  - Production-like scenarios
  - Complete FLIN implementation

---

## Code References

### Lightweight Simulator
- **Location**: `Lightweight_Simulator/include/scheduler_impl.hpp`
- **RR**: Lines 71-119
- **DRR**: Lines 121-196
- **QFQ**: Lines 198-297
- **FLIN**: Lines 299-506
- **MINMAX**: Lines 568-651

### MQSim
- **Location**: `MQSim/src/ssd/`
- **RR**: `TSU_RR.h` and `TSU_RR.cpp`
- **DRR**: `TSU_DRR.h` and `TSU_DRR.cpp`
- **QFQ**: `TSU_QFQ.h` and `TSU_QFQ.cpp`
- **FLIN**: `TSU_FLIN.h` and `TSU_FLIN.cpp`
- **MINMAX**: `TSU_MinMax.h` and `TSU_MinMax.cpp`

---

## Conclusion

Both simulators implement the core fairness algorithms correctly, with MQSim providing more detailed SSD modeling and Lightweight Simulator focusing on algorithm clarity and educational value. The choice between them depends on the specific research or educational goals.

