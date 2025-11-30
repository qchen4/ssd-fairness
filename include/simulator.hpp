// Simulator entry points for running SSD fairness experiments.
#pragma once

#include "metrics.hpp"
#include "scheduler.hpp"
#include "types.hpp"

#include <memory>
#include <string>
#include <vector>

namespace ssd {

struct SchedulerSettings {
    double quantum = 4096.0;          // DRR quantum or similar byte credit.
    std::vector<double> weights;      // Optional per-user weights.
    // FLIN tuning parameters. Unused by other schedulers.
    double flin_window_sec = 0.1;
    double flin_fairness_alpha = 0.1;
    double flin_read_alpha = 0.1;
    double flin_read_bias = 0.25;
    double flin_starvation_window = 0.2;
    int flin_parallelism_trigger = 2;

    // Wear-leveling parameters used by the wear-aware scheduler.
    double wear_hot_threshold = 4.0; // Hot/cold write classification threshold.
    int wear_pool_size = 16;         // Candidate blocks to examine per write.
    bool wear_read_balance = false;  // Enable read-balancing across channels.
};

struct SimulationOptions {
    SimConfig device_cfg;                     // SSD model configuration.
    SchedulerSettings scheduler;              // Scheduler tuning knobs.
    std::string results_path = "results/results.csv"; // Per-user CSV output.
    bool write_results = true;                // Enable CSV emission.
};

struct SimulationResult {
    Metrics metrics;              // Final per-user metrics.
    double finished_at = 0.0;     // Completion time in seconds.
    size_t completed_requests = 0;// Number of finished requests.
};

// Simulator owns the event loop that drives requests through the device and
// scheduler. It can be reused with different schedulers or traces.
class Simulator {
public:
    explicit Simulator(SimulationOptions opts);

    // Runs a trace through the simulator using the provided scheduler.
    SimulationResult run(std::unique_ptr<Scheduler> scheduler,
                         const std::vector<Request>& trace) const;

private:
    SimulationOptions opts_;
};

} // namespace ssd
