// command_line_parser.cpp: Implementation of command-line argument parsing.
#include "command_line_parser.hpp"

#include <getopt.h>
#include <iostream>
#include <sstream>
#include <algorithm>

namespace ssd {

void print_usage() {
    std::cout << "Usage: ssd-fairness [options]\n"
              << "  -t, --trace PATH               Input trace CSV or blktrace text file\n"
              << "  -s, --scheduler NAME           fifo | rr | drr | qfq | wfq | flin | wear | minmax | bfq | bfq-lite\n"
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
              << "      --wear-hot-threshold X     Threshold for hot vs cold writes\n"
              << "      --wear-pool-size N         Candidate blocks examined per write\n"
              << "      --wear-read-balance        Enable read-balancing across channels\n"
              << "      --wear-num-segments N      Number of Min-Max segments (wear scheduler)\n"
              << "      --wear-rebalance-interval N  Hot writes between segment rebalances\n"
              << "      --wear-rebalance-fraction F Fraction of LBAs moved per rebalance\n"
              << "      --wear-enable-min-cap      Enable global min-cap wear-leveling\n"
              << "      --wear-min-cap-delta N     Allowed delta from global min erase for hot writes\n"
              << "      --wear-min-cap-pool-size N Number of candidate blocks to sample for WL2\n"
              << "Example: ./ssd-fairness --trace traces/ssdtrace-sample --scheduler flin\n";
}

std::vector<double> parse_weights(const std::string& weights_str) {
    std::vector<double> weights;
    if (weights_str.empty()) {
        return weights;
    }
    
    std::stringstream ss(weights_str);
    std::string token;
    while (std::getline(ss, token, ',')) {
        weights.push_back(std::stod(token));
    }
    return weights;
}

bool parse_command_line(int argc, char** argv, CommandLineArgs& args, bool& help_requested) {
    help_requested = false;
    
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
        {"wear-hot-threshold", required_argument, 0, 0},
        {"wear-pool-size", required_argument, 0, 0},
        {"wear-read-balance", no_argument, 0, 0},
        {"wear-num-segments", required_argument, 0, 0},
        {"wear-rebalance-interval", required_argument, 0, 0},
        {"wear-rebalance-fraction", required_argument, 0, 0},
        {"wear-enable-min-cap", no_argument, 0, 0},
        {"wear-min-cap-delta", required_argument, 0, 0},
        {"wear-min-cap-pool-size", required_argument, 0, 0},
        {0, 0, 0, 0}
    };

