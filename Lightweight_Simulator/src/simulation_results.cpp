// simulation_results.cpp: Implementation of simulation results analysis and reporting.
#include "simulation_results.hpp"

namespace ssd {

AggregatedStatistics compute_statistics(const SimulationResult& result) {
    AggregatedStatistics stats;
    
    // Aggregate metrics across all users
    uint64_t total_bytes = 0;
    size_t total_completed = 0;
    double latency_sum = 0.0;
    double slowdown_sum = 0.0;
    int slowdown_participants = 0;
    
    for (int user_id = 0; user_id < result.metrics.users(); ++user_id) {
        total_bytes += result.metrics.total_bytes(user_id);
        const size_t completed = result.metrics.completed(user_id);
        total_completed += completed;
        latency_sum += result.metrics.avg_latency(user_id) * static_cast<double>(completed);
        
        if (result.metrics.has_fairness(user_id)) {
            slowdown_sum += result.metrics.fairness_avg(user_id);
            ++slowdown_participants;
        }
    }
    
    // Calculate derived statistics
    stats.total_bytes = total_bytes;
    stats.total_completed_requests = total_completed;
    stats.average_latency_seconds = total_completed > 0 
        ? latency_sum / static_cast<double>(total_completed) 
        : 0.0;
    
    constexpr double kBytesPerMB = 1024.0 * 1024.0;
    stats.throughput_MBps = (result.finished_at > 0.0)
        ? (static_cast<double>(total_bytes) / kBytesPerMB) / result.finished_at
        : 0.0;
    
    stats.throughput_fairness_index = result.metrics.throughput_fairness_index(result.finished_at);
    stats.average_slowdown = (slowdown_participants > 0)
        ? slowdown_sum / static_cast<double>(slowdown_participants)
        : 0.0;
    
    return stats;
}

void print_simulation_summary(const SimulationResult& result,
                             const AggregatedStatistics& stats,
                             const std::string& results_path) {
    std::cout << "Simulation complete.\n";
    std::cout << "Fairness Index: " << result.metrics.fairness_index() << "\n";
    std::cout << "Throughput Fairness Index: " << stats.throughput_fairness_index << "\n";
    std::cout << "Average slowdown: " << stats.average_slowdown << "\n";
    std::cout << "Throughput (MB/s): " << stats.throughput_MBps << "\n";
    std::cout << "Average latency (s): " << stats.average_latency_seconds << "\n";
    std::cout << "Results saved to " << results_path << "\n";
    std::cout << "Completed requests: " << stats.total_completed_requests
              << " in " << result.finished_at << "s\n";
}

} // namespace ssd

