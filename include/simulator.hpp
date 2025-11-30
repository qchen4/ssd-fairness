#pragma once

#include "metrics.hpp"
#include "scheduler.hpp"
#include "types.hpp"

#include <memory>
#include <string>
#include <vector>

namespace ssd {

struct SchedulerSettings {
    double quantum = 4096.0;
    std::vector<double> weights;
    int sgfs_rotate_every = 200;
    int sgfs_gap = 1;
};

struct SimulationOptions {
    SimConfig device_cfg;
    SchedulerSettings scheduler;
    std::string results_path = "results/results.csv";
    bool write_results = true;
};

struct SimulationResult {
    Metrics metrics;
    double finished_at = 0.0;
    size_t completed_requests = 0;
};

// Simulator owns the event loop that drives requests through the device and
// scheduler. It can be reused with different schedulers or traces.
class Simulator {
public:
    explicit Simulator(SimulationOptions opts);

    SimulationResult run(std::unique_ptr<Scheduler> scheduler,
                         const std::vector<Request>& trace) const;

private:
    SimulationOptions opts_;
};

} // namespace ssd