    int opt = 0;
    int long_index = 0;
    while ((opt = getopt_long(argc, argv, "t:s:q:u:c:r:w:W:o:h", longopts, &long_index)) != -1) {
        if (opt == 't') {
            args.trace_path = optarg;
        } else if (opt == 's') {
            args.scheduler_policy = optarg;
        } else if (opt == 'q') {
            args.quantum = std::atof(optarg);
        } else if (opt == 'u') {
            args.override_users = std::atoi(optarg);
        } else if (opt == 'c') {
            args.override_channels = std::atoi(optarg);
        } else if (opt == 'r') {
            args.read_bw_MBps = std::atof(optarg);
        } else if (opt == 'w') {
            args.write_bw_MBps = std::atof(optarg);
        } else if (opt == 'W') {
            args.weights_str = optarg;
        } else if (opt == 'o') {
            args.results_path = optarg;
        } else if (opt == 'h') {
            help_requested = true;
            return true;
        } else if (opt == 0) {
            // Handle long options without short equivalents
            const std::string option_name = longopts[long_index].name;
            
            if (option_name == "flin-window-sec") {
                args.flin_window_sec = std::atof(optarg);
            } else if (option_name == "flin-fairness-alpha") {
                args.flin_fairness_alpha = std::atof(optarg);
            } else if (option_name == "flin-read-alpha") {
                args.flin_read_alpha = std::atof(optarg);
            } else if (option_name == "flin-read-bias") {
                args.flin_read_bias = std::atof(optarg);
            } else if (option_name == "flin-starvation-window") {
                args.flin_starvation_window = std::atof(optarg);
            } else if (option_name == "flin-parallelism-trigger") {
                args.flin_parallelism_trigger = std::atoi(optarg);
            } else if (option_name == "wear-hot-threshold") {
                args.wear_hot_threshold = std::atof(optarg);
            } else if (option_name == "wear-pool-size") {
                args.wear_pool_size = std::atoi(optarg);
            } else if (option_name == "wear-read-balance") {
                args.wear_read_balance = true;
            } else if (option_name == "wear-num-segments") {
                args.wear_num_segments = std::max(1, std::atoi(optarg));
            } else if (option_name == "wear-rebalance-interval") {
                long long parsed = std::atoll(optarg);
                if (parsed < 0) parsed = 0;
                args.wear_rebalance_interval = static_cast<std::size_t>(parsed);
            } else if (option_name == "wear-rebalance-fraction") {
                args.wear_rebalance_fraction = std::atof(optarg);
                if (args.wear_rebalance_fraction < 0.0) {
                    args.wear_rebalance_fraction = 0.0;
                }
            } else if (option_name == "wear-enable-min-cap") {
                args.wear_enable_min_cap = true;
            } else if (option_name == "wear-min-cap-delta") {
                args.wear_min_cap_delta = static_cast<std::uint64_t>(std::strtoull(optarg, nullptr, 10));
            } else if (option_name == "wear-min-cap-pool-size") {
                args.wear_min_cap_pool_size = std::max(1, std::atoi(optarg));
            } else {
                // Unknown option
                return false;
            }
        } else {
            // Invalid option
            return false;
        }
    }
    
    return true;
}

SimulationOptions build_simulation_options(const CommandLineArgs& args, 
                                          const std::vector<Request>& trace) {
    // Determine number of users from trace or override
    int num_users = args.override_users > 0 ? args.override_users : 0;
    if (num_users == 0) {
        for (const auto& r : trace) {
            if (r.user_id + 1 > num_users) {
                num_users = r.user_id + 1;
            }
        }
    }
    
    // Determine number of channels
    const int num_channels = args.override_channels > 0 ? args.override_channels : 8;
    
    // Build device configuration
    SimConfig device_cfg;
    device_cfg.num_users = num_users;
    device_cfg.num_channels = num_channels;
    device_cfg.read_bw_MBps = args.read_bw_MBps;
    device_cfg.write_bw_MBps = args.write_bw_MBps;
    
    // Build scheduler settings
    SchedulerSettings sched_settings;
    sched_settings.quantum = args.quantum;
    sched_settings.weights = parse_weights(args.weights_str);
    sched_settings.flin_window_sec = args.flin_window_sec;
    sched_settings.flin_fairness_alpha = args.flin_fairness_alpha;
    sched_settings.flin_read_alpha = args.flin_read_alpha;
    sched_settings.flin_read_bias = args.flin_read_bias;
    sched_settings.flin_starvation_window = args.flin_starvation_window;
    sched_settings.flin_parallelism_trigger = args.flin_parallelism_trigger;
    sched_settings.wear_hot_threshold = args.wear_hot_threshold;
    sched_settings.wear_pool_size = args.wear_pool_size;
    sched_settings.wear_read_balance = args.wear_read_balance;
    sched_settings.wear_num_segments = args.wear_num_segments;
    sched_settings.wear_rebalance_interval = args.wear_rebalance_interval;
    sched_settings.wear_rebalance_fraction = args.wear_rebalance_fraction;
    sched_settings.wear_enable_min_cap = args.wear_enable_min_cap;
    sched_settings.wear_min_cap_delta = args.wear_min_cap_delta;
    sched_settings.wear_min_cap_pool_size = args.wear_min_cap_pool_size;
    
    // Build simulation options
    SimulationOptions opts;
    opts.device_cfg = device_cfg;
    opts.scheduler = sched_settings;
    opts.results_path = args.results_path;
    opts.write_results = true;
    
    return opts;
}

} // namespace ssd

