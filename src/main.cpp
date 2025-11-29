// SPDX-License-Identifier: MIT
// Main simulation driver for the SSD fairness scheduling simulator.

#include "scheduler_factory.hpp"
#include "simulator.hpp"
#include "trace_reader.hpp"

#include <cstdlib>
#include <getopt.h>
#include <iostream>
#include <memory>
#include <sstream>
#include <string>
#include <vector>

int main(int argc, char** argv) {
    std::string trace_path = "traces/example.csv";
    std::string policy_str = "qfq"; // rr, drr, qfq, sgfs
    double quantum = 4096.0;
    std::string weights_str;
    int override_users = -1;
    int override_channels = -1;
    double read_bw = 2000;
    double write_bw = 1200;
    int sgfs_rotate_every = 200;
    int sgfs_gap = 1;
    std::string results_path = "results/results.csv";

    static option longopts[] = {
        {"trace", required_argument, 0, 't'},
        {"scheduler", required_argument, 0, 's'},
        {"quantum", required_argument, 0, 'q'},
        {"users", required_argument, 0, 'u'},
        {"channels", required_argument, 0, 'c'},
        {"read-bw", required_argument, 0, 'r'},
        {"write-bw", required_argument, 0, 'w'},
        {"weights", required_argument, 0, 'W'},
        {"results", required_argument, 0, 'o'},
        {"sgfs-rotate", required_argument, 0, 0},
        {"sgfs-gap", required_argument, 0, 0},
        {0,0,0,0}
    };

    int opt = 0;
    int long_index = 0;
    while ((opt = getopt_long(argc, argv, "t:s:q:u:c:r:w:W:o:", longopts, &long_index)) != -1) {
        if (opt == 't') trace_path = optarg;
        else if (opt == 's') policy_str = optarg;
        else if (opt == 'q') quantum = atof(optarg);
        else if (opt == 'u') override_users = atoi(optarg);
        else if (opt == 'c') override_channels = atoi(optarg);
        else if (opt == 'r') read_bw = atof(optarg);
        else if (opt == 'w') write_bw = atof(optarg);
        else if (opt == 'W') weights_str = optarg;
        else if (opt == 'o') results_path = optarg;
        else if (opt == 0 && std::string(longopts[long_index].name) == "sgfs-rotate") {
            sgfs_rotate_every = atoi(optarg);
        } else if (opt == 0 && std::string(longopts[long_index].name) == "sgfs-gap") {
            sgfs_gap = atoi(optarg);
        }
    }

    std::vector<double> weights;
    if (!weights_str.empty()) {
        std::stringstream ss(weights_str);
        std::string token;
        while (std::getline(ss, token, ',')) {
            weights.push_back(std::stod(token));
        }
    }

    ssd::TraceReader reader;
    auto trace = reader.load_csv(trace_path);

    int num_users = override_users > 0 ? override_users : 0;
    for (const auto& r : trace)
        if (r.user_id + 1 > num_users)
            num_users = r.user_id + 1;

    int num_channels = override_channels > 0 ? override_channels : 8;
    SimConfig sim_cfg { num_users, num_channels, read_bw, write_bw };

    ssd::SchedulerSettings sched_settings;
    sched_settings.quantum = quantum;
    sched_settings.weights = weights;
    sched_settings.sgfs_rotate_every = sgfs_rotate_every;
    sched_settings.sgfs_gap = sgfs_gap;

    ssd::SimulationOptions opts;
    opts.device_cfg = sim_cfg;
    opts.scheduler = sched_settings;
    opts.results_path = results_path;
    opts.write_results = true;

    auto scheduler = ssd::make_scheduler(policy_str);
    if (!scheduler) {
        std::cerr << "Unknown scheduler policy: " << policy_str << "\n";
        return 1;
    }

    ssd::Simulator simulator(opts);
    auto result = simulator.run(std::move(scheduler), trace);

    uint64_t total_bytes = 0;
    size_t total_completed = 0;
    double latency_sum = 0.0;
    for (int uid = 0; uid < result.metrics.users(); ++uid) {
        total_bytes += result.metrics.total_bytes(uid);
        const size_t completed = result.metrics.completed(uid);
        total_completed += completed;
        latency_sum += result.metrics.avg_latency(uid) * static_cast<double>(completed);
    }
    double avg_latency = total_completed ? latency_sum / static_cast<double>(total_completed) : 0.0;
    double throughput_MBps = result.finished_at > 0.0
        ? (static_cast<double>(total_bytes) / (1024.0 * 1024.0)) / result.finished_at
        : 0.0;

    std::cout << "Simulation complete.\n";
    std::cout << "Fairness Index: " << result.metrics.fairness_index() << "\n";
    std::cout << "Throughput (MB/s): " << throughput_MBps << "\n";
    std::cout << "Average latency (s): " << avg_latency << "\n";
    std::cout << "Results saved to " << results_path << "\n";
    std::cout << "Completed requests: " << result.completed_requests
              << " in " << result.finished_at << "s\n";

    return 0;
}
