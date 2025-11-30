cmake_minimum_required(VERSION 3.10)
project(ssd-fairness)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(CORE_SOURCES
    src/metrics.cpp
    src/scheduler.cpp
    src/scheduler_factory.cpp
    src/simulator.cpp
    src/ssd.cpp
    src/trace_reader.cpp
    src/util.cpp
)

add_library(ssd-fairness-core ${CORE_SOURCES})
target_include_directories(ssd-fairness-core PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include)

add_executable(ssd-fairness src/main.cpp)
target_link_libraries(ssd-fairness PRIVATE ssd-fairness-core)

if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(ssd-fairness-core PRIVATE -Wall -Wextra -Wpedantic)
    target_compile_options(ssd-fairness PRIVATE -Wall -Wextra -Wpedantic)
endif()

enable_testing()
set(TEST_SOURCES
    tests/main.cpp
    tests/metrics_tests.cpp
    tests/scheduler_tests.cpp
    tests/simulator_tests.cpp
)
add_executable(ssd-fairness-tests ${TEST_SOURCES})
target_link_libraries(ssd-fairness-tests PRIVATE ssd-fairness-core)
if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(ssd-fairness-tests PRIVATE -Wall -Wextra -Wpedantic)
endif()
add_test(NAME ssd-fairness-tests COMMAND ssd-fairness-tests)
