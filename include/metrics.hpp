#pragma once

#include "types.hpp"

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace ssd {

// Metrics collects per-user throughput and latency statistics.
class Metrics {
public:
    explicit Metrics(int num_users = 0);

    void reset(int num_users);

    // on_finish ingests a completed request and updates aggregates.
    void on_finish(const Request& req);

    // avg_latency returns the mean latency (seconds) for |user_id|.
    double avg_latency(int user_id) const;
    // total_bytes returns the accumulated bytes served by |user_id|.
    uint64_t total_bytes(int user_id) const;
    // completed returns the number of finished requests for |user_id|.
    size_t completed(int user_id) const;

    // fairness_index returns Jain's fairness metric over non-idle users.
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
