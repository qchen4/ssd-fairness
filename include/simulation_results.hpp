// simulation_results.hpp: Helper functions for analyzing and reporting simulation results.
#pragma once

#include "simulator.hpp"

#include <string>
#include <iostream>

namespace ssd {

/**
 * Aggregated statistics across all users in a simulation run.
 */
struct AggregatedStatistics {
    uint64_t total_bytes = 0;
    size_t total_completed_requests = 0;
    double average_latency_seconds = 0.0;
    double throughput_MBps = 0.0;
    double throughput_fairness_index = 0.0;
    double average_slowdown = 0.0;
};

/**
 * Computes aggregated statistics from a simulation result.
 */
AggregatedStatistics compute_statistics(const SimulationResult& result);

/**
 * Prints simulation results summary to stdout.
 */
void print_simulation_summary(const SimulationResult& result, 
                             const AggregatedStatistics& stats,
                             const std::string& results_path);

} // namespace ssd

#pragma once

#include "simulator.hpp"

#include <string>
#include <iostream>

namespace ssd {

/**
 * Aggregated statistics across all users in a simulation run.
 */
struct AggregatedStatistics {
    uint64_t total_bytes = 0;
    size_t total_completed_requests = 0;
    double average_latency_seconds = 0.0;
    double throughput_MBps = 0.0;
    double throughput_fairness_index = 0.0;
    double average_slowdown = 0.0;
};

/**
 * Computes aggregated statistics from a simulation result.
 */
AggregatedStatistics compute_statistics(const SimulationResult& result);

/**
 * Prints simulation results summary to stdout.
 */
void print_simulation_summary(const SimulationResult& result, 
                             const AggregatedStatistics& stats,
                             const std::string& results_path);

} // namespace ssd

