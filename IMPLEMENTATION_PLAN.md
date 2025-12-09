# Implementation Plan: Six Scheduling Algorithms Across Lightweight Simulator and MQSim

## 1. Overview

This document presents a coordinated, cross-simulator implementation plan for six scheduling algorithms, evaluated in both the **Lightweight SSD Simulator** and **MQSim**:

### Algorithms

1. **Round Robin (RR)**
2. **Deficit Round Robin (DRR)**
3. **Quick Fair Queueing (QFQ)**
4. **BFQ-Lite (Proportional Budget Scheduling)**
   *(a simplified, TSU-compatible version of BFQ)*
5. **FLIN (Flash-Level Interference Mitigation)**
   *(device-level fairness, not wear-leveling)*
6. **Min–Max Fairness Scheduler (MINMAX)**

**Critical Note:** Because MQSim operates at the flash-transaction level (TSU) and not the OS-level request scheduler, algorithms such as BFQ must be adapted to MQSim's abstractions. This plan reflects those adaptations.

---

## 2. Current State Assessment

### 2.1 Lightweight Simulator Status

| Algorithm | Status | Location | Notes |
|-----------|--------|----------|-------|
| **RR** | ✅ Implemented | `include/scheduler_impl.hpp` (RoundRobinScheduler) | Ready |
| **DRR** | ✅ Implemented | `include/scheduler_impl.hpp` (DeficitRoundRobinScheduler) | Ready |
| **QFQ** | ✅ Implemented | `include/scheduler_impl.hpp` (WeightedFairScheduler) | Ready |
| **BFQ-Lite** | ❌ Missing | Needs implementation | Proportional-budget scheduler |
| **FLIN** | ⚠️ Partial | `include/scheduler_impl.hpp` (FlinScheduler) | Exists but needs verification |
| **MINMAX** | ❌ Missing | Needs implementation | Must match MQSim semantics |

**Important:** The lightweight simulator has a `WearLevelScheduler` that extends FLIN, but **wear-leveling and FLIN are separate concepts**. FLIN is an interference mitigation scheduler, not a wear-leveling mechanism.

### 2.2 MQSim Status

| Algorithm | Status | Location | Notes |
|-----------|--------|----------|-------|
| **RR** | ❌ Missing | Requires TSU implementation | Multi-level queue complexity |
| **DRR** | ❌ Missing | Requires TSU implementation | Multi-level queue complexity |
| **QFQ** | ✅ Implemented | `src/ssd/TSU_QFQ.cpp` | Ready |
| **BFQ-Lite** | ❌ Missing | Requires TSU implementation | Must be TSU-compatible |
| **FLIN** | ❌ Missing | Requires device-level scheduling | Complex interference rules |
| **MINMAX** | ✅ Implemented | `src/ssd/TSU_MinMax.cpp` | Needs consistency verification |

---

## 3. Architecture and Design Principles

### 3.1 Common Flow State Definition

**Critical:** Before implementing any schedulers, we must unify the scheduling model across both simulators to ensure cross-comparability.

All six schedulers will share a standard data structure:

```cpp
struct FlowState {
    double weight = 1.0;              // Proportional share weight
    uint64_t service_bytes = 0;        // Total bytes or service units consumed
    double deficit = 0.0;              // For DRR: accumulated deficit counter
    double budget = 0.0;               // For BFQ-Lite: current budget
    double max_budget = 0.0;           // For BFQ-Lite: maximum budget per period
    double finish_tag = 0.0;           // For QFQ/WFQ: virtual finish time
    double last_service_time = 0.0;     // Last time flow was served
    bool idle = false;                 // For BFQ-Lite and FLIN: idle detection
    int outstanding_requests = 0;      // For FLIN: parallelism tracking
};
```

This ensures:
- Consistent behavior across simulators
- Cross-simulator result comparability
- Easier algorithm porting
- Unified testing framework

### 3.2 Correct Algorithm Classification

#### BFQ vs BFQ-Lite

**Critical Correction:** BFQ (Budget Fair Queueing) is a *host-side OS scheduler* designed for a single block device queue. MQSim's TSU operates at the flash-transaction level, not host I/O requests.

