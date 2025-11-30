#pragma once

#include "scheduler.hpp"

#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstdlib>
#include <deque>
#include <iostream>
#include <limits>
#include <memory>
#include <optional>
#include <unordered_map>
#include <vector>

namespace ssd {

namespace detail {
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

// RoundRobinScheduler cycles through users in order, skipping empty queues.
class RoundRobinScheduler : public Scheduler {
    std::vector<std::deque<Request>> queues_;
    int next_ = 0;

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
class DeficitRoundRobinScheduler : public Scheduler {
    std::vector<std::deque<Request>> queues_;
    std::vector<int64_t> deficit_;
    std::vector<double> weights_;
    // Default quantum: 16KB is a good balance for typical SSD workloads (4KB-64KB range)
    // For optimal results, use sqrt(min_request_size * max_request_size)
    double quantum_ = 16384.0;
    int next_ = 0;

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
    // FIX: Loop until at least one user can send to avoid deadlock when quantum < request_size
    std::optional<int> pick_user(double) override {
        if (queues_.empty()) return std::nullopt;
        
        // Check if there are any pending requests
        bool has_pending = false;
        for (const auto& q : queues_) {
            if (!q.empty()) { has_pending = true; break; }
        }
        if (!has_pending) return std::nullopt;

        // Keep accumulating deficit until someone can send
        // Max iterations = max_request_size / quantum (safety limit to prevent infinite loop)
        constexpr int kMaxRounds = 1000;
        for (int round = 0; round < kMaxRounds; ++round) {
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
                                        " need=", r.size_bytes, " next=", next_, " rounds=", round + 1);
                    return uid;
                }
            }
        }
        // Should never reach here unless quantum is 0 or something is very wrong
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
class WeightedFairScheduler : public Scheduler {
    struct TaggedRequest {
        Request req;
        double finish_tag = 0.0;
    };

    std::vector<std::deque<TaggedRequest>> queues_;
    std::vector<double> weights_;
    std::vector<double> last_finish_;
    double virtual_time_ = 0.0;
    int active_flows_ = 0;

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
        double start_tag = std::max(last_finish_[r.user_id], virtual_time_);
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

// FlinScheduler: Fairness-aware Latency Interference Normalizer
// Based on ISCA 2018 paper: "FLIN: Enabling Fairness and Enhancing Performance in Modern NVMe SSDs"
// 
// Key insight: Fairness = min(slowdown) / max(slowdown)
// Goal: equalize slowdowns across all flows by prioritizing disadvantaged flows
//
// Simplified implementation focusing on the CORE idea:
// - Track estimated slowdown per flow (RT_shared / RT_alone)
// - Prioritize flows with HIGHER slowdowns to equalize them
class FlinScheduler : public Scheduler {
    struct FlowStats {
        std::deque<Request> queue;
        
        // Slowdown tracking
        double estimated_alone_rt = 0.0001;   // Baseline RT (100us default)
        double estimated_slowdown = 1.0;      // Current slowdown estimate
        uint64_t completed_requests = 0;
        
        // For fair round-robin when slowdowns are similar
        int64_t virtual_time = 0;
    };

    std::vector<FlowStats> flows_;
    std::vector<double> priorities_;
    int next_user_ = 0;  // For round-robin fallback
    
    // Parameters
    double slowdown_alpha_ = 0.05;            // EWMA factor for slowdown updates (slower = more stable)
    double fairness_threshold_ = 0.3;         // When slowdown diff < 30%, use round-robin (more stable)

    double priority_for(int uid) const {
        if (uid >= 0 && uid < static_cast<int>(priorities_.size()) && priorities_[uid] > 0.0)
            return priorities_[uid];
        return 1.0;
    }

