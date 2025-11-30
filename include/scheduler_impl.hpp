// Scheduler implementations for SSD fairness experiments.
#pragma once

#include "metrics.hpp"
#include "scheduler.hpp"
#include "ftl_wear.hpp"

#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstdlib>
#include <deque>
#include <iostream>
#include <limits>
#include <optional>
#include <utility>
#include <vector>

namespace ssd {

namespace detail {
// Lightweight debug helpers gated by the SCHED_DEBUG env var so the hot path
// stays fast when tracing is disabled.
inline bool sched_debug_enabled() {
    static bool enabled = std::getenv("SCHED_DEBUG") != nullptr;
    return enabled;
}

template <typename... Args>
void sched_debug(Args&&... args) {
    if (!sched_debug_enabled()) return;
    (std::cerr << ... << args) << '\n';
}
} // namespace detail

// FifoScheduler serves requests strictly in arrival order.
// Pros: high throughput, simple. Cons: no per-flow isolation/fairness.
class FifoScheduler : public Scheduler {
    std::deque<Request> queue_; // Single global queue in arrival order.
    int users_ = 0;             // Cached number of tenants for bounds checks.

public:
    void set_users(int n) override {
        users_ = std::max(n, 0);
        queue_.clear();
    }

    void enqueue(const Request& r) override {
        if (r.user_id < 0 || r.user_id >= users_) return;
        queue_.push_back(r);
        detail::sched_debug("[fifo enqueue] uid=", r.user_id, " sz=", r.size_bytes);
    }

    std::optional<int> pick_user(double) override {
        if (queue_.empty()) return std::nullopt;
        return queue_.front().user_id; // Always dispatch the oldest request.
    }

    std::optional<Request> pop(int uid) override {
        if (queue_.empty()) return std::nullopt;
        if (queue_.front().user_id != uid) return std::nullopt;
        Request r = queue_.front();
        queue_.pop_front();
        detail::sched_debug("[fifo pop] uid=", uid, " sz=", r.size_bytes, " remaining=", queue_.size());
        return r;
    }

    bool empty() const override { return queue_.empty(); }
};

// RoundRobinScheduler cycles through users in order, skipping empty queues.
// Provides per-flow isolation at the granularity of one request per turn.
class RoundRobinScheduler : public Scheduler {
    std::vector<std::deque<Request>> queues_; // Per-user FIFOs.
    int next_ = 0;                            // Next user slot to probe.

public:
    void set_users(int n) override {
        queues_.assign(std::max(n, 0), {});
        next_ = 0;
    }

    void enqueue(const Request& r) override {
        if (r.user_id < 0 || r.user_id >= static_cast<int>(queues_.size()))
            return;
        queues_[r.user_id].push_back(r);
        detail::sched_debug("[rr enqueue] uid=", r.user_id, " sz=", r.size_bytes);
    }

    // pick_user returns the next user id that has pending work.
    std::optional<int> pick_user(double) override {
        if (queues_.empty()) return std::nullopt;

        for (int i = 0; i < static_cast<int>(queues_.size()); ++i) {
            int candidate = (next_ + i) % queues_.size();
            if (!queues_[candidate].empty()) {
                next_ = (candidate + 1) % queues_.size();
                detail::sched_debug("[rr pick] uid=", candidate, " next=", next_);
                return candidate;
            }
        }
        return std::nullopt;
    }

    std::optional<Request> pop(int uid) override {
        if (uid < 0 || uid >= static_cast<int>(queues_.size()) || queues_[uid].empty())
            return std::nullopt;
        Request r = queues_[uid].front();
        queues_[uid].pop_front();
        detail::sched_debug("[rr pop] uid=", uid, " sz=", r.size_bytes, " remaining=", queues_[uid].size());
        return r;
    }

    bool empty() const override {
        for (const auto& q : queues_)
            if (!q.empty()) return false;
        return true;
    }
};

// DeficitRoundRobinScheduler enforces byte-level fairness using deficit counters.
// Larger requests consume more credit; weights scale the quantum per user.
class DeficitRoundRobinScheduler : public Scheduler {
    std::vector<std::deque<Request>> queues_; // Per-user FIFOs.
    std::vector<int64_t> deficit_;            // Byte credits carried across rounds.
    std::vector<double> weights_;             // Optional per-user weights.
    double quantum_ = 4096.0;                 // Base quantum in bytes.
    int next_ = 0;                            // Next user slot to probe.

public:
    void set_users(int n) override {
        queues_.assign(std::max(n, 0), {});
        deficit_.assign(queues_.size(), 0);
        weights_.assign(queues_.size(), 1.0);
        next_ = 0;
    }