**Therefore:**
- True BFQ cannot be implemented in MQSim as-is
- We implement **BFQ-Lite**: a simplified proportional-budget scheduler that captures BFQ's spirit (budget-based proportional sharing) but is adapted to MQSim's TSU architecture
- BFQ-Lite features:
  - Per-flow budgets proportional to weights
  - Budget consumption per transaction
  - Idle flow detection (simplified)
  - **No hierarchical service tree** (flat structure only)

#### FLIN vs Wear-Leveling

**Critical Correction:** FLIN is a **flash-level interference mitigation scheduler**, not a wear-leveling algorithm.

- **FLIN** = Device-level fairness scheduler that equalizes slowdowns across flows
- **Wear-Leveling** = FTL-level policy that distributes erase operations across blocks

These are **separate mechanisms** and should not be conflated. The lightweight simulator's `WearLevelScheduler` combines both, but they are conceptually distinct.

**For this plan:**
- Implement **FLIN** (interference mitigation) as a TSU scheduler
- Wear-leveling remains an FTL concern (not part of this scheduler implementation)

#### MINMAX Semantics

**Critical:** MINMAX must match MQSim's semantics exactly for cross-simulator consistency.

MQSim's MINMAX:
- Computes `(service + 1.0) / weight` for each flow
- Selects flow with minimum ratio
- Uses total serviced bytes (not just recent service)
- May include slowdown estimation

The lightweight simulator implementation must match these semantics.

### 3.3 Flow Mapping and Accounting

**Missing Requirement:** Define how host flows map to scheduler flows:

- **Lightweight Simulator:** Each `user_id` = one scheduler flow
- **MQSim:** Each `Stream_id` = one scheduler flow
- **GC Transactions:** Must decide if GC participates in fairness (recommendation: separate GC queue, not included in fairness)
- **Internal Operations:** Mapping reads/writes should not be penalized in fairness calculations

**Fairness Accounting Granularity:**
- Per-request fairness (RR)
- Per-byte fairness (DRR, QFQ, BFQ-Lite)
- Per-slowdown fairness (FLIN, MINMAX)

---

## 4. Implementation Phases (Optimized Order)

**Key Insight:** Implement in MQSim first, then port to lightweight simulator. MQSim's architecture is the superset; this prevents rework.

---

### Phase 0: Scheduler Framework Alignment (1-2 hours)

**Purpose:** Establish unified semantics before any implementation.

**Tasks:**
1. Define unified `FlowState` structure in both simulators
2. Ensure identical flow index mapping (`user_id` ↔ `Stream_id`)
3. Standardize weight handling (default 1.0, configurable)
4. Define service accounting rules (per-byte vs per-request)
5. Create shared header/interface for cross-simulator consistency

**Deliverables:**
- `include/flow_state.hpp` (shared definition)
- Documentation of flow mapping conventions
- Service accounting specification

**Why First:** Prevents inconsistent semantics that would require rework later.

---

### Phase 1: Implement RR, DRR, MINMAX in MQSim (14-18 hours)

**Rationale:** MQSim has stricter architecture (multi-level queues, transaction types). Implementing here first ensures correctness, then lightweight becomes a simplified port.

#### Task 1.1: Round Robin (RR) TSU

**Files to create/modify:**
- `src/ssd/TSU_RR.h` - Header file
- `src/ssd/TSU_RR.cpp` - Implementation
- `src/ssd/TSU_Base.h` - Add `RR` to `Flash_Scheduling_Type` enum
- `src/exec/SSD_Device.cpp` - Add factory case
- `src/exec/SSD_Defs.h` - Add XML config parsing

**Implementation approach:**
- Follow pattern of `TSU_QFQ.cpp` or `TSU_OutOfOrder.cpp`
- Maintain per-channel, per-chip transaction queues
- Track round-robin state per channel (read/write separately)
- Cycle through active flows in fixed order
- Handle transaction types: UserRead, UserWrite, MappingRead, MappingWrite, GCRead, GCWrite, GCErase

**Complexity:** Medium-High
- Must handle multi-level queueing (Channel → Chip → Die → Plane)
- Must respect transaction type priorities (mapping > user > GC)
- Must work with channel availability constraints

**Estimated time:** 6-8 hours (not 2-3 as originally estimated)

