// command_line_parser.hpp: Parses and validates command-line arguments for the simulator.
#pragma once

#include "simulator.hpp"

#include <string>
#include <vector>

namespace ssd {

/**
 * Command-line argument parser for the SSD fairness simulator.
 * Extracts and validates all simulation parameters from command-line arguments.
 */
struct CommandLineArgs {
    std::string trace_path = "traces/example.csv";
    std::string scheduler_policy = "flin";
    double quantum = 4096.0;
    std::string weights_str;
    int override_users = -1;
    int override_channels = -1;
    double read_bw_MBps = 2000.0;
    double write_bw_MBps = 1200.0;
    std::string results_path = "results/results.csv";
    
    // FLIN scheduler parameters
    double flin_window_sec = 0.1;
    double flin_fairness_alpha = 0.1;
    double flin_read_alpha = 0.1;
    double flin_read_bias = 0.25;
    double flin_starvation_window = 0.2;
    int flin_parallelism_trigger = 2;
    
    // Wear-leveling scheduler parameters
    double wear_hot_threshold = 4.0;
    int wear_pool_size = 16;
    bool wear_read_balance = false;
    int wear_num_segments = 8;
    std::size_t wear_rebalance_interval = 1000;
    double wear_rebalance_fraction = 0.05;
    bool wear_enable_min_cap = false;
    std::uint64_t wear_min_cap_delta = 8;
    int wear_min_cap_pool_size = 32;
};

/**
 * Parses command-line arguments and populates a CommandLineArgs structure.
 * Returns true on success, false if help was requested or on parse error.
 */
bool parse_command_line(int argc, char** argv, CommandLineArgs& args, bool& help_requested);

/**
 * Prints usage information to stdout.
 */
void print_usage();

/**
 * Converts comma-separated weights string to a vector of doubles.
 */
std::vector<double> parse_weights(const std::string& weights_str);

/**
 * Builds SimulationOptions from parsed command-line arguments and trace data.
 */
SimulationOptions build_simulation_options(const CommandLineArgs& args, 
                                          const std::vector<Request>& trace);

} // namespace ssd