    void set_quantum(double q) override {
        if (q > 0.0) quantum_ = q;
    }

    void set_weights(const std::vector<double>& w) override {
        if (queues_.empty()) return;
        weights_.assign(queues_.size(), 1.0);
        for (size_t i = 0; i < weights_.size() && i < w.size(); ++i)
            weights_[i] = std::max(w[i], 0.0);
    }

    void enqueue(const Request& r) override {
        if (r.user_id < 0 || r.user_id >= static_cast<int>(queues_.size()))
            return;
        queues_[r.user_id].push_back(r);
        detail::sched_debug("[drr enqueue] uid=", r.user_id, " sz=", r.size_bytes);
    }
    
    // pick_user adds quantum credit and selects the first user whose request fits.
    std::optional<int> pick_user(double) override {
        if (queues_.empty()) return std::nullopt;

        for (int i = 0; i < static_cast<int>(queues_.size()); ++i) {
            int uid = (next_ + i) % queues_.size();
            if (queues_[uid].empty()) continue;

            int64_t quantum = static_cast<int64_t>(quantum_ * weights_[uid]);
            if (quantum <= 0) quantum = static_cast<int64_t>(quantum_);
            deficit_[uid] += quantum;

            const Request& r = queues_[uid].front();
            if (deficit_[uid] >= static_cast<int64_t>(r.size_bytes)) {
                next_ = (uid + 1) % queues_.size();
                detail::sched_debug("[drr pick] uid=", uid, " deficit=", deficit_[uid],
                                    " need=", r.size_bytes, " next=", next_);
                return uid;
            }
        }
        return std::nullopt;
    }

    std::optional<Request> pop(int uid) override {
        if (uid < 0 || uid >= static_cast<int>(queues_.size()) || queues_[uid].empty())
            return std::nullopt;

        Request r = queues_[uid].front();
        queues_[uid].pop_front();
        deficit_[uid] = std::max<int64_t>(0, deficit_[uid] - static_cast<int64_t>(r.size_bytes));
        assert(deficit_[uid] >= 0);
        detail::sched_debug("[drr pop] uid=", uid, " sz=", r.size_bytes,
                            " new_deficit=", deficit_[uid], " remaining=", queues_[uid].size());
        return r;
    }

    bool empty() const override {
        for (const auto& q : queues_) if (!q.empty()) return false;
        return true;
    }
};

// WeightedFairScheduler approximates WFQ by tagging requests with finish times.
// Always serves the smallest virtual finish tag to approximate GPS service.
class WeightedFairScheduler : public Scheduler {
    struct TaggedRequest {
        Request req;
        double finish_tag = 0.0; // Virtual finish time used for selection.
    };

    std::vector<std::deque<TaggedRequest>> queues_; // Per-user tagged queues.
    std::vector<double> weights_;                   // WFQ weights per flow.
    std::vector<double> last_finish_;               // Last finish tag per flow.
    double virtual_time_ = 0.0;                     // System virtual time.
    int active_flows_ = 0;                          // Number of non-empty queues.

    void validate_active() const {
        if (!detail::sched_debug_enabled()) return;
        int observed = 0;
        for (const auto& q : queues_)
            if (!q.empty()) ++observed;
        assert(observed == active_flows_);
    }

public:
    void set_users(int n) override {
        queues_.assign(std::max(n, 0), {});
        weights_.assign(queues_.size(), 1.0);
        last_finish_.assign(queues_.size(), 0.0);
        active_flows_ = 0;
        virtual_time_ = 0.0;
    }

    void set_weights(const std::vector<double>& w) override {
        if (queues_.empty()) return;
        for (size_t i = 0; i < queues_.size(); ++i) {
            if (i < w.size())
                weights_[i] = std::max(w[i], 1e-9);
            else
                weights_[i] = 1.0;
        }
    }