**Key Implementation Details:**
```cpp
class TSU_RR : public TSU_Base {
    Flash_Transaction_Queue** UserReadTRQueue;
    Flash_Transaction_Queue** UserWriteTRQueue;
    // ... other queues (GC, Mapping)
    
    unsigned int* current_turn_read;   // Per-channel round-robin state
    unsigned int* current_turn_write;
    
    // Round-robin selection logic
    Flash_Transaction_Queue* select_next_queue_read(channel_id, chip_id);
    Flash_Transaction_Queue* select_next_queue_write(channel_id, chip_id);
};
```

#### Task 1.2: Deficit Round Robin (DRR) TSU

**Files to create/modify:**
- `src/ssd/TSU_DRR.h` - Header file
- `src/ssd/TSU_DRR.cpp` - Implementation
- `src/ssd/TSU_Base.h` - Add `DRR` to enum
- `src/exec/SSD_Device.cpp` - Add factory case
- `src/exec/SSD_Defs.h` - Add DRR quantum parameter to XML config

**Implementation approach:**
- Port `DeficitRoundRobinScheduler` logic from lightweight simulator
- Maintain per-flow deficit counters (per Stream_id)
- Add quantum per round (configurable via XML, default 4096 bytes)
- Support per-flow weights (from XML config)
- Only dispatch transactions when deficit >= transaction size
- Deficit accumulates across rounds until consumed

**Complexity:** Medium-High
- Must track deficits per flow across all channels/chips
- Must handle variable transaction sizes
- Must integrate with MQSim's transaction queue structure

**Estimated time:** 6-8 hours

**Key Implementation Details:**
```cpp
class TSU_DRR : public TSU_Base {
    struct FlowState {
        double weight = 1.0;
        int64_t deficit = 0;  // Accumulated deficit
    };
    
    std::vector<FlowState> flow_state_;
    double quantum_ = 4096.0;  // Base quantum in bytes
    
    // DRR selection: add quantum, check if transaction fits
    NVM_Transaction_Flash* pick_drr_transaction(Flash_Transaction_Queue& queue);
};
```

#### Task 1.3: MINMAX Verification and Cleanup

**Status:** Already implemented in `TSU_MinMax.cpp`, but needs:

1. **Consistency verification:**
   - Ensure `FlowState` matches unified definition
   - Verify service accounting matches lightweight version
   - Check weight handling

2. **Integration:**
   - Use unified `FlowState` structure
   - Add XML config for weights (if missing)
   - Ensure deterministic behavior

**Estimated time:** 2 hours

---

### Phase 2: Port RR, DRR, MINMAX to Lightweight Simulator (4-5 hours)

**Rationale:** Now that MQSim versions are correct, porting is straightforward simplification.

#### Task 2.1: MINMAX Scheduler

**Files to modify:**
- `include/scheduler_impl.hpp` - Add `MinMaxScheduler` class
- `src/scheduler_factory.cpp` - Add factory case for "minmax"
- `src/command_line_parser.cpp` - Add CLI option

**Implementation approach:**
- Port MINMAX logic from MQSim's `TSU_MinMax.cpp`
- Use unified `FlowState` structure
- Match MQSim semantics exactly: `(service + 1.0) / weight`
- Maintain per-flow service bytes and weights

**Estimated time:** 2-3 hours

**Key Implementation:**
```cpp
class MinMaxScheduler : public Scheduler {
    struct FlowState {
        double weight = 1.0;
        uint64_t service_bytes = 0;  // Total bytes served
    };
    
    std::vector<std::deque<Request>> queues_;
    std::vector<FlowState> flow_state_;
    
    // Select flow with minimum (service + 1.0) / weight
    std::optional<int> pick_user(double now) override;
};
```

#### Task 2.2: RR/DRR Consistency Verification

**Status:** Already implemented, but verify:
- Consistency with MQSim semantics
- Use of unified `FlowState` (if applicable)
- Correct weight handling

**Estimated time:** 1 hour

---

### Phase 3: Implement BFQ-Lite in Both Simulators (10-12 hours)

**Critical:** This is **BFQ-Lite**, not true BFQ. It's a proportional-budget scheduler adapted for TSU.

#### Task 3.1: BFQ-Lite in Lightweight Simulator (4 hours)

