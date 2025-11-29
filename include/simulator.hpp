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
