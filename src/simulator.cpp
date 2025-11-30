// simulator.cpp: Event-loop driver that dispatches requests via an SSD model.
#include "simulator.hpp"

#include "events.hpp"
#include "scheduler_impl.hpp"
#include "ssd.hpp"

#include <stdexcept>
#include <utility>

namespace ssd {

Simulator::Simulator(SimulationOptions opts) : opts_(std::move(opts)) {}

SimulationResult Simulator::run(std::unique_ptr<Scheduler> scheduler,
                                const std::vector<Request>& trace) const {
    if (!scheduler) {
        throw std::invalid_argument("Simulator::run requires a scheduler instance");
    }

    int num_users = 0;
    for (const auto& r : trace)
        if (r.user_id + 1 > num_users)
            num_users = r.user_id + 1;

    scheduler->set_users(num_users);
    scheduler->set_quantum(opts_.scheduler.quantum);
    if (!opts_.scheduler.weights.empty()) {
        scheduler->set_weights(opts_.scheduler.weights);
    }
    if (auto* flin = dynamic_cast<FlinScheduler*>(scheduler.get())) {
        FlinConfig cfg;
        cfg.window_sec = opts_.scheduler.flin_window_sec;
        cfg.fairness_alpha = opts_.scheduler.flin_fairness_alpha;
        cfg.read_alpha = opts_.scheduler.flin_read_alpha;
        cfg.read_bias_strength = opts_.scheduler.flin_read_bias;
        cfg.starvation_window = opts_.scheduler.flin_starvation_window;
        cfg.parallelism_trigger = opts_.scheduler.flin_parallelism_trigger;
        flin->set_config(cfg);
    }

    if (auto* wear = dynamic_cast<WearLevelScheduler*>(scheduler.get())) {
        WearLevelConfig wcfg;
        wcfg.hot_threshold = opts_.scheduler.wear_hot_threshold;
        wcfg.pool_size = opts_.scheduler.wear_pool_size;
        wcfg.balance_reads = opts_.scheduler.wear_read_balance;
        int channels = opts_.device_cfg.num_channels > 0 ? opts_.device_cfg.num_channels : 1;
        wcfg.total_blocks = static_cast<std::size_t>(channels) * 1024;
        wear->set_wear_config(wcfg, opts_.device_cfg.num_channels);
    }

    SSD device(opts_.device_cfg);
    EventQueue queue;
    Metrics metrics(num_users);

    size_t next_request = 0;
    double now = 0.0;
    size_t completed = 0;
    int last_read_channel = -1;

    while (next_request < trace.size() || !scheduler->empty() || !queue.empty()) {
        while (next_request < trace.size() && trace[next_request].arrival_ts <= now) {
            scheduler->enqueue(trace[next_request]);
            ++next_request;
        }

        while (true) {
            int any_free = device.first_free_channel(now);
            if (any_free < 0) break;

            auto uid = scheduler->pick_user(now);
            if (!uid) break;

            auto req = scheduler->pop(*uid);
            if (!req) break;

            int chan = any_free;
            if (opts_.scheduler.wear_read_balance && req->op == OpType::READ) {
                int num_ch = device.num_channels();
                if (num_ch > 0) {
                    int start = (last_read_channel + 1 + num_ch) % num_ch;
                    for (int i = 0; i < num_ch; ++i) {
                        int cand = (start + i) % num_ch;
                        if (device.is_free(cand, now)) {
                            chan = cand;
                            break;
                        }
                    }
                }
                last_read_channel = chan;
            }

            req->start_ts = now;
            req->finish_ts = device.dispatch(chan, *req, now);
            queue.push({ req->finish_ts, chan, *req });
        }

        if (!queue.empty()) {
            now = queue.top().time;
            auto ev = queue.pop();
            scheduler->on_request_finished(ev.request, now, &metrics);
            metrics.on_finish(ev.request);
            ++completed;
        } else if (next_request < trace.size()) {
            now = trace[next_request].arrival_ts;
        } else {
            break;
        }
    }

    if (opts_.write_results && !opts_.results_path.empty()) {
        metrics.save_csv(opts_.results_path);
    }

    return SimulationResult{std::move(metrics), now, completed};
}

} // namespace ssd