**Files to modify:**
- `include/scheduler_impl.hpp` - Add `BfqLiteScheduler` class
- `src/scheduler_factory.cpp` - Add factory case for "bfq" or "bfq-lite"
- `src/command_line_parser.cpp` - Add CLI options

**Implementation approach:**
- **Budget allocation:** Each flow gets `budget_i = base_budget * weight_i`
- **Service:** Serve requests while `budget_i >= request_size`
- **Budget refresh:** At end of service period, refresh budgets
- **Idle detection:** If flow idle for threshold time, reset budget
- **Simplified:** No hierarchical service tree (flat structure)

**Key Features:**
- Per-flow budgets proportional to weights
- Budget consumption per request
- Idle flow detection (simplified)
- Budget refresh mechanism

**Estimated time:** 4 hours

**Key Implementation:**
```cpp
class BfqLiteScheduler : public Scheduler {
    struct FlowState {
        double weight = 1.0;
        double budget = 0.0;           // Current budget
        double max_budget = 0.0;        // Maximum budget per period
        double last_service_time = 0.0;
        bool idle = false;
    };
    
    double base_budget_ = 8192.0;      // Base budget in bytes
    double idle_threshold_ = 0.1;      // Seconds before considered idle
    
    // BFQ-Lite selection logic
    std::optional<int> pick_user(double now) override;
};
```

#### Task 3.2: BFQ-Lite TSU in MQSim (6-8 hours)

**Files to create/modify:**
- `src/ssd/TSU_BFQ.h` - Header file
- `src/ssd/TSU_BFQ.cpp` - Implementation
- `src/ssd/TSU_Base.h` - Add `BFQ_LITE` to enum
- `src/exec/SSD_Device.cpp` - Add factory case
- `src/exec/SSD_Defs.h` - Add BFQ-Lite parameters to XML

**Implementation approach:**
- Similar to lightweight version but adapted for TSU
- Track budgets per Stream_id
- Handle transaction types (read/write separately or combined)
- Integrate with MQSim's transaction queue structure

**Complexity:** Medium-High
- Must work with multi-level queues
- Must handle variable transaction sizes
- Must detect idle flows across channels

**Estimated time:** 6-8 hours

---

### Phase 4: Implement FLIN in MQSim (10-14 hours)

**Critical:** FLIN is an interference mitigation scheduler, NOT wear-leveling.

#### Task 4.1: FLIN TSU Implementation

**Files to create/modify:**
- `src/ssd/TSU_FLIN.h` - Header file (may already exist, verify)
- `src/ssd/TSU_FLIN.cpp` - Implementation
- `src/ssd/TSU_Base.h` - Add `FLIN` to enum (if missing)
- `src/exec/SSD_Device.cpp` - Add factory case

**Implementation approach:**
FLIN consists of multiple stages:

1. **Flow Monitoring:**
   - Track per-flow service history (EWMA)
   - Monitor read/write mix
   - Detect flow intensity

2. **Interference Detection:**
   - Identify flows experiencing interference (GC, mapping operations)
   - Compute slowdown: `actual_service / fair_share`

3. **Fairness Enforcement:**
   - Prioritize flows with high slowdown (under-served)
   - Reorder transactions to equalize slowdowns
   - Apply read bias (prefer read-heavy flows)

4. **Request Reordering:**
   - Insert new requests based on slowdown
   - Maintain barriers to prevent starvation
   - Handle parallelism-aware insertion

**Complexity:** Very High
- FLIN contains ~40 decision rules in original design
- Requires careful EWMA tracking
- Must handle reordering without breaking transaction dependencies

**Estimated time:** 10-14 hours

**Key Implementation:**
```cpp
class TSU_FLIN : public TSU_Base {
    struct FLIN_FlowState {
        double served_bytes_ewma = 0.0;
        double fairness_ewma = 1.0;
        double read_fraction = 0.5;
        double last_finish_time = 0.0;
        int outstanding = 0;
    };
    
    // FLIN-specific logic
    void reorder_for_fairness(Flash_Transaction_Queue* queue, ...);
    double compute_slowdown(stream_id_type sid);
    NVM_Transaction_Flash* pick_flin_transaction(...);
};
```

