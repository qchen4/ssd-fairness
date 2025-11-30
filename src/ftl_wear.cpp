// ftl_wear.cpp: Implementation of the simple wear-leveling FTL model.
#include "ftl_wear.hpp"

#include <algorithm>
#include <numeric>

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
}

std::uint64_t WearLevelFtl::map_write(std::uint64_t lba_bytes, bool* is_hot_out) {
    // Update moving-average write frequency for this LBA.
    double& freq = write_freq_[lba_bytes];
    freq = freq * kFreqDecay + 1.0;  // EWMA over write events.

    bool is_hot = freq >= cfg_.hot_threshold;
    if (is_hot_out) *is_hot_out = is_hot;

    std::uint64_t block = choose_block_for_lba(lba_bytes, is_hot);
    lba_to_block_[lba_bytes] = block;
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

} // namespace ssd
