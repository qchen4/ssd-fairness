#pragma once

#include "types.hpp"

#include <vector>

namespace ssd {

struct ChannelState {
    double free_at = 0.0;
};

class SSD {
public:
    explicit SSD(const SimConfig& cfg);

    // Dispatches a request to the specified channel at time 'now'.
    // Returns the completion timestamp.
    double dispatch(int channel_idx, const Request& r, double now);

    int first_free_channel(double now) const;

    double read_service_time_s(uint32_t bytes) const;
    double write_service_time_s(uint32_t bytes) const;

    bool is_free(int idx, double now) const;
    double free_at(int idx) const;

    int num_channels() const { return static_cast<int>(channels_.size()); }

private:
    SimConfig cfg_;
    std::vector<ChannelState> channels_;
};

} // namespace ssd