**Note:** The lightweight simulator already has a `FlinScheduler`. Verify it matches FLIN semantics and port any missing logic to MQSim.

---

## 5. Integration and Test Plan

### 5.1 Unit Testing

#### Required Tests for Each Scheduler

**Lightweight Simulator:**
- Flow selection correctness
- Weight proportionality
- Budget/deficit accounting (BFQ-Lite, DRR)
- Idle detection (BFQ-Lite)
- Slowdown reduction (MINMAX, FLIN)
- Fairness metrics (Jain's index)

**MQSim:**
- Per-channel queue management
- Transaction type handling
- Multi-level queue correctness
- GC interaction (should not affect fairness)
- Weight proportionality across channels

#### Test Files

- **Lightweight:** `tests/scheduler_tests.cpp`
- **MQSim:** Create `tests/tsu_tests.cpp` or extend existing tests

#### Test Cases

1. **Equal weights, equal workloads:** All flows should get equal service
2. **Weighted sharing (4:2:1):** Verify proportional allocation
3. **Bursty arrivals:** Test fairness under bursty traffic
4. **Size asymmetry:** Large vs small requests
5. **Idle flows:** BFQ-Lite should handle idle detection
6. **Interference:** FLIN should mitigate interference effects

### 5.2 Integration Tests

#### Cross-Simulator Validation

1. **Identical Traces:**
   - Run same trace file through both simulators
   - Compare fairness metrics (Jain's index, slowdown)
   - Verify similar behavior for shared algorithms

2. **Metrics to Compare:**
   - Throughput distribution per flow
   - Jain's fairness index
   - Per-flow slowdown ratios
   - Latency CDFs (P50, P95, P99)
   - Average latency per flow

3. **Expected Discrepancies:**
   - Queue depth differences (MQSim has internal queues)
   - Channel availability variance
   - GC effects (MQSim models GC explicitly)
   - Internal mapping operations

**Acceptance Criteria:** Fairness metrics should match within ±5% between simulators for identical traces.

### 5.3 Workload Set

#### Standard Workloads

1. **Mixed read/write (50/50):** Balanced workload
2. **Heavy writer vs light reader:** Asymmetric workload
3. **Bursty arrivals:** Test fairness under bursts
4. **Size asymmetry:** 4KB vs 128KB requests
5. **Weighted sharing:** 4:2:1 weight ratios

#### Adversarial Workloads (Critical for Fairness Testing)

1. **Micro-burst attacks:**
   - One flow sends many small requests in short bursts
   - Tests if scheduler prevents fairness stealing

2. **Large-request attackers:**
   - One flow sends very large requests
   - Tests byte-level fairness (DRR, QFQ, BFQ-Lite)

3. **Random vs sequential mixes:**
   - Some flows sequential, others random
   - Tests interference handling (FLIN)

4. **Extreme write-only vs read-only:**
   - Tests read bias in FLIN
   - Tests interference mitigation

### 5.4 Performance Validation

#### Fairness Metrics

1. **Jain's Fairness Index:**
   ```
   J = (Σx_i)² / (n * Σx_i²)
   ```
   Where `x_i` = throughput or slowdown ratio per flow

2. **Per-flow slowdown ratios:**
   - `slowdown_i = actual_service_i / fair_share_i`
   - Should be close to 1.0 for fair schedulers

3. **Throughput distribution:**
   - Coefficient of variation (CV) of per-flow throughput
   - Lower CV = more fair

#### Latency Metrics

1. **Average latency per flow**
2. **P95/P99 tail latencies**
3. **Latency CDFs** for comparison

#### Wear Metrics (if applicable)

- **Erase count variance:** Lower is better
- **Min/max erase counts:** Track wear spread
- **Wear imbalance:** Ratio of max/min erase counts

---

## 6. Risk Assessment and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| **BFQ semantics mismatch** | Very High | High | Use BFQ-Lite (proportional-budget), explicitly document limitations |
| **FLIN complexity** | Very High | Medium | Implement core FLIN stages first, add logging for debugging, validate against reference |
| **TSU RR/DRR multi-level queue complexity** | High | Medium | Start with per-channel implementation, test thoroughly, document queue traversal logic |
| **Cross-simulator result mismatches** | Medium | Medium | Standardize FlowState first, normalize service-time models, document expected differences |
| **GC transaction fairness** | Medium | Low | Separate GC queues, exclude from fairness calculations, validate GC doesn't starve user flows |
| **Testing overhead** | Medium | High | Auto-generate metrics CSV, create Python visualization scripts, automate comparison |
| **Time overrun** | Medium | Medium | Prioritize: RR/DRR first (simpler), then MINMAX, then BFQ-Lite, then FLIN (hardest) |

### Additional Mitigations

1. **Incremental Implementation:**
   - Implement one scheduler at a time
   - Test thoroughly before moving to next
   - Don't attempt all at once

2. **Reference Validation:**
   - Compare against known-good implementations
   - Use theoretical fairness bounds
   - Validate against published papers

3. **Logging and Debugging:**
   - Add extensive logging for scheduler decisions
   - Create deterministic replay mode
   - Enable scheduler debug flags

---

## 7. Updated Timeline (Corrected Based on Real Complexity)

| Phase | Task | Estimated Time |
|-------|------|----------------|
| **Phase 0** | Framework alignment (FlowState) | 1-2 hours |
| **Phase 1** | RR in MQSim | 6-8 hours |
| **Phase 1** | DRR in MQSim | 6-8 hours |
| **Phase 1** | MINMAX verification | 2 hours |
| **Phase 2** | MINMAX in Lightweight | 2-3 hours |
| **Phase 2** | RR/DRR consistency check | 1 hour |
| **Phase 3** | BFQ-Lite in Lightweight | 4 hours |
| **Phase 3** | BFQ-Lite in MQSim | 6-8 hours |
| **Phase 4** | FLIN in MQSim | 10-14 hours |
| **Testing** | Unit & Integration tests | 6-8 hours |
| **Documentation** | README updates, examples | 2-3 hours |
| **Total** | | **45-59 hours** |

This is a realistic engineering estimate based on:
- MQSim's multi-level queue complexity
- FLIN's ~40 decision rules
- Cross-simulator consistency requirements
- Testing and validation overhead

---

## 8. Missing Tasks (Must Add)

### 8.1 Fairness Accounting Granularity

**Define:**
- Per-request fairness (RR)
- Per-byte fairness (DRR, QFQ, BFQ-Lite)
- Per-slowdown fairness (FLIN, MINMAX)

**Implementation:**
- Add accounting mode to `FlowState`
- Update metrics collection accordingly

### 8.2 Global Per-Flow Index

**Requirement:**
- Shared flow index across all TSU pipelines
- Consistent flow identification (Stream_id ↔ user_id)

**Implementation:**
- Create flow mapping table
- Ensure deterministic mapping

### 8.3 Logging Hooks for Fairness Metrics

**Requirement:**
- Log scheduler decisions (which flow selected, why)
- Log fairness metrics per epoch
- Enable debugging mode

**Implementation:**
- Add `SCHED_DEBUG` environment variable support
- Create fairness log file format
- Add Python scripts for analysis

### 8.4 Deterministic Replay Mode

**Requirement:**
- Reproduce exact scheduler behavior
- Debug fairness issues
- Validate correctness

**Implementation:**
- Seed random number generators
- Log all scheduler decisions
- Create replay script

### 8.5 XML/CLI Configuration

**MQSim:**
- Add XML config fields for new algorithms
- Quantum for DRR
- Budget parameters for BFQ-Lite
- FLIN parameters (window, alpha, etc.)

**Lightweight Simulator:**
- Add CLI options for all parameters
- Document in README

### 8.6 JSON/CSV Output for Fairness Breakdown

**Requirement:**
- Per-flow fairness metrics
- Time-series data
- Easy analysis

**Implementation:**
- Extend metrics output format
- Add JSON export option
- Create visualization scripts

---

## 9. Success Criteria

### Simulator Feature Criteria

✅ All six schedulers implemented with unified `FlowState`  
✅ Equivalent semantics across simulators  
✅ Configurable weighting, budgets, and quanta  
✅ XML/CLI configuration for all parameters  
✅ Comprehensive logging and debugging support  

### Correctness Criteria

✅ Deterministic flow selection under fixed traces  
✅ Regression tests passing for all schedulers  
✅ Weight proportionality verified (4:2:1 test)  
✅ Budget/deficit accounting correct (BFQ-Lite, DRR)  
✅ Idle detection working (BFQ-Lite)  
✅ Interference mitigation verified (FLIN)  

### Evaluation Criteria

✅ Cross-simulator consistency within ±5% fairness deviation  
✅ Jain's index matches theoretical expectations  
✅ Slowdown fairness matches expected behavior  
✅ FLIN reduces interference compared to RR/DRR/QFQ  
✅ MINMAX minimizes slowdown variance  
✅ Adversarial workloads handled correctly  

### Documentation Criteria

✅ Updated README for each simulator  
✅ XML/CLI configuration examples  
✅ Full experimental methodology documented  
✅ Algorithm comparison guide  
✅ Troubleshooting guide  

---

## 10. Next Actions (Starting Order)

1. **Phase 0:** Implement unified `FlowState` in both simulators (1-2 hours)
2. **Phase 1.1:** Implement RR in MQSim (6-8 hours)
3. **Phase 1.2:** Implement DRR in MQSim (6-8 hours)
4. **Phase 1.3:** Verify MINMAX in MQSim (2 hours)
5. **Phase 2.1:** Port MINMAX to Lightweight simulator (2-3 hours)
6. **Phase 2.2:** Verify RR/DRR consistency (1 hour)
7. **Phase 3.1:** Implement BFQ-Lite in Lightweight simulator (4 hours)
8. **Phase 3.2:** Implement BFQ-Lite in MQSim (6-8 hours)
9. **Phase 4.1:** Implement FLIN in MQSim (10-14 hours)
10. **Testing:** Execute full test suite (6-8 hours)
11. **Documentation:** Update READMEs and create examples (2-3 hours)

---

## 11. References

### Papers and Documentation

- **BFQ:** "BFQ, a Proportional-Share Disk Scheduling Algorithm" (Paolo Valente)
- **FLIN:** "FLIN: Enabling Fairness and Enhancing Performance in Modern NVMe Solid State Drives" (ISCA 2018)
- **DRR:** "Efficient Fair Queueing Using Deficit Round Robin" (Shreedhar & Varghese)
- **QFQ:** "QFQ: Efficient Packet Scheduling with Bandwidth Guarantees" (Checconi et al.)

### Code References

- **Lightweight Simulator:** `Lightweight_Simulator/README.md`
- **MQSim:** `MQSim/README.md`
- **MQSim TSU_QFQ:** `MQSim/src/ssd/TSU_QFQ.cpp` (reference implementation)
- **MQSim TSU_MinMax:** `MQSim/src/ssd/TSU_MinMax.cpp` (reference implementation)
- **Lightweight Schedulers:** `include/scheduler_impl.hpp` (reference implementations)

---

## 12. Appendix: Algorithm Quick Reference

### Round Robin (RR)
- **Selection:** Cycle through active flows in fixed order
- **Fairness:** Per-request fairness
- **Complexity:** Low
- **Use case:** Simple, uniform request sizes

### Deficit Round Robin (DRR)
- **Selection:** Add quantum, serve requests that fit deficit
- **Fairness:** Per-byte fairness
- **Complexity:** Medium
- **Use case:** Variable request sizes, byte-level fairness

### Quick Fair Queueing (QFQ)
- **Selection:** Smallest virtual finish tag
- **Fairness:** Per-byte weighted fairness
- **Complexity:** Medium
- **Use case:** Weighted proportional sharing

### BFQ-Lite
- **Selection:** Serve requests within budget, refresh budgets
- **Fairness:** Per-byte proportional with budgets
- **Complexity:** Medium-High
- **Use case:** Proportional sharing with budget guarantees

### FLIN
- **Selection:** Prioritize flows with high slowdown (under-served)
- **Fairness:** Per-slowdown fairness (interference-aware)
- **Complexity:** Very High
- **Use case:** Mitigate flash-level interference, equalize slowdowns

### MINMAX
- **Selection:** Flow with minimum `(service + 1.0) / weight`
- **Fairness:** Per-slowdown fairness (minimize max slowdown)
- **Complexity:** Low-Medium
- **Use case:** Minimize worst-case slowdown disparity

---

**End of Implementation Plan**
