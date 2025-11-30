#include "ssd.hpp"

#include <algorithm>
#include <stdexcept>

namespace {

constexpr double kBytesPerMB = 1024.0 * 1024.0;

double bytes_per_second(double bw_MBps, int channels) {
    if (channels <= 0) return 0.0;
    return (bw_MBps / static_cast<double>(channels)) * kBytesPerMB;
}

} // namespace

namespace ssd {

SSD::SSD(const SimConfig& cfg) : cfg_(cfg) {
    channels_.assign(std::max(cfg_.num_channels, 0), {});
}

// Dispatch applies the scheduling decision onto the physical channel model.
double SSD::dispatch(int channel_idx, const Request& r, double now) {
    if (channel_idx < 0 || channel_idx >= static_cast<int>(channels_.size()))
        throw std::out_of_range("Invalid channel index");

    double service = (r.op == OpType::READ)
        ? read_service_time_s(r.size_bytes)
        : write_service_time_s(r.size_bytes);

    ChannelState& ch = channels_[channel_idx];
    double start = std::max(now, ch.free_at);
    ch.free_at = start + service;
    return ch.free_at;
}

// first_free_channel scans channels sequentially; the workload uses small N, so
// this linear scan is sufficient and keeps the model simple.
int SSD::first_free_channel(double now) const {
    for (int i = 0; i < static_cast<int>(channels_.size()); ++i) {
        if (channels_[i].free_at <= now)
            return i;
    }
    return -1;
}

double SSD::read_service_time_s(uint32_t bytes) const {
    double rate = bytes_per_second(cfg_.read_bw_MBps, cfg_.num_channels);
    if (rate <= 0.0) return 0.0;
    return static_cast<double>(bytes) / rate;
}

double SSD::write_service_time_s(uint32_t bytes) const {
    double rate = bytes_per_second(cfg_.write_bw_MBps, cfg_.num_channels);
    if (rate <= 0.0) return 0.0;
    return static_cast<double>(bytes) / rate;
}

bool SSD::is_free(int idx, double now) const {
    if (idx < 0 || idx >= static_cast<int>(channels_.size())) return false;
    return channels_[idx].free_at <= now;
}

double SSD::free_at(int idx) const {
    if (idx < 0 || idx >= static_cast<int>(channels_.size())) return 0.0;
    return channels_[idx].free_at;
}

} // namespace ssd
