// SPDX-License-Identifier: MIT
// main.cpp: Command-line driver that wires traces, schedulers, and the simulator.

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
    auto print_usage = []() {
        std::cout << "Usage: ssd-fairness [options]\n"
                  << "  -t, --trace PATH               Input trace CSV or blktrace text file\n"
                  << "  -s, --scheduler NAME           fifo | rr | drr | qfq | wfq | flin\n"
                  << "  -q, --quantum BYTES            DRR quantum size\n"
                  << "  -u, --users N                  Override number of users (else inferred)\n"
                  << "  -c, --channels N               Number of SSD channels\n"
                  << "  -r, --read-bw MBPS             Aggregate read bandwidth\n"
                  << "  -w, --write-bw MBPS            Aggregate write bandwidth\n"
                  << "  -W, --weights CSV              Comma-separated per-user weights\n"
                  << "  -o, --results PATH             Per-user summary CSV output path\n"
                  << "      --flin-window-sec SEC      FLIN EWMA window for service accounting\n"
                  << "      --flin-fairness-alpha A    FLIN slowdown smoothing factor\n"
                  << "      --flin-read-alpha A        FLIN read/write mix smoothing factor\n"
                  << "      --flin-read-bias B         Bias toward read-heavy flows (0..1)\n"
                  << "      --flin-starvation-window S Idle time before FLIN boosts a flow\n"
                  << "      --flin-parallelism-trigger N Outstanding threshold for size-aware insert\n"
                  << "Example: ./ssd-fairness --trace traces/ssdtrace-sample --scheduler flin\n";
    };

    std::string trace_path = "traces/example.csv";
    std::string policy_str = "flin"; // fifo, rr, drr, wfq, flin
    double quantum = 4096.0;
    std::string weights_str;
    int override_users = -1;
    int override_channels = -1;
    double read_bw = 2000;
    double write_bw = 1200;
    std::string results_path = "results/results.csv";
    double flin_window_sec = 0.1;
    double flin_fairness_alpha = 0.1;
    double flin_read_alpha = 0.1;
    double flin_read_bias = 0.25;
    double flin_starvation_window = 0.2;
    int flin_parallelism_trigger = 2;

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
        {"help", no_argument, 0, 'h'},
        {"flin-window-sec", required_argument, 0, 0},
        {"flin-fairness-alpha", required_argument, 0, 0},
        {"flin-read-alpha", required_argument, 0, 0},
        {"flin-read-bias", required_argument, 0, 0},
        {"flin-starvation-window", required_argument, 0, 0},
        {"flin-parallelism-trigger", required_argument, 0, 0},
        {0,0,0,0}
    };

    int opt = 0;
    int long_index = 0;
    while ((opt = getopt_long(argc, argv, "t:s:q:u:c:r:w:W:o:h", longopts, &long_index)) != -1) {
        if (opt == 't') trace_path = optarg;
        else if (opt == 's') policy_str = optarg;
        else if (opt == 'q') quantum = atof(optarg);
        else if (opt == 'u') override_users = atoi(optarg);
        else if (opt == 'c') override_channels = atoi(optarg);
        else if (opt == 'r') read_bw = atof(optarg);
        else if (opt == 'w') write_bw = atof(optarg);
        else if (opt == 'W') weights_str = optarg;
        else if (opt == 'o') results_path = optarg;
        else if (opt == 'h') {
            print_usage();
            return 0;
        }
        else if (opt == 0 && std::string(longopts[long_index].name) == "flin-window-sec") {
            flin_window_sec = atof(optarg);
        } else if (opt == 0 && std::string(longopts[long_index].name) == "flin-fairness-alpha") {
            flin_fairness_alpha = atof(optarg);
        } else if (opt == 0 && std::string(longopts[long_index].name) == "flin-read-alpha") {
            flin_read_alpha = atof(optarg);
        } else if (opt == 0 && std::string(longopts[long_index].name) == "flin-read-bias") {
            flin_read_bias = atof(optarg);
        } else if (opt == 0 && std::string(longopts[long_index].name) == "flin-starvation-window") {
            flin_starvation_window = atof(optarg);
        } else if (opt == 0 && std::string(longopts[long_index].name) == "flin-parallelism-trigger") {
            flin_parallelism_trigger = atoi(optarg);
        } else {
            print_usage();
            return 1;
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
    sched_settings.flin_window_sec = flin_window_sec;
    sched_settings.flin_fairness_alpha = flin_fairness_alpha;
    sched_settings.flin_read_alpha = flin_read_alpha;
    sched_settings.flin_read_bias = flin_read_bias;
    sched_settings.flin_starvation_window = flin_starvation_window;
    sched_settings.flin_parallelism_trigger = flin_parallelism_trigger;

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
    double slowdown_sum = 0.0;
    int slowdown_participants = 0;
    for (int uid = 0; uid < result.metrics.users(); ++uid) {
        total_bytes += result.metrics.total_bytes(uid);
        const size_t completed = result.metrics.completed(uid);
        total_completed += completed;
        latency_sum += result.metrics.avg_latency(uid) * static_cast<double>(completed);
        if (result.metrics.has_fairness(uid)) {
            slowdown_sum += result.metrics.fairness_avg(uid);
            ++slowdown_participants;
        }
    }
    double avg_latency = total_completed ? latency_sum / static_cast<double>(total_completed) : 0.0;
    double throughput_MBps = result.finished_at > 0.0
        ? (static_cast<double>(total_bytes) / (1024.0 * 1024.0)) / result.finished_at
        : 0.0;
    double throughput_fairness = result.metrics.throughput_fairness_index(result.finished_at);
    double avg_slowdown = slowdown_participants > 0
        ? slowdown_sum / static_cast<double>(slowdown_participants)
        : 0.0;

    std::cout << "Simulation complete.\n";
    std::cout << "Fairness Index: " << result.metrics.fairness_index() << "\n";
    std::cout << "Throughput Fairness Index: " << throughput_fairness << "\n";
    std::cout << "Average slowdown: " << avg_slowdown << "\n";
    std::cout << "Throughput (MB/s): " << throughput_MBps << "\n";
    std::cout << "Average latency (s): " << avg_latency << "\n";
    std::cout << "Results saved to " << results_path << "\n";
    std::cout << "Completed requests: " << result.completed_requests
              << " in " << result.finished_at << "s\n";

    return 0;
}
