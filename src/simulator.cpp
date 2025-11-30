#include "simulator.hpp"

#include "events.hpp"
#include "ssd.hpp"

#include <algorithm>
#include <stdexcept>
#include <utility>

namespace ssd {

Simulator::Simulator(SimulationOptions opts) : opts_(std::move(opts)) {}

SimulationResult Simulator::run(std::unique_ptr<Scheduler> scheduler,
                                const std::vector<Request>& trace) const {
    if (!scheduler) {
        throw std::invalid_argument("Simulator::run requires a scheduler instance");
    }

    int inferred_users = 0;
    for (const auto& r : trace) {
        if (r.user_id >= 0 && r.user_id + 1 > inferred_users)
            inferred_users = r.user_id + 1;
    }
    int num_users = inferred_users;
    if (opts_.user_override > 0)
        num_users = std::max(num_users, opts_.user_override);

    scheduler->set_users(num_users);
    scheduler->set_quantum(opts_.scheduler.quantum);
    if (!opts_.scheduler.weights.empty()) {
        scheduler->set_weights(opts_.scheduler.weights);
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