    void enqueue(const Request& r) override {
        if (r.user_id < 0 || r.user_id >= static_cast<int>(queues_.size()))
            return;

        double weight = weights_[r.user_id];
        // Virtual start is the later of the user's last finish and system VT.
        double start_tag = std::max(last_finish_[r.user_id], virtual_time_);
        // Finish tag grows with size and inversely with weight (higher weight -> smaller tag).
        double finish_tag = start_tag + static_cast<double>(r.size_bytes) / weight;
        last_finish_[r.user_id] = finish_tag;

        bool was_empty = queues_[r.user_id].empty();
        queues_[r.user_id].push_back(TaggedRequest{r, finish_tag});
        if (was_empty) ++active_flows_;
        detail::sched_debug("[wfq enqueue] uid=", r.user_id, " sz=", r.size_bytes,
                            " finish_tag=", finish_tag);
        validate_active();
    }

    std::optional<int> pick_user(double now) override {
        if (queues_.empty() || active_flows_ == 0) return std::nullopt;
        virtual_time_ = std::max(virtual_time_, now);

        int best_uid = -1;
        double best_finish = std::numeric_limits<double>::infinity();
        for (int uid = 0; uid < static_cast<int>(queues_.size()); ++uid) {
            if (queues_[uid].empty()) continue;
            double finish = queues_[uid].front().finish_tag;
            if (finish < best_finish) {
                best_finish = finish;
                best_uid = uid;
            }
        }
        if (best_uid < 0) return std::nullopt;
        detail::sched_debug("[wfq pick] uid=", best_uid, " finish_tag=",
                            queues_[best_uid].front().finish_tag, " vt=", virtual_time_);
        return best_uid;
    }

    std::optional<Request> pop(int uid) override {
        if (uid < 0 || uid >= static_cast<int>(queues_.size()) || queues_[uid].empty())
            return std::nullopt;
        TaggedRequest tagged = queues_[uid].front();
        queues_[uid].pop_front();
        if (queues_[uid].empty()) --active_flows_;
        // Advance virtual time to reflect service completion of the chosen packet.
        virtual_time_ = std::max(virtual_time_, tagged.finish_tag);
        detail::sched_debug("[wfq pop] uid=", uid, " sz=", tagged.req.size_bytes,
                            " finish_tag=", tagged.finish_tag, " remaining=", queues_[uid].size());
        validate_active();
        return tagged.req;
    }

    bool empty() const override {
        for (const auto& q : queues_)
            if (!q.empty()) return false;
        return true;
    }
};

// FlinScheduler implements a slowdown-aware policy inspired by FLIN (ISCA'18).
// It tracks recent service per flow, estimates actual vs. fair share, and
// prioritizes the most under-served flow while giving a slight preference to
// read-heavy tenants.
// Key idea: equalize slowdown = (actual service / fair share) across flows,
// letting GC/interference be observed implicitly via actual completion bytes.
struct FlinConfig {
    double window_sec = 0.1;          // EWMA decay window for service tracking.
    double fairness_alpha = 0.1;      // EWMA smoothing for slowdown.
    double read_alpha = 0.1;          // EWMA smoothing for read/write mix.
    double read_bias_strength = 0.25; // Bias toward read-heavy flows (0..1).
    double starvation_window = 0.2;   // Idle interval before starvation boost.
    int parallelism_trigger = 2;      // Outstanding threshold for size-aware insert.
};

class FlinScheduler : public Scheduler {
    struct FlowStats {
        std::deque<Request> queue;
        double served_bytes = 0.0;   // EWMA of bytes served in the recent window.
        double last_update = 0.0;    // Timestamp of the last decay update.
        double fairness_ewma = 1.0;  // EWMA of actual_rate / fair_share.
        double read_fraction = 0.5;  // EWMA of read intensity (1.0 = all reads).
        double last_finish = 0.0;    // Last time a request from this flow finished.
        uint64_t total_served = 0;   // Aggregate bytes served (for introspection).
        int outstanding = 0;         // Requests in flight for this flow.
        uint64_t outstanding_bytes = 0;
    };

    std::vector<FlowStats> flows_;
    FlinConfig cfg_;

    static constexpr double kEpsilon = 1e-9; // Guard against divide-by-zero.

    void decay_flow(FlowStats& f, double now) const {
        double dt = now - f.last_update;
        if (dt <= 0.0) return;
        // Exponential decay approximates a sliding time window of recent service.
        double factor = std::exp(-dt / cfg_.window_sec);
        f.served_bytes *= factor;
        f.last_update = now;
    }

    double fair_share(double total_served, int active) const {
        if (active <= 0 || total_served <= 0.0) return 0.0;
        return total_served / static_cast<double>(active);
    }

