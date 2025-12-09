// SPDX-License-Identifier: MIT
// main.cpp: Command-line driver that wires traces, schedulers, and the simulator.

#include "command_line_parser.hpp"
#include "scheduler_factory.hpp"
#include "simulation_results.hpp"
#include "simulator.hpp"
#include "trace_reader.hpp"

#include <iostream>
#include <memory>

int main(int argc, char** argv) {
    // Parse command-line arguments
    ssd::CommandLineArgs args;
    bool help_requested = false;
    
    if (!ssd::parse_command_line(argc, argv, args, help_requested)) {
        ssd::print_usage();
        return 1;
    }
    
    if (help_requested) {
        ssd::print_usage();
        return 0;
    }
    
    // Load trace file
    ssd::TraceReader reader;
    auto trace = reader.load_csv(args.trace_path);
    
    if (trace.empty()) {
        std::cerr << "Error: No requests found in trace file: " << args.trace_path << "\n";
        return 1;
    }
    
    // Build simulation options from parsed arguments
    ssd::SimulationOptions sim_options = ssd::build_simulation_options(args, trace);
    
    // Create scheduler
    auto scheduler = ssd::make_scheduler(args.scheduler_policy);
    if (!scheduler) {
        std::cerr << "Error: Unknown scheduler policy: " << args.scheduler_policy << "\n";
        ssd::print_usage();
        return 1;
    }
    
    // Run simulation
    ssd::Simulator simulator(sim_options);
    auto result = simulator.run(std::move(scheduler), trace);
    
    // Compute and print statistics
    auto stats = ssd::compute_statistics(result);
    ssd::print_simulation_summary(result, stats, args.results_path);
    
    return 0;
}
