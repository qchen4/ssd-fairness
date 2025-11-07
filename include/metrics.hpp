#pragma once

#include "types.hpp"

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace ssd {

class Metrics {
public:
    explicit Metrics(int num_users = 0);

    void reset(int num_users);

    void on_finish(const Request& req);

    double avg_latency(int user_id) const;
    uint64_t total_bytes(int user_id) const;
    size_t completed(int user_id) const;

    double fairness_index() const;

    // Writes per-user stats to CSV. Returns true on success.
    bool save_csv(const std::string& path) const;

private:
    struct UserStats {
        size_t completed = 0;
        double total_latency = 0.0;
        uint64_t bytes = 0;
    };

    std::vector<UserStats> stats_;
};

} // namespace ssd
