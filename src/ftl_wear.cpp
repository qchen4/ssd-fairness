// ftl_wear.cpp: Implementation of the simple wear-leveling FTL model.
#include "ftl_wear.hpp"

#include <algorithm>
#include <limits>
#include <numeric>
#include <random>

namespace ssd {

WearLevelFtl::WearLevelFtl(const WearLevelConfig& cfg) : cfg_(cfg) {
    reset(cfg_.total_blocks);
}

void WearLevelFtl::reset(std::size_t blocks) {
    if (blocks == 0) blocks = 1;
    cfg_.total_blocks = blocks;
    write_freq_.clear();
    lba_to_block_.clear();
    lba_to_phys_.clear();
    init_blocks(blocks);
    init_segments();
    hot_write_counter_ = 0;
}

void WearLevelFtl::init_blocks(std::size_t blocks) {
    pages_per_block_ = cfg_.pages_per_block > 0 ? cfg_.pages_per_block : 64;
    blocks_.clear();
    blocks_.resize(blocks);
    erase_counts_.assign(blocks, 0);
    for (std::size_t b = 0; b < blocks; ++b) {
        BlockState& bs = blocks_[b];
        bs.erase_count = 0;
        bs.pages_used = 0;
        bs.pages_valid = 0;
        bs.pages.assign(pages_per_block_, PageEntry{});
    }
}

void WearLevelFtl::init_segments() {
    const std::size_t blocks = erase_counts_.size();
    if (blocks == 0) {
        block_segment_.clear();
        segment_lbas_.clear();
        return;
    }
    if (cfg_.num_segments <= 0) cfg_.num_segments = 1;
    const int S = cfg_.num_segments;
    block_segment_.assign(blocks, 0);
    segment_lbas_.assign(S, {});

    // Simple contiguous partition of blocks into segments.
    for (std::size_t b = 0; b < blocks; ++b) {
        int seg = static_cast<int>((b * S) / blocks);
        if (seg >= S) seg = S - 1;
        block_segment_[b] = seg;
    }
}

std::uint64_t WearLevelFtl::map_write(std::uint64_t lba_bytes, bool* is_hot_out) {
    double& freq = write_freq_[lba_bytes];
    freq = freq * kFreqDecay + 1.0;

    bool is_hot = freq >= cfg_.hot_threshold;
    if (is_hot_out) *is_hot_out = is_hot;

    PhysAddr phys = allocate_page_for_write(lba_bytes, is_hot);

    if (is_hot) {
        ++hot_write_counter_;
        maybe_rebalance_segments();
    }

    return phys.block;
}

std::uint64_t WearLevelFtl::map_read(std::uint64_t lba_bytes) const {
    auto phys_it = lba_to_phys_.find(lba_bytes);
    if (phys_it != lba_to_phys_.end()) return phys_it->second.block;

    auto it = lba_to_block_.find(lba_bytes);
    if (it != lba_to_block_.end()) return it->second;

    if (blocks_.empty()) return 0;
    return static_cast<std::uint64_t>(lba_bytes % blocks_.size());
}

void WearLevelFtl::on_write_completed(std::uint64_t /*lba_bytes*/) {
    // Erase counts are updated during GC; nothing to do per write completion.
}

double WearLevelFtl::wear_variance() const {
    if (erase_counts_.empty()) return 0.0;
    const std::size_t n = erase_counts_.size();
    double mean = static_cast<double>(std::accumulate(
        erase_counts_.begin(), erase_counts_.end(), std::uint64_t{0})) /
                  static_cast<double>(n);
    double acc = 0.0;
    for (auto v : erase_counts_) {
        double d = static_cast<double>(v) - mean;
        acc += d * d;
    }
    return acc / static_cast<double>(n);
}

std::uint64_t WearLevelFtl::wear_min_erase() const {
    if (erase_counts_.empty()) return 0;
    return *std::min_element(erase_counts_.begin(), erase_counts_.end());
}

std::uint64_t WearLevelFtl::wear_max_erase() const {
    if (erase_counts_.empty()) return 0;
    return *std::max_element(erase_counts_.begin(), erase_counts_.end());
}

std::uint64_t WearLevelFtl::choose_block_for_lba(std::uint64_t lba_bytes, bool is_hot) const {
    if (erase_counts_.empty()) return 0;
    const std::size_t n = erase_counts_.size();

    // Compute a simple median erase count as the split between "cool" and "hot".
    std::vector<std::uint64_t> tmp = erase_counts_;
    std::nth_element(tmp.begin(), tmp.begin() + tmp.size() / 2, tmp.end());
    std::uint64_t median = tmp[tmp.size() / 2];

    // Start near the LBA-derived home block for locality.
    std::size_t start = static_cast<std::size_t>(lba_bytes % n);
    std::size_t examined = 0;
    std::size_t best_idx = n; // sentinel = not found yet.

    for (std::size_t offset = 0; offset < n && examined < static_cast<std::size_t>(cfg_.pool_size); ++offset) {
        std::size_t idx = (start + offset) % n;
        bool candidate = is_hot ? (erase_counts_[idx] <= median)
                                : (erase_counts_[idx] > median);
        if (!candidate) continue;
        ++examined;
        if (best_idx == n || erase_counts_[idx] < erase_counts_[best_idx]) {
            best_idx = idx;
        }
    }

    if (best_idx != n) return static_cast<std::uint64_t>(best_idx);

    // Fallback when no candidate on the preferred side of the median:
    // - for hot writes, choose the globally least-worn block;
    // - for cold writes, choose the most-worn block.
    if (is_hot) {
        return static_cast<std::uint64_t>(
            std::distance(erase_counts_.begin(),
                          std::min_element(erase_counts_.begin(), erase_counts_.end())));
    }
    return static_cast<std::uint64_t>(
        std::distance(erase_counts_.begin(),
                      std::max_element(erase_counts_.begin(), erase_counts_.end())));
}

void WearLevelFtl::register_lba_in_segment(std::uint64_t lba, std::uint64_t block) {
    if (block_segment_.empty()) return;
    if (block >= block_segment_.size()) return;
    int seg = block_segment_[block];
    if (seg < 0 || seg >= static_cast<int>(segment_lbas_.size())) return;
    segment_lbas_[seg].push_back(lba);
}

void WearLevelFtl::unregister_lba_in_segment(std::uint64_t lba, std::uint64_t block) {
    if (block_segment_.empty()) return;
    if (block >= block_segment_.size()) return;
    int seg = block_segment_[block];
    if (seg < 0 || seg >= static_cast<int>(segment_lbas_.size())) return;
    auto& vec = segment_lbas_[seg];
    auto it = std::find(vec.begin(), vec.end(), lba);
    if (it != vec.end()) vec.erase(it);
}

void WearLevelFtl::maybe_rebalance_segments() {
    if (cfg_.rebalance_interval <= 0) return;
    if (hot_write_counter_ < cfg_.rebalance_interval) return;
    hot_write_counter_ = 0;
    rebalance_once();
}

void WearLevelFtl::rebalance_once() {
    const int S = static_cast<int>(segment_lbas_.size());
    if (S <= 1 || erase_counts_.empty()) return;

    // 1. Compute average erase count per segment.
    std::vector<double> seg_avg(S, 0.0);
    std::vector<int> seg_count(S, 0);
    for (std::size_t b = 0; b < erase_counts_.size(); ++b) {
        int seg = (b < block_segment_.size()) ? block_segment_[b] : 0;
        if (seg < 0 || seg >= S) continue;
        seg_avg[seg] += static_cast<double>(erase_counts_[b]);
        seg_count[seg] += 1;
    }
    for (int s = 0; s < S; ++s) {
        if (seg_count[s] > 0) {
            seg_avg[s] /= static_cast<double>(seg_count[s]);
        }
    }

    // 2. Find hottest and coldest segments.
    int hot_seg = 0, cold_seg = 0;
    for (int s = 1; s < S; ++s) {
        if (seg_avg[s] > seg_avg[hot_seg]) hot_seg = s;
        if (seg_avg[s] < seg_avg[cold_seg]) cold_seg = s;
    }
    if (hot_seg == cold_seg) return;

    auto& hot_lbas = segment_lbas_[hot_seg];
    if (hot_lbas.empty()) return;

    // 3. Decide how many LBAs to move.
    std::size_t moves = static_cast<std::size_t>(
        cfg_.rebalance_fraction * static_cast<double>(hot_lbas.size()));
    if (moves == 0) moves = 1;
    if (moves > hot_lbas.size()) moves = hot_lbas.size();

    // 4. Shuffle for randomness (fixed seed for reproducible tests).
    std::mt19937 rng{12345};
    std::shuffle(hot_lbas.begin(), hot_lbas.end(), rng);

    // 5. Move a subset of LBAs from hot_seg to cold_seg.
    std::vector<std::uint64_t> to_move;
    to_move.reserve(moves);
    for (std::size_t i = 0; i < moves; ++i) {
        to_move.push_back(hot_lbas[i]);
    }

    for (std::uint64_t lba : to_move) {
        std::uint64_t new_block = choose_block_in_segment(cold_seg, /*prefer_cold=*/true);
        move_lba_to_block(lba, static_cast<std::uint32_t>(new_block));
    }

    // Remove the moved LBAs from the hot segment's list.
    if (moves > 0 && moves <= hot_lbas.size()) {
        hot_lbas.erase(hot_lbas.begin(), hot_lbas.begin() + static_cast<long>(moves));
    }
}

std::uint64_t WearLevelFtl::choose_block_in_segment(int segment, bool prefer_cold) const {
    if (erase_counts_.empty() || block_segment_.empty()) return 0;
    const int S = static_cast<int>(segment_lbas_.size());
    if (segment < 0 || segment >= S) return 0;

    std::uint64_t invalid = static_cast<std::uint64_t>(-1);
    std::uint64_t best_idx = invalid;

    for (std::size_t b = 0; b < erase_counts_.size(); ++b) {
        if (block_segment_[b] != segment) continue;
        if (best_idx == invalid) {
            best_idx = static_cast<std::uint64_t>(b);
            continue;
        }
        if (prefer_cold) {
            if (erase_counts_[b] < erase_counts_[best_idx]) best_idx = static_cast<std::uint64_t>(b);
        } else {
            if (erase_counts_[b] > erase_counts_[best_idx]) best_idx = static_cast<std::uint64_t>(b);
        }
    }

    if (best_idx != invalid) return best_idx;

    // Fallback to global min (cold) or max (hot), similar to choose_block_for_lba.
    if (prefer_cold) {
        return static_cast<std::uint64_t>(
            std::distance(erase_counts_.begin(),
                          std::min_element(erase_counts_.begin(), erase_counts_.end())));
    }
    return static_cast<std::uint64_t>(
        std::distance(erase_counts_.begin(),
                      std::max_element(erase_counts_.begin(), erase_counts_.end())));
}

WearLevelFtl::PhysAddr WearLevelFtl::allocate_page_for_write(std::uint64_t lba_bytes, bool is_hot) {
    invalidate_old_mapping(lba_bytes);

    const int max_attempts = 3;
    for (int attempt = 0; attempt < max_attempts; ++attempt) {
        maybe_gc();
        if (!blocks_.empty()) {
            std::uint32_t preferred =
                static_cast<std::uint32_t>(choose_block_for_lba(lba_bytes, is_hot) % blocks_.size());
            if (auto phys = place_new_page_in_block(lba_bytes, preferred)) return *phys;
        }
        if (auto phys = place_in_any_block(lba_bytes)) return *phys;
        run_gc_once();
    }

    if (!blocks_.empty()) {
        run_gc_once();
        if (auto phys = place_in_any_block(lba_bytes)) return *phys;
    }

    return PhysAddr{0, 0};
}

WearLevelFtl::PhysAddr WearLevelFtl::allocate_page_for_gc(std::uint64_t lba_bytes) {
    if (!blocks_.empty()) {
        std::uint32_t preferred =
            static_cast<std::uint32_t>(choose_block_for_lba(lba_bytes, false) % blocks_.size());
        if (auto phys = place_new_page_in_block(lba_bytes, preferred)) return *phys;
        if (auto phys = place_in_any_block(lba_bytes)) return *phys;
    }
    return PhysAddr{std::numeric_limits<std::uint32_t>::max(), 0};
}

void WearLevelFtl::invalidate_old_mapping(std::uint64_t lba_bytes) {
    auto phys_it = lba_to_phys_.find(lba_bytes);
    if (phys_it != lba_to_phys_.end()) {
        const PhysAddr old = phys_it->second;
        if (old.block < blocks_.size()) {
            BlockState& bs = blocks_[old.block];
            if (old.page < bs.pages.size()) {
                PageEntry& pe = bs.pages[old.page];
                if (pe.valid) {
                    pe.valid = false;
                    pe.lba = 0;
                    if (bs.pages_valid > 0) --bs.pages_valid;
                }
            }
        }
        lba_to_phys_.erase(phys_it);
    }

    auto block_it = lba_to_block_.find(lba_bytes);
    if (block_it != lba_to_block_.end()) {
        unregister_lba_in_segment(lba_bytes, block_it->second);
        lba_to_block_.erase(block_it);
    }
}

bool WearLevelFtl::has_free_page_in_any_block() const {
    for (const auto& bs : blocks_) {
        if (bs.pages_used < pages_per_block_) return true;
    }
    return false;
}

std::optional<std::uint16_t> WearLevelFtl::find_free_page_in_block(std::uint32_t block) const {
    if (block >= blocks_.size()) return std::nullopt;
    const BlockState& bs = blocks_[block];
    if (bs.pages_used >= pages_per_block_) return std::nullopt;
    return static_cast<std::uint16_t>(bs.pages_used);
}

std::optional<WearLevelFtl::PhysAddr> WearLevelFtl::place_new_page_in_block(std::uint64_t lba_bytes,
                                                                            std::uint32_t block) {
    if (block >= blocks_.size()) return std::nullopt;
    auto maybe_page = find_free_page_in_block(block);
    if (!maybe_page.has_value()) return std::nullopt;

    BlockState& bs = blocks_[block];
    std::uint16_t page_idx = *maybe_page;
    PageEntry& pe = bs.pages[page_idx];
    pe.valid = true;
    pe.lba = lba_bytes;
    bs.pages_valid++;
    bs.pages_used = static_cast<std::uint16_t>(page_idx + 1);

    PhysAddr phys{block, page_idx};
    lba_to_phys_[lba_bytes] = phys;
    lba_to_block_[lba_bytes] = block;
    register_lba_in_segment(lba_bytes, block);
    return phys;
}

std::optional<WearLevelFtl::PhysAddr> WearLevelFtl::place_in_any_block(std::uint64_t lba_bytes) {
    for (std::uint32_t block = 0; block < blocks_.size(); ++block) {
        if (auto phys = place_new_page_in_block(lba_bytes, block)) return phys;
    }
    return std::nullopt;
}

void WearLevelFtl::maybe_gc() {
    if (blocks_.empty()) return;
    if (!has_free_page_in_any_block()) {
        run_gc_once();
        return;
    }
    std::size_t free_pages = 0;
    for (const auto& bs : blocks_) {
        if (bs.pages_used < pages_per_block_) free_pages += pages_per_block_ - bs.pages_used;
    }
    if (free_pages <= pages_per_block_) run_gc_once();
}

int WearLevelFtl::choose_gc_victim_block() const {
    if (blocks_.empty()) return -1;
    int victim = -1;
    std::uint16_t best_valid = std::numeric_limits<std::uint16_t>::max();
    for (std::size_t b = 0; b < blocks_.size(); ++b) {
        const BlockState& bs = blocks_[b];
        if (bs.pages_used == 0) {
            victim = static_cast<int>(b);
            best_valid = 0;
            break;
        }
        if (bs.pages_valid < best_valid) {
            best_valid = bs.pages_valid;
            victim = static_cast<int>(b);
        }
    }
    return victim;
}

void WearLevelFtl::erase_block(std::uint32_t block) {
    if (block >= blocks_.size()) return;
    BlockState& bs = blocks_[block];
    bs.erase_count++;
    erase_counts_[block] = bs.erase_count;
    bs.pages_used = 0;
    bs.pages_valid = 0;
    for (auto& page : bs.pages) {
        page.valid = false;
        page.lba = 0;
    }
}

void WearLevelFtl::run_gc_once() {
    if (blocks_.empty()) return;
    int victim = choose_gc_victim_block();
    if (victim < 0) return;

    BlockState& vb = blocks_[victim];
    if (vb.pages_used == 0) {
        erase_block(static_cast<std::uint32_t>(victim));
        return;
    }

    std::vector<std::uint64_t> fallback_lbas;
    fallback_lbas.reserve(vb.pages_valid);

    for (std::uint16_t page = 0; page < vb.pages_used; ++page) {
        PageEntry& pe = vb.pages[page];
        if (!pe.valid) continue;
        const std::uint64_t lba = pe.lba;
        invalidate_old_mapping(lba);
        PhysAddr new_phys = allocate_page_for_gc(lba);
        if (new_phys.block == std::numeric_limits<std::uint32_t>::max()) {
            fallback_lbas.push_back(lba);
        }
    }

    erase_block(static_cast<std::uint32_t>(victim));

    for (std::uint64_t lba : fallback_lbas) {
        auto phys = place_new_page_in_block(lba, static_cast<std::uint32_t>(victim));
        if (!phys.has_value()) {
            auto alt = place_in_any_block(lba);
            if (!alt.has_value()) {
                // As a last resort, keep the mapping unmapped.
            }
        }
    }
}

void WearLevelFtl::move_lba_to_block(std::uint64_t lba_bytes, std::uint32_t new_block) {
    if (blocks_.empty()) return;

    std::uint32_t old_block = 0;
    auto phys_it = lba_to_phys_.find(lba_bytes);
    if (phys_it != lba_to_phys_.end()) old_block = phys_it->second.block;

    invalidate_old_mapping(lba_bytes);

    if (new_block < blocks_.size()) {
        if (auto phys = place_new_page_in_block(lba_bytes, new_block)) return;
    }

    if (auto phys = place_in_any_block(lba_bytes)) return;

    run_gc_once();
    if (auto phys = place_in_any_block(lba_bytes)) return;
    if (old_block < blocks_.size()) {
        (void)place_new_page_in_block(lba_bytes, old_block);
    }
}

} // namespace ssd
