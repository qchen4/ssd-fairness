#pragma once

#include "types.hpp"

#include <cstdint>
#include <unordered_map>
#include <unordered_set>
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

    const std::vector<std::uint64_t>& wear_counts() const { return wear_count_; }

private:
    struct PhysLocation {
        std::uint32_t block = 0;
        std::uint32_t page = 0;
    };

    void handle_write(const Request& r);
    void invalidate_old_mapping(std::uint64_t lba);
    int select_block_for_write();
    void place_lba_in_block(std::uint64_t lba, int block);
    void erase_block(int block);
    void maybe_balance_wear();

    SimConfig cfg_;
    std::vector<ChannelState> channels_;

    const int flash_blocks_ = 256;
    const int pages_per_block_ = 64;
    bool wear_tracking_enabled_ = true;
    std::vector<std::uint64_t> wear_count_;
    std::vector<std::size_t> block_next_page_;
    std::vector<std::size_t> block_valid_pages_;
    std::vector<std::unordered_set<std::uint64_t>> block_lbas_;
    std::unordered_map<std::uint64_t, PhysLocation> lba_map_;
    std::uint64_t total_writes_ = 0;
    const std::size_t wear_check_interval_ = 1000;
    const std::uint64_t wear_balance_threshold_ = 5;
};

} // namespace ssd
