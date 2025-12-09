// Metrics helpers for collecting latency, throughput, and fairness statistics.
#pragma once

#include "types.hpp"

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace ssd {

// Metrics collects per-user throughput, latency, and fairness/slowdown statistics.
class Metrics {
public:
    explicit Metrics(int num_users = 0);

    // Resets internal aggregations for |num_users| tenants.
    void reset(int num_users);

    // on_finish ingests a completed request and updates aggregates.
    void on_finish(const Request& req);

    // record_fairness captures slowdown-style fairness for a user.
    // |instant_ratio| is the instantaneous actual_rate / fair_share ratio,
    // |ewma_ratio| is a smoothed version tracked by the scheduler.
    void record_fairness(int user_id, double instant_ratio, double ewma_ratio);

    // avg_latency returns the mean latency (seconds) for |user_id|.
    double avg_latency(int user_id) const;
    // percentile_latency returns the given latency percentile (0..1) in seconds.
    double percentile_latency(int user_id, double percentile) const;
    // total_bytes returns the accumulated bytes served by |user_id|.
    uint64_t total_bytes(int user_id) const;
    // completed returns the number of finished requests for |user_id|.
    size_t completed(int user_id) const;
    // fairness_ewma returns the slowdown metric tracked for |user_id|.
    double fairness_ewma(int user_id) const;
    // fairness_avg returns the average instantaneous fairness ratio for |user_id|.
    double fairness_avg(int user_id) const;
    // Returns true if slowdown/fairness samples have been recorded.
    bool has_fairness(int user_id) const;
    // slowdown_avg is an alias for fairness_avg to mirror FLIN nomenclature.
    double slowdown_avg(int user_id) const { return fairness_avg(user_id); }
    // users returns the number of tracked users.
    int users() const { return static_cast<int>(stats_.size()); }

    // fairness_index returns Jain's fairness over slowdown ratios when available,
    // otherwise over throughput (bytes).
    double fairness_index() const;
    // throughput_fairness_index computes Jain's fairness across per-user throughput.
    double throughput_fairness_index(double runtime_s) const;

    // Wear-leveling statistics: these are global device-level aggregates
    // captured from the wear-leveling FTL when available.
    void record_wear_snapshot(const std::vector<std::uint64_t>& erase_counts);
    double wear_variance() const { return wear_variance_; }
    std::uint64_t wear_min_erase() const { return wear_min_erase_; }
    std::uint64_t wear_max_erase() const { return wear_max_erase_; }
    bool has_wear_stats() const { return wear_stats_valid_; }

    // Writes per-user stats to CSV. Returns true on success.
    bool save_csv(const std::string& path) const;

    // Convenience helpers for global aggregates.
    uint64_t total_bytes_all() const;

private:
    struct UserStats {
        size_t completed = 0;
        double total_latency = 0.0;
        uint64_t bytes = 0;
        std::vector<double> latencies;   // Latency samples for tail percentiles.
        double fairness_sum = 0.0;       // Sum of instantaneous fairness ratios.
        double fairness_ewma = 1.0;      // EWMA of actual_rate / fair_share.
        size_t fairness_samples = 0;     // Number of fairness samples recorded.
    };

    std::vector<UserStats> stats_;

    // Global wear-leveling aggregates.
    double wear_variance_ = 0.0;
    std::uint64_t wear_min_erase_ = 0;
    std::uint64_t wear_max_erase_ = 0;
    bool wear_stats_valid_ = false;
};

} // namespace ssd
