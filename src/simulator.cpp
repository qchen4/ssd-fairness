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

    SSD device(opts_.device_cfg);
    EventQueue queue;
    Metrics metrics(num_users);

    size_t next_request = 0;
    double now = 0.0;
    size_t completed = 0;

    while (next_request < trace.size() || !scheduler->empty() || !queue.empty()) {
        while (next_request < trace.size() && trace[next_request].arrival_ts <= now) {
            scheduler->enqueue(trace[next_request]);
            ++next_request;
        }

        while (true) {
            int chan = device.first_free_channel(now);
            if (chan < 0) break;

            auto uid = scheduler->pick_user(now);
            if (!uid) break;

            auto req = scheduler->pop(*uid);
            if (!req) break;

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
