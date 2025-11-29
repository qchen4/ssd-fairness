#include "metrics.hpp"

#include <filesystem>
#include <fstream>
#include <numeric>
#include <vector>

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

double Metrics::avg_throughput_bytes_per_s(int user_id) const {
    if (user_id < 0 || user_id >= static_cast<int>(stats_.size()))
        return 0.0;
    const auto& s = stats_[user_id];
    if (s.total_latency <= 0.0)
        return 0.0;
    return s.bytes / s.total_latency;
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

double Metrics::fairness_index() const {
    const double throughput = throughput_fairness_index();
    const double latency = latency_fairness_index();
    if (throughput == 0.0 && latency == 0.0)
        return 0.0;
    if (throughput == 0.0)
        return latency;
    if (latency == 0.0)
        return throughput;
    return 0.5 * throughput + 0.5 * latency;
}

double Metrics::throughput_fairness_index() const {
    std::vector<double> values;
    values.reserve(stats_.size());
    for (const auto& s : stats_) {
        if (s.bytes == 0) continue;
        values.push_back(static_cast<double>(s.bytes));
    }
    return jain_index(values);
}

double Metrics::latency_fairness_index() const {
    std::vector<double> values;
    values.reserve(stats_.size());
    for (size_t i = 0; i < stats_.size(); ++i) {
        if (stats_[i].completed == 0) continue;
        double avg = avg_latency(static_cast<int>(i));
        if (avg <= 0.0) continue;
        values.push_back(1.0 / avg);
    }
    return jain_index(values);
}

double Metrics::jain_index(const std::vector<double>& values) const {
    if (values.empty()) return 0.0;
    double sum = 0.0;
    double sum_sq = 0.0;
    for (double v : values) {
        if (v <= 0.0) continue;
        sum += v;
        sum_sq += v * v;
    }
    if (sum_sq == 0.0) return 0.0;
    const double participants = static_cast<double>(values.size());
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

    out << "user_id,completed,avg_latency_s,avg_throughput_bytes_per_s,total_bytes\n";
    for (size_t i = 0; i < stats_.size(); ++i) {
        out << i << ","
            << stats_[i].completed << ","
            << avg_latency(static_cast<int>(i)) << ","
            << avg_throughput_bytes_per_s(static_cast<int>(i)) << ","
            << stats_[i].bytes << "\n";
    }
    return true;
}

} // namespace ssd
