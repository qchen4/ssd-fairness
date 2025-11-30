// ssd.cpp: Simple SSD channel timing model for the simulator.
#include "ssd.hpp"

#include <algorithm>
#include <limits>
#include <numeric>
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
    wear_tracking_enabled_ = flash_blocks_ > 0 && pages_per_block_ > 0;
    if (wear_tracking_enabled_) {
        wear_count_.assign(flash_blocks_, 0);
        block_next_page_.assign(flash_blocks_, 0);
        block_valid_pages_.assign(flash_blocks_, 0);
        block_lbas_.assign(flash_blocks_, {});
    }
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

    if (r.op == OpType::WRITE) {
        handle_write(r);
    }

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

void SSD::handle_write(const Request& r) {
    if (!wear_tracking_enabled_) return;

    std::uint64_t lba_value = r.lba;
    std::uint64_t logical_page = 0;
    if (lba_value >= 4096) {
        logical_page = lba_value / 4096;
    } else {
        logical_page = lba_value;
    }
    if (logical_page == 0 && lba_value == 0) {
        logical_page = total_writes_;
    }

    invalidate_old_mapping(logical_page);

    int block = select_block_for_write();
    if (block < 0) return;

    place_lba_in_block(logical_page, block);
    ++total_writes_;
    maybe_balance_wear();
}

void SSD::invalidate_old_mapping(std::uint64_t lba) {
    auto it = lba_map_.find(lba);
    if (it == lba_map_.end()) return;
    int block = static_cast<int>(it->second.block);
    if (block >= 0 && block < static_cast<int>(block_lbas_.size())) {
        block_lbas_[block].erase(lba);
        block_valid_pages_[block] = block_lbas_[block].size();
    }
    lba_map_.erase(it);
}

int SSD::select_block_for_write() {
    int best_block = -1;
    std::uint64_t best_wear = std::numeric_limits<std::uint64_t>::max();

    for (int b = 0; b < flash_blocks_; ++b) {
        if (block_next_page_[b] >= static_cast<std::size_t>(pages_per_block_)) continue;
        if (wear_count_[b] < best_wear) {
            best_wear = wear_count_[b];
            best_block = b;
        } else if (wear_count_[b] == best_wear && best_block >= 0 &&
                   block_valid_pages_[b] < block_valid_pages_[best_block]) {
            best_block = b;
        }
    }

    if (best_block != -1) return best_block;

    // No block has free pages; pick a victim with the most invalid space.
    int victim = 0;
    int best_invalid = -1;
    for (int b = 0; b < flash_blocks_; ++b) {
        int invalid_pages = pages_per_block_ - static_cast<int>(block_valid_pages_[b]);
        if (invalid_pages > best_invalid) {
            best_invalid = invalid_pages;
            victim = b;
        }
    }
    erase_block(victim);
    return victim;
}

void SSD::place_lba_in_block(std::uint64_t lba, int block) {
    if (block < 0 || block >= flash_blocks_) return;
    if (block_next_page_[block] >= static_cast<std::size_t>(pages_per_block_)) {
        erase_block(block);
    }
    std::size_t page = block_next_page_[block]++;
    block_lbas_[block].insert(lba);
    block_valid_pages_[block] = block_lbas_[block].size();
    lba_map_[lba] = PhysLocation{
        static_cast<std::uint32_t>(block),
        static_cast<std::uint32_t>(page)
    };
}

void SSD::erase_block(int block) {
    if (block < 0 || block >= flash_blocks_) return;
    auto& residents = block_lbas_[block];
    for (std::uint64_t lba : residents) {
        lba_map_.erase(lba);
    }
    residents.clear();
    block_valid_pages_[block] = 0;
    block_next_page_[block] = 0;
    if (static_cast<std::size_t>(block) < wear_count_.size()) {
        ++wear_count_[block];
    }
}

void SSD::maybe_balance_wear() {
    if (!wear_tracking_enabled_ || wear_count_.empty()) return;
    if (wear_check_interval_ == 0) return;
    if (total_writes_ == 0 || (total_writes_ % wear_check_interval_) != 0) return;

    auto [min_it, max_it] = std::minmax_element(wear_count_.begin(), wear_count_.end());
    if (min_it == wear_count_.end() || max_it == wear_count_.end()) return;
    if (*max_it > *min_it + wear_balance_threshold_) {
        std::size_t min_idx = static_cast<std::size_t>(std::distance(wear_count_.begin(), min_it));
        if (min_idx < wear_count_.size()) {
            ++wear_count_[min_idx];
        }
    }
}

} // namespace ssd
