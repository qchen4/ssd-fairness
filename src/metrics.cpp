// metrics.cpp: Implements per-user throughput, latency, and fairness tracking.
#include "metrics.hpp"

#include <algorithm>
#include <filesystem>
#include <fstream>
#include <numeric>

namespace ssd {

Metrics::Metrics(int num_users) {
    reset(num_users);
}

// reset prepares collectors for |num_users| tenants.
void Metrics::reset(int num_users) {
    stats_.assign(std::max(num_users, 0), {});
    for (auto& s : stats_) s.fairness_ewma = 1.0;

    wear_variance_ = 0.0;
    wear_min_erase_ = 0;
    wear_max_erase_ = 0;
    wear_stats_valid_ = false;
}

// on_finish accumulates latency and throughput for the provided request.
void Metrics::on_finish(const Request& req) {
    if (req.user_id < 0) return;
    if (req.user_id >= static_cast<int>(stats_.size()))
        stats_.resize(req.user_id + 1);

    auto& s = stats_[req.user_id];
    double latency = req.finish_ts - req.arrival_ts;
    if (latency < 0) latency = 0.0;

    s.completed += 1;
    s.total_latency += latency;
    s.bytes += req.size_bytes;
    s.latencies.push_back(latency);
}

void Metrics::record_fairness(int user_id, double instant_ratio, double ewma_ratio) {
    if (user_id < 0) return;
    if (user_id >= static_cast<int>(stats_.size()))
        stats_.resize(user_id + 1);
    auto& s = stats_[user_id];
    s.fairness_sum += instant_ratio;
    s.fairness_samples += 1;
    s.fairness_ewma = ewma_ratio;
}

double Metrics::avg_latency(int user_id) const {
    if (user_id < 0 || user_id >= static_cast<int>(stats_.size()) || stats_[user_id].completed == 0)
        return 0.0;
    return stats_[user_id].total_latency / static_cast<double>(stats_[user_id].completed);
}

double Metrics::percentile_latency(int user_id, double percentile) const {
    if (user_id < 0 || user_id >= static_cast<int>(stats_.size()))
        return 0.0;
    const auto& samples = stats_[user_id].latencies;
    if (samples.empty()) return 0.0;
    std::vector<double> sorted = samples;
    std::sort(sorted.begin(), sorted.end());
    double clamped = std::clamp(percentile, 0.0, 1.0);
    size_t idx = static_cast<size_t>(clamped * static_cast<double>(sorted.size() - 1));
    if (idx >= sorted.size()) idx = sorted.size() - 1;
    return sorted[idx];
}

uint64_t Metrics::total_bytes(int user_id) const {
    if (user_id < 0 || user_id >= static_cast<int>(stats_.size()))
        return 0;
    return stats_[user_id].bytes;
}

size_t Metrics::completed(int user_id) const {
    if (user_id < 0 || user_id >= static_cast<int>(stats_.size()))
        return 0;
    return stats_[user_id].completed;
}

double Metrics::fairness_ewma(int user_id) const {
    if (user_id < 0 || user_id >= static_cast<int>(stats_.size()))
        return 0.0;
    return stats_[user_id].fairness_samples > 0 ? stats_[user_id].fairness_ewma : 0.0;
}

double Metrics::fairness_avg(int user_id) const {
    if (user_id < 0 || user_id >= static_cast<int>(stats_.size()))
        return 0.0;
    const auto& s = stats_[user_id];
    if (s.fairness_samples == 0) return 0.0;
    return s.fairness_sum / static_cast<double>(s.fairness_samples);
}

bool Metrics::has_fairness(int user_id) const {
    if (user_id < 0 || user_id >= static_cast<int>(stats_.size()))
        return false;
    return stats_[user_id].fairness_samples > 0;
}

// fairness_index implements Jain's metric. If slowdown samples are available we
// use them, otherwise we fall back to throughput fairness based on bytes.
double Metrics::fairness_index() const {
    double sum = 0.0;
    double sum_sq = 0.0;
    size_t participants = 0;
    for (const auto& s : stats_) {
        if (s.fairness_samples == 0) continue;
        participants += 1;
        double x = s.fairness_ewma;
        sum += x;
        sum_sq += x * x;
    }
    if (participants > 0 && sum_sq > 0.0)
        return (sum * sum) / (participants * sum_sq);

    // Fall back to byte-level fairness when no slowdown data exists.
    sum = 0.0;
    sum_sq = 0.0;
    participants = 0;
    for (const auto& s : stats_) {
        if (s.bytes == 0) continue;
        participants += 1;
        double x = static_cast<double>(s.bytes);
        sum += x;
        sum_sq += x * x;
    }
    if (participants == 0 || sum_sq == 0.0) return 0.0;
    return (sum * sum) / (participants * sum_sq);
}

double Metrics::throughput_fairness_index(double runtime_s) const {
    if (runtime_s <= 0.0) runtime_s = 1.0;
    double sum = 0.0;
    double sum_sq = 0.0;
    size_t participants = 0;
    for (const auto& s : stats_) {
        if (s.bytes == 0) continue;
        double thr = static_cast<double>(s.bytes) / runtime_s;
        participants += 1;
        sum += thr;
        sum_sq += thr * thr;
    }
    if (participants == 0 || sum_sq == 0.0) return 0.0;
    return (sum * sum) / (participants * sum_sq);
}

void Metrics::record_wear_snapshot(const std::vector<std::uint64_t>& erase_counts) {
    if (erase_counts.empty()) {
        wear_variance_ = 0.0;
        wear_min_erase_ = 0;
        wear_max_erase_ = 0;
        wear_stats_valid_ = false;
        return;
    }

    const std::size_t n = erase_counts.size();
    std::uint64_t sum = std::accumulate(erase_counts.begin(), erase_counts.end(), std::uint64_t{0});
    double mean = static_cast<double>(sum) / static_cast<double>(n);

    double acc = 0.0;
    std::uint64_t min_v = erase_counts.front();
    std::uint64_t max_v = erase_counts.front();
    for (auto v : erase_counts) {
        double d = static_cast<double>(v) - mean;
        acc += d * d;
        if (v < min_v) min_v = v;
        if (v > max_v) max_v = v;
    }

    wear_variance_ = acc / static_cast<double>(n);
    wear_min_erase_ = min_v;
    wear_max_erase_ = max_v;
    wear_stats_valid_ = true;
}

uint64_t Metrics::total_bytes_all() const {
    uint64_t sum = 0;
    for (const auto& s : stats_) sum += s.bytes;
    return sum;
}

// save_csv persists a per-user summary so downstream tools can analyze results.
bool Metrics::save_csv(const std::string& path) const {
    std::filesystem::path file_path(path);
    if (file_path.has_parent_path() && !file_path.parent_path().empty()) {
        std::error_code ec;
        std::filesystem::create_directories(file_path.parent_path(), ec);
    }

    std::ofstream out(path);
    if (!out.is_open()) return false;

    out << "user_id,completed,avg_latency_s,p95_latency_s,p99_latency_s,total_bytes,"
           "slowdown_avg,slowdown_ewma,wear_variance,wear_min_erase,wear_max_erase\n";
    for (size_t i = 0; i < stats_.size(); ++i) {
        out << i << ","
            << stats_[i].completed << ","
            << avg_latency(static_cast<int>(i)) << ","
            << percentile_latency(static_cast<int>(i), 0.95) << ","
            << percentile_latency(static_cast<int>(i), 0.99) << ","
            << stats_[i].bytes << ","
            << fairness_avg(static_cast<int>(i)) << ","
            << fairness_ewma(static_cast<int>(i)) << ","
            << (wear_stats_valid_ ? wear_variance_ : 0.0) << ","
            << (wear_stats_valid_ ? wear_min_erase_ : 0) << ","
            << (wear_stats_valid_ ? wear_max_erase_ : 0) << "\n";
    }
    return true;
}

} // namespace ssd
