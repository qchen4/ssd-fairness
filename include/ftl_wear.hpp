// ftl_wear.hpp: Simple wear-leveling helper for the SSD simulator.
#pragma once

#include "types.hpp"

#include <cstdint>
#include <unordered_map>
#include <utility>
#include <vector>

namespace ssd {

// WearLevelConfig configures the lightweight FTL wear-leveling model.
struct WearLevelConfig {
    double hot_threshold = 4.0;         // Moving-average threshold for hot writes.
    int pool_size = 16;                 // Candidate blocks to examine per write.
    bool balance_reads = false;         // Rotate reads across channels when enabled.
    std::size_t total_blocks = 1024;    // Total number of physical blocks.

    // Min–Max-style, segment-based rebalancing parameters.
    int num_segments = 8;                  // Number of block segments.
    std::size_t rebalance_interval = 1000; // Hot writes between segment rebalances.
    double rebalance_fraction = 0.05;      // Fraction of LBAs in hottest segment to move.
};


// WearLevelFtl tracks per-block erase counts and a simple hot/cold
// classification based on per-LBA write frequency. It does not model
// pages or internal SSD garbage collection; instead, it approximates
// wear by incrementing per-block erase counts when writes complete.
class WearLevelFtl {
public:
    WearLevelFtl() = default;
    explicit WearLevelFtl(const WearLevelConfig& cfg);

    // Re-initialize the FTL for a device with |blocks| physical blocks.
    void reset(std::size_t blocks);

    // Updates moving-average write frequency for |lba_bytes| and chooses
    // a physical block to place the write. |is_hot_out| is set to true
    // when the LBA is classified as "hot".
    std::uint64_t map_write(std::uint64_t lba_bytes, bool* is_hot_out);

    // Returns the physical block currently mapped for |lba_bytes|, or a
    // default mapping if this is the first access.
    std::uint64_t map_read(std::uint64_t lba_bytes) const;

    // Called when a write to |lba_bytes| has completed and the block has
    // been erased/remapped. In this simple model we treat each completed
    // write as one erase event for the mapped block.
    void on_write_completed(std::uint64_t lba_bytes);

    const std::vector<std::uint64_t>& erase_counts() const { return erase_counts_; }

    // Global wear statistics helpers.
    double wear_variance() const;
    std::uint64_t wear_min_erase() const;
    std::uint64_t wear_max_erase() const;

private:
    WearLevelConfig cfg_;
    std::vector<std::uint64_t> erase_counts_;              // Per-block erase counters.
    std::unordered_map<std::uint64_t, double> write_freq_; // Moving avg writes per LBA.
    std::unordered_map<std::uint64_t, std::uint64_t> lba_to_block_;

    static constexpr double kFreqDecay = 0.9; // Exponential decay for write_freq_.

    // Existing per-write dynamic WL.
    std::uint64_t choose_block_for_lba(std::uint64_t lba_bytes, bool is_hot) const;

    // New: segment-based Min–Max-style rebalancing state.
    std::vector<int> block_segment_;                       // block -> segment index
    std::vector<std::vector<std::uint64_t>> segment_lbas_; // segment -> LBAs mapped into that segment
    std::uint64_t hot_write_counter_ = 0;                  // hot writes since last segment rebalance

    // New helpers.
    void init_segments();
    void register_lba_in_segment(std::uint64_t lba, std::uint64_t block);
    void unregister_lba_in_segment(std::uint64_t lba, std::uint64_t block);
    void maybe_rebalance_segments();
    void rebalance_once();
    std::uint64_t choose_block_in_segment(int segment, bool prefer_cold) const;
};

} // namespace ssd