    // Estimate "alone" response time based on request characteristics
    double estimate_alone_rt(const Request& req) const {
        // Simple model based on SSD characteristics
        // Read: ~25us base + transfer time at 150MB/s per channel
        // Write: ~50us base + transfer time at 100MB/s per channel
        double base = (req.op == OpType::READ) ? 0.000025 : 0.000050;
        double transfer = (req.op == OpType::READ) 
            ? req.size_bytes / (150.0 * 1024 * 1024)
            : req.size_bytes / (100.0 * 1024 * 1024);
        return base + transfer;
    }

public:
    void set_users(int n) override {
        flows_.assign(std::max(n, 0), {});
        priorities_.assign(flows_.size(), 1.0);
        next_user_ = 0;
    }

    void set_weights(const std::vector<double>& weights) override {
        if (flows_.empty()) return;
        priorities_.assign(flows_.size(), 1.0);
        for (size_t i = 0; i < priorities_.size() && i < weights.size(); ++i) {
            priorities_[i] = std::max(weights[i], 1e-6);
        }
    }

    void enqueue(const Request& r) override {
        if (r.user_id < 0 || r.user_id >= static_cast<int>(flows_.size()))
            return;
        flows_[r.user_id].queue.push_back(r);
    }

    std::optional<int> pick_user(double now) override {
        if (flows_.empty()) return std::nullopt;

        // Count active flows and check if we have enough samples for reliable slowdowns
        int active_count = 0;
        int flows_with_samples = 0;
        double min_slowdown = std::numeric_limits<double>::max();
        double max_slowdown = 0.0;
        
        for (const auto& flow : flows_) {
            if (!flow.queue.empty()) {
                active_count++;
                // Only consider slowdown if we have enough samples (at least 10 requests)
                if (flow.completed_requests >= 10) {
                    flows_with_samples++;
                    min_slowdown = std::min(min_slowdown, flow.estimated_slowdown);
                    max_slowdown = std::max(max_slowdown, flow.estimated_slowdown);
                }
            }
        }
        
        if (active_count == 0) return std::nullopt;
        
        // If not enough samples yet, use pure round-robin (warmup phase)
        // This prevents early scheduling decisions from creating artificial differences
        if (flows_with_samples < active_count) {
            for (int i = 0; i < static_cast<int>(flows_.size()); ++i) {
                int uid = (next_user_ + i) % flows_.size();
                if (!flows_[uid].queue.empty()) {
                    next_user_ = (uid + 1) % flows_.size();
                    return uid;
                }
            }
        }
        
        // Calculate current fairness estimate
        double fairness_ratio = (max_slowdown > 0) ? min_slowdown / max_slowdown : 1.0;
        
        // If slowdowns are similar (fairness_ratio > threshold), use simple round-robin
        // This provides stability in symmetric workloads
        if (fairness_ratio > (1.0 - fairness_threshold_)) {
            // Round-robin among active flows
            for (int i = 0; i < static_cast<int>(flows_.size()); ++i) {
                int uid = (next_user_ + i) % flows_.size();
                if (!flows_[uid].queue.empty()) {
                    next_user_ = (uid + 1) % flows_.size();
                    return uid;
                }
            }
        }
        
        // Otherwise, prioritize flows with HIGHER slowdowns to equalize
        int best_uid = -1;
        double best_score = -1.0;
        
        for (int uid = 0; uid < static_cast<int>(flows_.size()); ++uid) {
            const FlowStats& flow = flows_[uid];
            if (flow.queue.empty()) continue;

            // Score = priority * slowdown (higher slowdown = higher priority)
            // Use log scale to prevent extreme differences
            double slowdown_factor = 1.0 + std::log1p(flow.estimated_slowdown);
            double score = priority_for(uid) * slowdown_factor;
            
            // Aging factor to prevent starvation
            const Request& front_req = flow.queue.front();
            double wait_time = now - front_req.arrival_ts;
            if (wait_time > 0.0001) {  // > 100us wait
                score *= (1.0 + std::log1p(wait_time * 1000));  // Log-scale aging
            }

            if (score > best_score) {
                best_score = score;
                best_uid = uid;
            }
        }

        if (best_uid >= 0) {
            next_user_ = (best_uid + 1) % flows_.size();
        }
        return best_uid >= 0 ? std::optional<int>(best_uid) : std::nullopt;
    }

