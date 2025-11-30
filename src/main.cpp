// SPDX-License-Identifier: MIT
// Main simulation driver for the SSD fairness scheduling simulator.

#include "scheduler_factory.hpp"
#include "simulator.hpp"
#include "trace_reader.hpp"

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include "getopt_compat.hpp"
#include <iostream>
#include <map>
#include <memory>
#include <sstream>
#include <string>
#include <vector>

namespace {

// Workload analyzer for automatic algorithm selection
struct WorkloadProfile {
    int num_users;
    size_t total_requests;
    uint32_t min_size;
    uint32_t max_size;
    double size_ratio;
    double overall_read_ratio;
    double read_ratio_variance;
    bool has_pure_read_user;
    bool has_pure_write_user;
    bool has_burst;
    
    WorkloadProfile() : num_users(0), total_requests(0), min_size(UINT32_MAX), 
        max_size(0), size_ratio(1.0), overall_read_ratio(0.5), 
        read_ratio_variance(0.0), has_pure_read_user(false), 
        has_pure_write_user(false), has_burst(false) {}
};

WorkloadProfile analyze_workload(const std::vector<Request>& trace) {
    WorkloadProfile profile;
    if (trace.empty()) return profile;
    
    std::map<int, size_t> user_reads, user_writes;
    std::map<int, size_t> user_counts;
    std::map<double, int> timestamp_counts;
    
    for (size_t i = 0; i < trace.size(); ++i) {
        const Request& req = trace[i];
        profile.total_requests++;
        if (req.size_bytes < profile.min_size) profile.min_size = req.size_bytes;
        if (req.size_bytes > profile.max_size) profile.max_size = req.size_bytes;
        
        if (req.op == OpType::READ) {
            user_reads[req.user_id]++;
        } else {
            user_writes[req.user_id]++;
        }
        user_counts[req.user_id]++;
        timestamp_counts[req.arrival_ts]++;
    }
    
    profile.num_users = static_cast<int>(user_counts.size());
    profile.size_ratio = (profile.min_size > 0) 
        ? static_cast<double>(profile.max_size) / profile.min_size 
        : 1.0;
    
    // Calculate read/write ratios
    size_t total_reads = 0, total_writes = 0;
    std::vector<double> read_ratios;
    
    for (std::map<int, size_t>::iterator it = user_counts.begin(); it != user_counts.end(); ++it) {
        int uid = it->first;
        size_t reads = user_reads[uid];
        size_t writes = user_writes[uid];
        total_reads += reads;
        total_writes += writes;
        
        double ratio = (reads + writes > 0) 
            ? static_cast<double>(reads) / (reads + writes) 
            : 0.5;
        read_ratios.push_back(ratio);
        
        if (ratio > 0.95) profile.has_pure_read_user = true;
        if (ratio < 0.05) profile.has_pure_write_user = true;
    }
    
    profile.overall_read_ratio = (total_reads + total_writes > 0)
        ? static_cast<double>(total_reads) / (total_reads + total_writes)
        : 0.5;
    
    // Variance of read ratios
    if (!read_ratios.empty()) {
        double avg = 0;
        for (size_t i = 0; i < read_ratios.size(); ++i) avg += read_ratios[i];
        avg /= read_ratios.size();
        
        double var = 0;
        for (size_t i = 0; i < read_ratios.size(); ++i) {
            double diff = read_ratios[i] - avg;
            var += diff * diff;
        }
        profile.read_ratio_variance = var / read_ratios.size();
    }
    
    // Detect burst
    int max_concurrent = 0;
    for (std::map<double, int>::iterator it = timestamp_counts.begin(); it != timestamp_counts.end(); ++it) {
        if (it->second > max_concurrent) max_concurrent = it->second;
    }
    profile.has_burst = max_concurrent > profile.num_users * 2;
    
    return profile;
}

std::string select_algorithm(const WorkloadProfile& profile, bool has_weights = false) {
    double score_rr = 0, score_drr = 0, score_qfq = 0, score_flin = 0;
    
    // Rule 1: Size variance → DRR or QFQ
    if (profile.size_ratio > 16) {
        score_drr += 3.0;
        score_qfq += 2.5;  // QFQ also good for large size variance
    } else if (profile.size_ratio > 4) {
        score_drr += 2.0;
        score_qfq += 1.5;
    } else {
        score_rr += 1.0;
    }
    
    // Rule 2: Read/write variance → FLIN
    if (profile.read_ratio_variance > 0.1) {
        score_flin += 3.0;
    } else if (profile.read_ratio_variance > 0.05) {
        score_flin += 1.5;
    }
    
    // Rule 3: Pure read/write users → FLIN
    if (profile.has_pure_read_user && profile.has_pure_write_user) {
        score_flin += 2.0;
    }
    
    // Rule 4: Simple scenario → RR
    if (profile.size_ratio < 2 && profile.read_ratio_variance < 0.01) {
        score_rr += 1.5;
    }
    
    // Rule 5: Weights specified → QFQ (weighted fair queueing)
    if (has_weights) {
        score_qfq += 5.0;  // Strong preference for QFQ when weights are needed
    }
    
    // Rule 6: High contention (burst) with varied sizes → QFQ
    // QFQ's virtual time scheduling is more precise under high contention
    if (profile.has_burst && profile.size_ratio > 2) {
        score_qfq += 2.0;
    }
    
    // Rule 7: Many users (>4) with size variance → QFQ
    // QFQ scales better with more flows
    if (profile.num_users > 4 && profile.size_ratio > 4) {
        score_qfq += 1.5;
    }
    
    // Select best
    std::string best = "rr";
    double best_score = score_rr;
    if (score_drr > best_score) { best = "drr"; best_score = score_drr; }
    if (score_qfq > best_score) { best = "qfq"; best_score = score_qfq; }
    if (score_flin > best_score) { best = "flin"; best_score = score_flin; }
    
    return best;
}

} // namespace

