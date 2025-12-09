// simulator.cpp: Event-loop driver that dispatches requests via an SSD model.
#include "simulator.hpp"

#include "events.hpp"
#include "scheduler_impl.hpp"
#include "ssd.hpp"

#include <algorithm>
#include <stdexcept>
#include <utility>

namespace ssd {

namespace {
    // Helper functions to configure specific scheduler types
    
    /**
     * Configures a FLIN scheduler with the provided settings.
     */
    void configure_flin_scheduler(FlinScheduler* flin, const SchedulerSettings& settings) {
        FlinConfig cfg;
        cfg.window_sec = settings.flin_window_sec;
        cfg.fairness_alpha = settings.flin_fairness_alpha;
        cfg.read_alpha = settings.flin_read_alpha;
        cfg.read_bias_strength = settings.flin_read_bias;
        cfg.starvation_window = settings.flin_starvation_window;
        cfg.parallelism_trigger = settings.flin_parallelism_trigger;
        flin->set_config(cfg);
    }
    
    /**
     * Configures a wear-leveling scheduler with the provided settings.
     */
    void configure_wear_scheduler(WearLevelScheduler* wear, 
                                   const SchedulerSettings& settings,
                                   int num_channels) {
        WearLevelConfig wcfg;
        wcfg.hot_threshold = settings.wear_hot_threshold;
        wcfg.pool_size = settings.wear_pool_size;
        wcfg.balance_reads = settings.wear_read_balance;
        wcfg.num_segments = std::max(1, settings.wear_num_segments);
        wcfg.rebalance_interval = settings.wear_rebalance_interval;
        wcfg.rebalance_fraction = std::max(0.0, settings.wear_rebalance_fraction);
        wcfg.enable_min_cap_wl = settings.wear_enable_min_cap;
        wcfg.hot_min_cap_delta = settings.wear_min_cap_delta;
        wcfg.hot_min_cap_pool_size = settings.wear_min_cap_pool_size;
        
        const int channels = num_channels > 0 ? num_channels : 1;
        wcfg.total_blocks = static_cast<std::size_t>(channels) * 1024;
        wear->set_wear_config(wcfg, num_channels);
    }
    
    /**
     * Counts the number of unique users in a trace.
     */
    int count_users_in_trace(const std::vector<Request>& trace) {
        int max_user_id = -1;
        for (const auto& req : trace) {
            if (req.user_id > max_user_id) {
                max_user_id = req.user_id;
            }
        }
        return max_user_id + 1;
    }
    