    std::pair<double, int> update_totals(double now) {
        double total = 0.0;
        int active = 0;
        for (auto& f : flows_) {
            decay_flow(f, now);
            // Treat flows that have either backlog or recent service as active.
            if (!f.queue.empty() || f.served_bytes > 1.0) {
                total += f.served_bytes;
                ++active;
            }
        }
        return {total, active};
    }

    // Stage 1: intensity- and parallelism-aware queue insertion.
    void insert_request(FlowStats& f, const Request& r) {
        if (f.outstanding >= cfg_.parallelism_trigger && !f.queue.empty()) {
            // When the flow already drives parallelism, keep smaller requests
            // near the head to reduce tail latency.
            auto it = std::find_if(f.queue.begin(), f.queue.end(),
                                   [&](const Request& existing) {
                                       return r.size_bytes < existing.size_bytes;
                                   });
            f.queue.insert(it, r);
        } else {
            f.queue.push_back(r);
        }
    }

    double read_starvation_bias(const FlowStats& f, double now) const {
        double read_bias = 1.0 - cfg_.read_bias_strength * f.read_fraction;
        read_bias = std::clamp(read_bias, 0.5, 1.0);

        double starvation = 1.0;
        if (now - f.last_finish > cfg_.starvation_window) starvation = 0.5;

        return read_bias * starvation;
    }

public:
    FlinScheduler() = default;
    explicit FlinScheduler(const FlinConfig& cfg) : cfg_(cfg) {}

    void set_config(const FlinConfig& cfg) {
        cfg_ = cfg;
        if (cfg_.window_sec < 1e-6) cfg_.window_sec = 1e-6;
        cfg_.fairness_alpha = std::clamp(cfg_.fairness_alpha, 0.0, 1.0);
        cfg_.read_alpha = std::clamp(cfg_.read_alpha, 0.0, 1.0);
        cfg_.read_bias_strength = std::clamp(cfg_.read_bias_strength, 0.0, 1.0);
        if (cfg_.starvation_window < 0.0) cfg_.starvation_window = 0.0;
        if (cfg_.parallelism_trigger < 0) cfg_.parallelism_trigger = 0;
    }

    void set_users(int n) override {
        flows_.assign(std::max(n, 0), {});
    }

    void enqueue(const Request& r) override {
        if (r.user_id < 0 || r.user_id >= static_cast<int>(flows_.size()))
            return;
        insert_request(flows_[r.user_id], r);
        detail::sched_debug("[flin enqueue] uid=", r.user_id, " sz=", r.size_bytes);
    }

    // pick_user selects the most under-served flow according to slowdown
    // (actual service / fair share). Lower score => more under-served.
    std::optional<int> pick_user(double now) override {
        if (flows_.empty()) return std::nullopt;

        auto [total_served, active] = update_totals(now);
        if (active == 0) return std::nullopt;
        double share = fair_share(total_served, active); // Ideal bytes served per active flow.

        int best_uid = -1;
        double best_score = std::numeric_limits<double>::infinity();

        for (int uid = 0; uid < static_cast<int>(flows_.size()); ++uid) {
            auto& f = flows_[uid];
            if (f.queue.empty()) continue;

            // Slowdown proxy: actual service vs. fair share. Smaller => under-served.
            double fairness_ratio = share > kEpsilon ? f.served_bytes / share : 0.0;
            // If the flow has not received service recently, treat it as heavily under-served.
            if (f.served_bytes < kEpsilon && share > 0.0) fairness_ratio = 0.0;

            double bias = read_starvation_bias(f, now);
            double score = fairness_ratio * bias;

            if (score < best_score) {
                best_score = score;
                best_uid = uid;
            } else if (std::abs(score - best_score) < 1e-9 && best_uid >= 0) {
                // Tie-breaker: prefer fewer outstanding requests to reduce HOL blocking.
                if (f.outstanding < flows_[best_uid].outstanding) best_uid = uid;
            }
        }

        if (best_uid < 0) return std::nullopt;
        detail::sched_debug("[flin pick] uid=", best_uid, " score=", best_score,
                            " share=", share, " active=", active);
        return best_uid;
    }