int main(int argc, char** argv) {
    std::string trace_path = "traces/example.csv";
    std::string policy_str = "qfq"; // rr, drr, qfq, sgfs, auto
    std::string goal_str;  // Fairness goal: request, byte, latency, slowdown
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
        {"goal", required_argument, 0, 'g'},  // NEW: fairness goal
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
    while ((opt = getopt_long(argc, argv, "t:s:g:q:u:c:r:w:W:o:", longopts, &long_index)) != -1) {
        if (opt == 't') trace_path = optarg;
        else if (opt == 's') policy_str = optarg;
        else if (opt == 'g') goal_str = optarg;  // NEW: fairness goal
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

    // Goal-based or automatic algorithm selection
    if (!goal_str.empty()) {
        // User specified a fairness goal
        if (goal_str == "request") {
            policy_str = "rr";
            std::cout << "=== Goal-Based Selection ===\n";
            std::cout << "Goal: Request Fairness -> RR\n";
            std::cout << "Metric: Jain(requests/user)\n";
        } else if (goal_str == "byte") {
            policy_str = "drr";
            std::cout << "=== Goal-Based Selection ===\n";
            std::cout << "Goal: Byte Fairness -> DRR\n";
            std::cout << "Metric: Jain(bytes/user)\n";
        } else if (goal_str == "latency") {
            policy_str = "qfq";
            std::cout << "=== Goal-Based Selection ===\n";
            std::cout << "Goal: Latency Fairness -> QFQ\n";
            std::cout << "Metric: Jain(1/latency)\n";
        } else if (goal_str == "slowdown") {
            policy_str = "flin";
            std::cout << "=== Goal-Based Selection ===\n";
            std::cout << "Goal: Slowdown Fairness -> FLIN\n";
            std::cout << "Metric: min(S)/max(S)\n";
        } else {
            std::cerr << "Unknown goal: " << goal_str << "\n";
            std::cerr << "Valid goals: request, byte, latency, slowdown\n";
            return 1;
        }
        std::cout << "================================\n\n";
    } else if (policy_str == "auto") {
        // Automatic algorithm selection based on workload
        WorkloadProfile profile = analyze_workload(trace);
        bool has_weights = !weights.empty();
        policy_str = select_algorithm(profile, has_weights);
        
        std::cout << "=== Auto Algorithm Selection ===\n";
        std::cout << "Workload Analysis:\n";
        std::cout << "  Users: " << profile.num_users << "\n";
        std::cout << "  Requests: " << profile.total_requests << "\n";
        std::cout << "  Size range: " << profile.min_size << " - " << profile.max_size 
                  << " (" << profile.size_ratio << "x)\n";
        std::cout << "  Read ratio: " << (profile.overall_read_ratio * 100) << "%\n";
        std::cout << "  R/W variance: " << profile.read_ratio_variance << "\n";
        std::cout << "  Pure read user: " << (profile.has_pure_read_user ? "yes" : "no") << "\n";
        std::cout << "  Pure write user: " << (profile.has_pure_write_user ? "yes" : "no") << "\n";
        std::cout << "  Burst detected: " << (profile.has_burst ? "yes" : "no") << "\n";
        std::cout << "\nSelected algorithm: " << policy_str << "\n";
        std::cout << "================================\n\n";
        
        // 如果选择 DRR，自动计算最佳 quantum
        if (policy_str == "drr" && quantum == 4096.0) {
            quantum = std::sqrt(static_cast<double>(profile.min_size) * profile.max_size);
            std::cout << "Auto quantum for DRR: " << quantum << " bytes\n\n";
        }
    }

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
    std::cout << "Fairness Index (combined): " << result.metrics.fairness_index() << "\n";
    std::cout << "Fairness Index (throughput): " << result.metrics.throughput_fairness_index() << "\n";
    std::cout << "Fairness Index (latency): " << result.metrics.latency_fairness_index() << "\n";
    std::cout << "Throughput (MB/s): " << throughput_MBps << "\n";
    std::cout << "Average latency (s): " << avg_latency << "\n";
    std::cout << "Results saved to " << results_path << "\n";
    std::cout << "Completed requests: " << result.completed_requests
              << " in " << result.finished_at << "s\n";

    return 0;
}
