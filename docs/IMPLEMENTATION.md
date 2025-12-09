# Implementation Details

**Last Updated:** December 8, 2024

---

## MQSim Implementation

### Implemented Schedulers

#### 1. Quick Fair Queueing (QFQ)
- **Files:** `MQSim/src/ssd/TSU_QFQ.h`, `TSU_QFQ.cpp`
- **Enum:** `Flash_Scheduling_Type::QFQ` in `TSU_Base.h`
- **Factory:** Case in `SSD_Device.cpp` (lines 151-157)
- **XML Parsing:** Supported in `Device_Parameter_Set.cpp`
- **Status:** ✅ Complete and tested

#### 2. FLIN
- **Files:** `MQSim/src/ssd/TSU_FLIN.h`, `TSU_FLIN.cpp`
- **Enum:** `Flash_Scheduling_Type::FLIN` in `TSU_Base.h`
- **Factory:** Case in `SSD_Device.cpp` (lines 167-201)
- **XML Parsing:** Supported in `Device_Parameter_Set.cpp`
- **Bug Fix:** Constructor now uses `Flash_Scheduling_Type::FLIN` (was `OUT_OF_ORDER`)
- **Status:** ✅ Complete and tested

#### 3. MINMAX
- **Files:** `MQSim/src/ssd/TSU_MinMax.h`, `TSU_MinMax.cpp`
- **Enum:** `Flash_Scheduling_Type::MINMAX` in `TSU_Base.h`
- **Factory:** Case in `SSD_Device.cpp` (lines 203-209)
- **XML Parsing:** Supported in `Device_Parameter_Set.cpp`
- **Status:** ✅ Complete and tested

### Missing Schedulers

#### Round Robin (RR)
- **Status:** ❌ Not implemented
- **Required:**
  - Create `TSU_RR.h` and `TSU_RR.cpp`
  - Add `RR` to `Flash_Scheduling_Type` enum
  - Add factory case in `SSD_Device.cpp`
  - Add XML parsing in `Device_Parameter_Set.cpp`

#### Deficit Round Robin (DRR)
- **Status:** ❌ Not implemented
- **Required:**
  - Create `TSU_DRR.h` and `TSU_DRR.cpp`
  - Add `DRR` to `Flash_Scheduling_Type` enum
  - Add factory case in `SSD_Device.cpp`
  - Add XML parsing in `Device_Parameter_Set.cpp`

---

## Lightweight Simulator Implementation

All 5 schedulers are implemented in `include/scheduler_impl.hpp`:
- `RoundRobinScheduler`
- `DeficitRoundRobinScheduler`
- `WeightedFairScheduler` (QFQ)
- `MinMaxScheduler`
- `FlinScheduler`

---

## Usage

### MQSim
```bash
cd MQSim
make
./MQSim -i ssdconfig.xml -w workload.xml
```

Edit `ssdconfig.xml`:
```xml
<Transaction_Scheduling_Policy>QFQ</Transaction_Scheduling_Policy>
<!-- or FLIN, MINMAX -->
```

### Lightweight Simulator
```bash
cd Lightweight_Simulator/build
make
./ssd-fairness --trace ../test_data/traces/high_vs_low.csv --scheduler minmax
```

---

**For build instructions, see `docs/BUILD.md`**

