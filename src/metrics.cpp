#include "metrics.hpp"

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
}

double Metrics::avg_latency(int user_id) const {
    if (user_id < 0 || user_id >= static_cast<int>(stats_.size()) || stats_[user_id].completed == 0)
        return 0.0;
    return stats_[user_id].total_latency / static_cast<double>(stats_[user_id].completed);
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

// fairness_index implements Jain's metric while excluding idle users so that
// workloads with unused queues do not skew the score toward zero.
double Metrics::fairness_index() const {
    double sum = 0.0;
    double sum_sq = 0.0;
    size_t participants = 0;
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

// save_csv persists a per-user summary so downstream tools can analyze results.
bool Metrics::save_csv(const std::string& path) const {
    std::filesystem::path file_path(path);
    if (file_path.has_parent_path() && !file_path.parent_path().empty()) {
        std::error_code ec;
        std::filesystem::create_directories(file_path.parent_path(), ec);
    }

    std::ofstream out(path);
    if (!out.is_open()) return false;

    out << "user_id,completed,avg_latency_s,total_bytes\n";
    for (size_t i = 0; i < stats_.size(); ++i) {
        out << i << ","
            << stats_[i].completed << ","
            << avg_latency(static_cast<int>(i)) << ","
            << stats_[i].bytes << "\n";
    }
    return true;
}

} // namespace ssd