    std::optional<Request> pop(int uid) override {
        if (uid < 0 || uid >= static_cast<int>(flows_.size())) return std::nullopt;
        auto& q = flows_[uid].queue;
        if (q.empty()) return std::nullopt;
        Request r = q.front();
        q.pop_front();

        auto& f = flows_[uid];
        f.outstanding += 1;
        f.outstanding_bytes += r.size_bytes;

        detail::sched_debug("[flin pop] uid=", uid, " sz=", r.size_bytes, " remaining=", q.size(),
                            " outstanding=", f.outstanding);
        return r;
    }

    bool empty() const override {
        for (const auto& f : flows_) if (!f.queue.empty()) return false;
        return true;
    }

    void on_request_finished(const Request& req, double finish_time, Metrics* metrics) override {
        if (req.user_id < 0 || req.user_id >= static_cast<int>(flows_.size()))
            return;

        // Update decayed service totals to include time elapsed since last event.
        auto [total_served, active] = update_totals(finish_time);
        auto& f = flows_[req.user_id];
        f.served_bytes += req.size_bytes;
        f.total_served += req.size_bytes;
        f.last_finish = finish_time;
        if (f.outstanding > 0) --f.outstanding;
        if (f.outstanding_bytes >= req.size_bytes)
            f.outstanding_bytes -= req.size_bytes;
        else
            f.outstanding_bytes = 0;

        total_served += req.size_bytes;
        if (active == 0) active = 1; // At least this flow is active now.

        double share = fair_share(total_served, active);
        double fairness_ratio = share > kEpsilon ? f.served_bytes / share : 1.0;

        // Smooth fairness ratio to avoid oscillations in selection.
        f.fairness_ewma = (1.0 - cfg_.fairness_alpha) * f.fairness_ewma +
                          cfg_.fairness_alpha * fairness_ratio;

        double is_read = req.op == OpType::READ ? 1.0 : 0.0;
        f.read_fraction = (1.0 - cfg_.read_alpha) * f.read_fraction + cfg_.read_alpha * is_read;

        // Export fairness info so metrics can log slowdown per flow.
        if (metrics) metrics->record_fairness(req.user_id, fairness_ratio, f.fairness_ewma);

        detail::sched_debug("[flin finish] uid=", req.user_id, " served_bytes=", f.served_bytes,
                            " share=", share, " fairness=", fairness_ratio,
                            " fairness_ewma=", f.fairness_ewma);
    }
};

// WearLevelScheduler composes FLIN's slowdown-aware fairness with a simple
// wear-leveling FTL that tracks per-block erase counts and classifies writes
// as hot or cold. The SSD timing model remains unchanged; wear-leveling is
// surfaced via Metrics so experiments can compare wear variance across
// scheduler policies.
class WearLevelScheduler : public FlinScheduler {
public:
    WearLevelScheduler() = default;

    // Configure wear-leveling parameters and (re)initialize the FTL model.
    void set_wear_config(const WearLevelConfig& cfg, int /*num_channels*/) {
        wear_cfg_ = cfg;
        ftl_ = WearLevelFtl(wear_cfg_);
    }

    void set_users(int n) override {
        FlinScheduler::set_users(n);
        if (wear_cfg_.total_blocks == 0) wear_cfg_.total_blocks = 1024;
        ftl_.reset(wear_cfg_.total_blocks);
    }

    void enqueue(const Request& r) override {
        Request mapped = r;

        if (mapped.op == OpType::WRITE) {
            bool is_hot = false;
            std::uint64_t block = ftl_.map_write(mapped.lba, &is_hot);
            (void)block;
            detail::sched_debug("[wear enqueue] uid=", mapped.user_id,
                                " lba=", mapped.lba,
                                " hot=", is_hot ? 1 : 0);
        } else if (mapped.op == OpType::READ) {
            // Ensure a stable mapping exists for reads, even if this is the
            // first access to the LBA.
            (void)ftl_.map_read(mapped.lba);
        }

        FlinScheduler::enqueue(mapped);
    }

    void on_request_finished(const Request& req,
                             double finish_time,
                             Metrics* metrics) override {
        FlinScheduler::on_request_finished(req, finish_time, metrics);

        if (req.op == OpType::WRITE) {
            ftl_.on_write_completed(req.lba);
            if (metrics) {
                metrics->record_wear_snapshot(ftl_.erase_counts());
            }
        }
    }

    const WearLevelFtl& ftl() const { return ftl_; }

private:
    WearLevelConfig wear_cfg_{};
    WearLevelFtl ftl_;
};

} // namespace ssd