    std::optional<Request> pop(int uid) override {
        if (uid < 0 || uid >= static_cast<int>(flows_.size()) || flows_[uid].queue.empty())
            return std::nullopt;
        Request req = flows_[uid].queue.front();
        flows_[uid].queue.pop_front();
        return req;
    }

    bool empty() const override {
        for (const auto& flow : flows_)
            if (!flow.queue.empty()) return false;
        return true;
    }

    void on_request_finished(const Request& req) override {
        if (req.user_id < 0 || req.user_id >= static_cast<int>(flows_.size()))
            return;
        
        FlowStats& flow = flows_[req.user_id];
        flow.completed_requests++;
        
        // Calculate actual response time
        double actual_rt = req.finish_ts - req.arrival_ts;
        if (actual_rt <= 0) actual_rt = 0.0001;
        
        // Update estimated "alone" RT
        double alone_rt = estimate_alone_rt(req);
        flow.estimated_alone_rt = (1.0 - slowdown_alpha_) * flow.estimated_alone_rt 
                                + slowdown_alpha_ * alone_rt;
        
        // Update estimated slowdown: actual_rt / alone_rt
        if (flow.estimated_alone_rt > 0) {
            double instant_slowdown = actual_rt / flow.estimated_alone_rt;
            instant_slowdown = std::clamp(instant_slowdown, 0.1, 1000.0);
            flow.estimated_slowdown = (1.0 - slowdown_alpha_) * flow.estimated_slowdown 
                                    + slowdown_alpha_ * instant_slowdown;
        }
    }
};

// StartGapScheduler rotates logical-to-physical user mapping to simulate SGFS.
class StartGapScheduler : public Scheduler {
    std::unique_ptr<Scheduler> base_;
    int rotate_every_ = 200;
    int gap_ = 1;
    int rotate_count_ = 0;
    int start_ = 0;
    int users_ = 0;
    std::unordered_map<int, int> remap_;

public:
    explicit StartGapScheduler(std::unique_ptr<Scheduler> base)
        : base_(std::move(base)) {}

    void set_users(int n) override {
        users_ = std::max(n, 0);
        base_->set_users(users_);
        remap_.clear();
        rotate_count_ = 0;
        start_ = 0;
    }

    void set_weights(const std::vector<double>& w) override {
        base_->set_weights(w);
    }

    void set_quantum(double q) override {
        base_->set_quantum(q);
    }

    void enqueue(const Request& r) override {
        base_->enqueue(r);
        detail::sched_debug("[sgfs enqueue] uid=", r.user_id);
    }

    std::optional<int> pick_user(double now) override {
        if (users_ == 0) return std::nullopt;

        auto uid = base_->pick_user(now);
        if (!uid) return std::nullopt;

        if (rotate_every_ > 0 && ++rotate_count_ >= rotate_every_) {
            if (users_ > 0) start_ = (start_ + gap_) % users_;
            rotate_count_ = 0;
        }

        int mapped = users_ > 0 ? ( (*uid + start_) % users_) : *uid;
        remap_[mapped] = *uid;
        detail::sched_debug("[sgfs pick] logical=", mapped, " physical=", *uid,
                            " start=", start_, " rotate_count=", rotate_count_);
        return mapped;
    }

    std::optional<Request> pop(int uid) override {
        int actual = uid;
        auto it = remap_.find(uid);
        if (it != remap_.end()) {
            actual = it->second;
            remap_.erase(it);
        }
        detail::sched_debug("[sgfs pop] logical=", uid, " physical=", actual);
        return base_->pop(actual);
    }

    bool empty() const override {
        return base_->empty();
    }

    void on_request_finished(const Request& req) override {
        base_->on_request_finished(req);
    }

    void set_start_gap(int rotate_every, int gap) {
        rotate_every_ = std::max(1, rotate_every);
        gap_ = std::max(1, gap);
    }
};

} // namespace ssd
