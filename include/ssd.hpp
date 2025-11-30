#pragma once

#include "types.hpp"

#include <vector>

namespace ssd {

// ChannelState tracks when an SSD channel becomes available again.
struct ChannelState {
    double free_at = 0.0;  // Absolute time when the channel frees up.
};

// SSD models a simple multi-channel flash device with per-channel service time.
class SSD {
public:
    explicit SSD(const SimConfig& cfg);

    // Dispatches |r| onto |channel_idx| at time |now| and returns completion time.
    double dispatch(int channel_idx, const Request& r, double now);

    // first_free_channel scans for the earliest channel that is idle at |now|.
    int first_free_channel(double now) const;

    // read_service_time_s returns the service time for a read of |bytes|.
    double read_service_time_s(uint32_t bytes) const;
    // write_service_time_s returns the service time for a write of |bytes|.
    double write_service_time_s(uint32_t bytes) const;

    // is_free reports whether channel |idx| is available at |now|.
    bool is_free(int idx, double now) const;
    // free_at returns the timestamp when channel |idx| becomes idle.
    // This is useful for debugging or visualization.
    double free_at(int idx) const;

    int num_channels() const { return static_cast<int>(channels_.size()); }

private:
    SimConfig cfg_;
    std::vector<ChannelState> channels_;
};

} // namespace ssd
