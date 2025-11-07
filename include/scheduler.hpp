#pragma once

#include "types.hpp"

#include <optional>
#include <vector>

namespace ssd {

/**
 * Base scheduler interface implemented by all scheduling policies.
 *
 * The simulator interacts with the scheduler using three operations:
 *   - enqueue(): admit a new request to the scheduler.
 *   - pick_user(): select the next user id to dispatch (if any).
 *   - pop(): remove and return the request for the chosen user.
 *
 * Schedulers are also told how many users exist (set_users) and can optionally
 * accept per-user weights or a quantum size.
 */
class Scheduler {
public:
    virtual ~Scheduler() = default;

    virtual void set_users(int n) = 0;

    // Optional knobs. Default implementations ignore the parameters.
    virtual void set_weights(const std::vector<double>&) {}
    virtual void set_quantum(double) {}

    virtual void enqueue(const Request& r) = 0;
    virtual std::optional<int> pick_user(double virtual_time) = 0;
    virtual std::optional<Request> pop(int uid) = 0;
    virtual bool empty() const = 0;
};

} // namespace ssd
