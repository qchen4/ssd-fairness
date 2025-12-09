# Build Instructions

**Last Updated:** December 8, 2024

---

## MQSim Build

### Prerequisites
- GCC with C++11 support
- Make

### Build Steps
```bash
cd MQSim
make clean    # Optional: clean previous build
make          # Build with default settings
make -j4      # Build with 4 parallel jobs (faster)
```

### Build Output
- Executable: `MQSim/MQSim`
- Object files: `MQSim/build/`
- Build log: Check console output or redirect to file

### Verification
```bash
cd MQSim
./MQSim --help  # Should show usage information
```

---

## Lightweight Simulator Build

### Prerequisites
- CMake ≥ 3.10
- C++17 compiler (GCC, Clang)

### Build Steps
```bash
cd Lightweight_Simulator
mkdir -p build
cd build
cmake ..
make -j$(nproc)
```

### Build Output
- Executable: `Lightweight_Simulator/build/ssd-fairness`
- Test executable: `Lightweight_Simulator/build/ssd-fairness-tests`

---

## Troubleshooting

### MQSim Build Issues
- **Missing dependencies:** Check that all source files are present
- **Compilation errors:** Check `TSU_Base.h` for enum definitions
- **Linking errors:** Verify all object files are generated

### Lightweight Simulator Build Issues
- **CMake errors:** Ensure CMake version ≥ 3.10
- **C++17 errors:** Update compiler or adjust CMakeLists.txt
- **Missing headers:** Check `include/` directory structure

---

**For implementation status, see `docs/STATUS.md`**