    /**
     * Selects the appropriate channel for a read request when read balancing is enabled.
     * Returns the channel index to use, or -1 if no suitable channel is found.
     */
    int select_read_channel(const SSD& device, 
                            int last_used_channel,
                            double current_time) {
        const int num_channels = device.num_channels();
        if (num_channels <= 0) {
            return -1;
        }
        
        // Start searching from the next channel after the last used one
        const int start_channel = (last_used_channel + 1) % num_channels;
        for (int i = 0; i < num_channels; ++i) {
            const int candidate = (start_channel + i) % num_channels;
            if (device.is_free(candidate, current_time)) {
                return candidate;
            }
        }
        return -1;
    }
} // anonymous namespace

Simulator::Simulator(SimulationOptions opts) : opts_(std::move(opts)) {}

SimulationResult Simulator::run(std::unique_ptr<Scheduler> scheduler,
                                const std::vector<Request>& trace) const {
    if (!scheduler) {
        throw std::invalid_argument("Simulator::run requires a scheduler instance");
    }

    // Determine number of users from trace
    const int num_users = count_users_in_trace(trace);
    
    // Configure the scheduler
    scheduler->set_users(num_users);
    scheduler->set_quantum(opts_.scheduler.quantum);
    if (!opts_.scheduler.weights.empty()) {
        scheduler->set_weights(opts_.scheduler.weights);
    }
    
    // Apply scheduler-specific configuration
    if (auto* flin = dynamic_cast<FlinScheduler*>(scheduler.get())) {
        configure_flin_scheduler(flin, opts_.scheduler);
    } else if (auto* wear = dynamic_cast<WearLevelScheduler*>(scheduler.get())) {
        configure_wear_scheduler(wear, opts_.scheduler, opts_.device_cfg.num_channels);
    }

    // Initialize simulation state
    SSD device(opts_.device_cfg);
    EventQueue completion_queue;
    Metrics metrics(num_users);

    size_t next_arrival_index = 0;
    double current_time = 0.0;
    size_t completed_count = 0;
    int last_read_channel = -1;

    // Main simulation event loop
    while (next_arrival_index < trace.size() || !scheduler->empty() || !completion_queue.empty()) {
        // Admit new requests that have arrived
        while (next_arrival_index < trace.size() && 
               trace[next_arrival_index].arrival_ts <= current_time) {
            scheduler->enqueue(trace[next_arrival_index]);
            ++next_arrival_index;
        }

        // Dispatch ready requests to available channels
        while (true) {
            const int free_channel = device.first_free_channel(current_time);
            if (free_channel < 0) {
                break; // No free channels
            }

            const auto selected_user = scheduler->pick_user(current_time);
            if (!selected_user) {
                break; // No user has pending work
            }

            auto request = scheduler->pop(*selected_user);
            if (!request) {
                break; // Could not pop request for selected user
            }

            // Select channel (with read balancing if enabled)
            int target_channel = free_channel;
            if (opts_.scheduler.wear_read_balance && request->op == OpType::READ) {
                const int balanced_channel = select_read_channel(device, 
                                                                 last_read_channel, 
                                                                 current_time);
                if (balanced_channel >= 0) {
                    target_channel = balanced_channel;
                }
                last_read_channel = target_channel;
            }

            // Dispatch request to SSD and schedule completion event
            request->start_ts = current_time;
            request->finish_ts = device.dispatch(target_channel, *request, current_time);
            completion_queue.push({request->finish_ts, target_channel, *request});
        }

        // Process next completion event or advance time
        if (!completion_queue.empty()) {
            // Process the earliest completion
            current_time = completion_queue.top().time;
            const Event completed_event = completion_queue.pop();
            
            scheduler->on_request_finished(completed_event.request, current_time, &metrics);
            metrics.on_finish(completed_event.request);
            ++completed_count;
        } else if (next_arrival_index < trace.size()) {
            // No completions pending, advance to next arrival
            current_time = trace[next_arrival_index].arrival_ts;
        } else {
            // No more work to do
            break;
        }
    }

    // Record wear statistics if available
    if (!device.wear_counts().empty()) {
        metrics.record_wear_snapshot(device.wear_counts());
    }

    // Save results if requested
    if (opts_.write_results && !opts_.results_path.empty()) {
        metrics.save_csv(opts_.results_path);
    }

    return SimulationResult{std::move(metrics), current_time, completed_count};
}

} // namespace ssd


        // Dispatch ready requests to available channels
        while (true) {
            const int free_channel = device.first_free_channel(current_time);
            if (free_channel < 0) {
                break; // No free channels
            }

            const auto selected_user = scheduler->pick_user(current_time);
            if (!selected_user) {
                break; // No user has pending work
            }

            auto request = scheduler->pop(*selected_user);
            if (!request) {
                break; // Could not pop request for selected user
            }

            // Select channel (with read balancing if enabled)
            int target_channel = free_channel;
            if (opts_.scheduler.wear_read_balance && request->op == OpType::READ) {
                const int balanced_channel = select_read_channel(device, 
                                                                 last_read_channel, 
                                                                 current_time);
                if (balanced_channel >= 0) {
                    target_channel = balanced_channel;
                }
                last_read_channel = target_channel;
            }

            // Dispatch request to SSD and schedule completion event
            request->start_ts = current_time;
            request->finish_ts = device.dispatch(target_channel, *request, current_time);
            completion_queue.push({request->finish_ts, target_channel, *request});
        }

        // Process next completion event or advance time
        if (!completion_queue.empty()) {
            // Process the earliest completion
            current_time = completion_queue.top().time;
            const Event completed_event = completion_queue.pop();
            
            scheduler->on_request_finished(completed_event.request, current_time, &metrics);
            metrics.on_finish(completed_event.request);
            ++completed_count;
        } else if (next_arrival_index < trace.size()) {
            // No completions pending, advance to next arrival
            current_time = trace[next_arrival_index].arrival_ts;
        } else {
            // No more work to do
            break;
        }
    }

    // Record wear statistics if available
    if (!device.wear_counts().empty()) {
        metrics.record_wear_snapshot(device.wear_counts());
    }

    // Save results if requested
    if (opts_.write_results && !opts_.results_path.empty()) {
        metrics.save_csv(opts_.results_path);
    }

    return SimulationResult{std::move(metrics), current_time, completed_count};
}

} // namespace ssd
