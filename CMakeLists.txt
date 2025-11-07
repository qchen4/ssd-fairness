cmake_minimum_required(VERSION 3.10)
project(ssd-fairness)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Source files from src/
set(SOURCES
    src/main.cpp
    src/metrics.cpp
    src/scheduler.cpp
    src/ssd.cpp
    src/util.cpp
)

# Include directory for headers
include_directories(include)

# Create the executable
add_executable(ssd-fairness ${SOURCES})

# Enable common warnings for GCC/Clang
if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(ssd-fairness PRIVATE -Wall -Wextra -Wpedantic)
endif()
