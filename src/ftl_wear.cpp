// ftl_wear.cpp: Implementation of the simple wear-leveling FTL model.
#include "ftl_wear.hpp"

#include <algorithm>
#include <numeric>
#include <random>

namespace ssd {

WearLevelFtl::WearLevelFtl(const WearLevelConfig& cfg) : cfg_(cfg) {
    reset(cfg_.total_blocks);
}

void WearLevelFtl::reset(std::size_t blocks) {
    if (blocks == 0) blocks = 1;
    cfg_.total_blocks = blocks;
    erase_counts_.assign(blocks, 0);
    write_freq_.clear();
    lba_to_block_.clear();
    init_segments();
    hot_write_counter_ = 0;
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

    std::uint64_t block = choose_block_for_lba(lba_bytes, is_hot);

    // Update segment membership for this LBA.
    auto it = lba_to_block_.find(lba_bytes);
    if (it != lba_to_block_.end()) {
        unregister_lba_in_segment(lba_bytes, it->second);
        it->second = block;
    } else {
        lba_to_block_[lba_bytes] = block;
    }
    register_lba_in_segment(lba_bytes, block);

    // Count hot writes and periodically rebalance segments.
    if (is_hot) {
        ++hot_write_counter_;
        maybe_rebalance_segments();
    }

    return block;
}

std::uint64_t WearLevelFtl::map_read(std::uint64_t lba_bytes) const {
    auto it = lba_to_block_.find(lba_bytes);
    if (it != lba_to_block_.end()) return it->second;

    if (erase_counts_.empty()) return 0;
    return static_cast<std::uint64_t>(lba_bytes % erase_counts_.size());
}

void WearLevelFtl::on_write_completed(std::uint64_t lba_bytes) {
    if (erase_counts_.empty()) return;
    auto it = lba_to_block_.find(lba_bytes);
    if (it == lba_to_block_.end()) {
        // If we do not have an explicit mapping yet, fall back to a simple hash.
        std::uint64_t idx = static_cast<std::uint64_t>(lba_bytes % erase_counts_.size());
        erase_counts_[idx] += 1;
        return;
    }
    std::uint64_t idx = it->second;
    if (idx >= erase_counts_.size()) return;
    erase_counts_[idx] += 1;
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
    for (std::size_t i = 0; i < moves; ++i) {
        std::uint64_t lba = hot_lbas[i];
        std::uint64_t new_block = choose_block_in_segment(cold_seg, /*prefer_cold=*/true);
        auto it = lba_to_block_.find(lba);
        if (it != lba_to_block_.end()) {
            unregister_lba_in_segment(lba, it->second);
            it->second = new_block;
        } else {
            lba_to_block_[lba] = new_block;
        }
        register_lba_in_segment(lba, new_block);
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

} // namespace ssd
