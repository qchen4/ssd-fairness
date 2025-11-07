// SPDX-License-Identifier: MIT
// Main simulation driver for the SSD fairness scheduling simulator.

#include "types.hpp"
#include "util.hpp"
#include "scheduler.hpp"
#include "scheduler_impl.hpp"
#include "ssd.hpp"
#include "events.hpp"
#include "metrics.hpp"

#include <iostream>
#include <fstream>
#include <sstream>
#include <string>
#include <memory>
#include <getopt.h>

int main(int argc, char** argv) {
    // ==== Configuration Parameters ====
    std::string trace_path = "traces/example.csv";   // Path to request trace
    std::string policy_str = "qfq";                  // Scheduler type: rr, drr, qfq, sgfs
    double quantum = 4096.0;                         // DRR quantum (bytes)
    std::string weights_str;                         // Comma-separated weights string
    int override_users = -1;
    int override_channels = -1;
    double read_bw = 2000;       // Default read bandwidth (MB/s)
    double write_bw = 1200;      // Default write bandwidth (MB/s)
    int sgfs_rotate_every = 200; // SGFS rotation interval
    int sgfs_gap = 1;            // SGFS rotation stride

    // Parse command line options
    static option longopts[] = {
        {"trace", required_argument, 0, 't'},
        {"scheduler", required_argument, 0, 's'},
        {"quantum", required_argument, 0, 'q'},
        {"users", required_argument, 0, 'u'},
        {"channels", required_argument, 0, 'c'},
        {"read-bw", required_argument, 0, 'r'},
        {"write-bw", required_argument, 0, 'w'},
        {"weights", required_argument, 0, 'W'},
        {0,0,0,0}
    };

    int opt, idx=0;
    while ((opt = getopt_long(argc, argv, "t:s:q:u:c:r:w:W:", longopts, &idx)) != -1) {
        if (opt=='t') trace_path = optarg;
        else if (opt=='s') policy_str = optarg;
        else if (opt=='q') quantum = atof(optarg);
        else if (opt=='u') override_users = atoi(optarg);
        else if (opt=='c') override_channels = atoi(optarg);
        else if (opt=='r') read_bw = atof(optarg);
        else if (opt=='w') write_bw = atof(optarg);
        else if (opt=='W') weights_str = optarg;
    }

    // ==== Load trace ====
    auto trace = util::load_trace_csv(trace_path);

    // ==== Determine number of users from trace or override ====
    int num_users = override_users > 0 ? override_users : 0;
    for (const auto& r : trace)
        if (r.user_id + 1 > num_users)
            num_users = r.user_id + 1;

    // ==== Setup simulation config ====
    int num_channels = override_channels > 0 ? override_channels : 8;
    SimConfig sim_cfg { num_users, num_channels, read_bw, write_bw };

    // ==== Create scheduler based on requested policy ====
    std::unique_ptr<ssd::Scheduler> scheduler;
    if (policy_str == "rr") {
        scheduler = std::make_unique<ssd::RoundRobinScheduler>();
    } else if (policy_str == "drr") {
        auto drr = std::make_unique<ssd::DeficitRoundRobinScheduler>();
        drr->set_quantum(quantum);
        scheduler = std::move(drr);
    } else if (policy_str == "qfq") {
        scheduler = std::make_unique<ssd::WeightedFairScheduler>();
    } else if (policy_str == "sgfs") {
        // SGFS wraps a base scheduler and rotates mappings
        auto base = std::make_unique<ssd::WeightedFairScheduler>();
        auto sgfs = std::make_unique<ssd::StartGapScheduler>(std::move(base));
        sgfs->set_start_gap(sgfs_rotate_every, sgfs_gap);
        scheduler = std::move(sgfs);
    } else {
        std::cerr << "Unknown scheduler policy: " << policy_str << "\n";
        return 1;
    }

    // ==== Initialize scheduler and set weights if provided ====
    scheduler->set_users(num_users);
    scheduler->set_quantum(quantum);

    if (!weights_str.empty()) {
        std::vector<double> weights;
        std::stringstream ss(weights_str);
        std::string token;
        while (std::getline(ss, token, ',')) {
            weights.push_back(std::stod(token));
        }
        scheduler->set_weights(weights);
    }

    // ==== Initialize SSD, event queue, and metrics tracker ====
    ssd::SSD device(sim_cfg);
    ssd::EventQueue queue;
    ssd::Metrics metrics(num_users);

    // ==== Main Simulation Loop ====
    size_t i = 0;       // Index into trace
    double now = 0.0;   // Current simulation time

    // Drive the event loop until all requests have been admitted and completed.
    while (i < trace.size() || !scheduler->empty() || !queue.empty()) {
        // 1. Admit all trace arrivals with timestamp <= now.
        while (i < trace.size() && trace[i].arrival_ts <= now) {
            scheduler->enqueue(trace[i]);
            ++i;
        }

        // 2. Dispatch requests while channels are free. Each dispatch both
        // dequeues a request and schedules a corresponding completion event.
        while (true) {
            int chan = device.first_free_channel(now);
            if (chan < 0) break;  // No free channels

            auto uid = scheduler->pick_user(now);
            if (!uid) break;

            auto req = scheduler->pop(*uid);
            if (!req) break;

            req->start_ts = now;
            req->finish_ts = device.dispatch(chan, *req, now);
            queue.push({ req->finish_ts, chan, *req });
        }

        // 3. Process next event (completion) when work is in-flight.
        if (!queue.empty()) {
            now = queue.top().time;             // Advance to next event time
            auto ev = queue.pop();              // Pop event
            metrics.on_finish(ev.request);      // Log stats
        }
        // 4. Otherwise fast-forward to the next arrival if more requests exist.
        else if (i < trace.size()) {
            now = trace[i].arrival_ts;
        }
        // 5. Done
        else break;
    }

    // ==== Output Results ====
    if (!metrics.save_csv("build/results.csv")) {
        std::cerr << "Warning: failed to write build/results.csv\n";
    }

    std::cout << "Simulation complete.\n";
    std::cout << "Fairness Index: " << metrics.fairness_index() << "\n";
    std::cout << "Results saved to build/results.csv\n";

    return 0;
}
