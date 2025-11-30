// ftl_wear.hpp: Simple wear-leveling helper for the SSD simulator.
#pragma once

#include "types.hpp"

#include <cstdint>
#include <optional>
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

    // Flash geometry.
    std::size_t pages_per_block = 64;      // Pages per physical block.

    // WL2: global min-cap policy parameters.
    bool enable_min_cap_wl = false;        // When true, use WL2 instead of WL0 logic.
    std::uint64_t hot_min_cap_delta = 8;   // Allowed offset from global min erase for hot writes.
    int hot_min_cap_pool_size = 32;        // How many candidates to sample for hot writes.
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

    // Debug-only helper to inspect how often GC runs in tests/experiments.
    std::size_t gc_invocations_debug() const { return gc_invocations_debug_; }

    // Global wear statistics helpers.
    double wear_variance() const;
    std::uint64_t wear_min_erase() const;
    std::uint64_t wear_max_erase() const;

private:
    struct PhysAddr {
        std::uint32_t block = 0;
        std::uint16_t page = 0;
    };

    struct PageEntry {
        bool valid = false;
        std::uint64_t lba = 0;
    };

    struct BlockState {
        std::uint64_t erase_count = 0;
        std::uint16_t pages_used = 0;   // allocated pages (valid + invalid)
        std::uint16_t pages_valid = 0;  // number of valid pages
        std::vector<PageEntry> pages;
    };

    WearLevelConfig cfg_;
    std::vector<std::uint64_t> erase_counts_;              // Per-block erase counters.
    std::unordered_map<std::uint64_t, double> write_freq_; // Moving avg writes per LBA.
    std::unordered_map<std::uint64_t, std::uint64_t> lba_to_block_;

    static constexpr double kFreqDecay = 0.9; // Exponential decay for write_freq_.

    // Existing per-write dynamic WL.
    std::uint64_t choose_block_for_lba(std::uint64_t lba_bytes, bool is_hot) const;
    std::uint64_t choose_block_original(std::uint64_t lba_bytes, bool is_hot) const;
    std::uint64_t choose_block_min_cap(std::uint64_t lba_bytes, bool is_hot) const;

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

    // Flash physical state and helpers.
    void init_blocks(std::size_t blocks);
    PhysAddr allocate_page_for_write(std::uint64_t lba_bytes, bool is_hot);
    PhysAddr allocate_page_for_gc(std::uint64_t lba_bytes);
    void invalidate_old_mapping(std::uint64_t lba_bytes);
    void maybe_gc();
    void run_gc_once();
    int choose_gc_victim_block() const;
    bool has_free_page_in_any_block() const;
    std::optional<std::uint16_t> find_free_page_in_block(std::uint32_t block) const;
    std::optional<PhysAddr> place_new_page_in_block(std::uint64_t lba_bytes, std::uint32_t block);
    std::optional<PhysAddr> place_in_any_block(std::uint64_t lba_bytes);
    void erase_block(std::uint32_t block);
    void move_lba_to_block(std::uint64_t lba_bytes, std::uint32_t new_block);

    std::vector<BlockState> blocks_;
    std::unordered_map<std::uint64_t, PhysAddr> lba_to_phys_;
    std::size_t pages_per_block_ = 0;

    // Debug-only: counts how many times GC has been invoked.
    std::size_t gc_invocations_debug_ = 0;
};

} // namespace ssd

