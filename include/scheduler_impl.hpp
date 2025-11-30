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
    double quantum_ = 4096.0;
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

// FlinScheduler approximates FLIN (Fairness-aware Latency Interference Normalizer).
class FlinScheduler : public Scheduler {
    struct FlowStats {
        std::deque<Request> queue;
        double ewma_bytes = 0.0;
        double read_ewma = 0.5;
        double last_update = 0.0;
    };

    std::vector<FlowStats> flows_;
    std::vector<double> priorities_;
    double window_s_ = 0.002;                 // seconds
    double cap_bytes_per_window_ = 512 * 1024.0;
    double min_throttle_ = 0.15;

    void decay_flow(FlowStats& flow, double now) const {
        if (window_s_ <= 0.0 || now <= flow.last_update) return;
        double delta = now - flow.last_update;
        double factor = std::exp(-delta / window_s_);
        flow.ewma_bytes *= factor;
        flow.last_update = now;
    }

    double priority_for(int uid) const {
        if (uid >= 0 && uid < static_cast<int>(priorities_.size()) && priorities_[uid] > 0.0)
            return priorities_[uid];
        return 1.0;
    }

public:
    void set_users(int n) override {
        flows_.assign(std::max(n, 0), {});
        priorities_.assign(flows_.size(), 1.0);
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
        FlowStats& flow = flows_[r.user_id];
        decay_flow(flow, r.arrival_ts);
        flow.ewma_bytes += r.size_bytes;
        flow.queue.push_back(r);
    }

    std::optional<int> pick_user(double now) override {
        if (flows_.empty()) return std::nullopt;

        int best_uid = -1;
        double best_score = -1.0;

        for (int uid = 0; uid < static_cast<int>(flows_.size()); ++uid) {
            auto& flow = flows_[uid];
            if (flow.queue.empty()) continue;
            decay_flow(flow, now);

            double intensity = cap_bytes_per_window_ > 0.0
                ? flow.ewma_bytes / cap_bytes_per_window_
                : 0.0;

            double throttle = 1.0 - std::min(1.0, intensity);
            throttle = std::clamp(throttle, min_throttle_, 1.0);

            double write_penalty = 1.0 + (1.0 - flow.read_ewma); // more writes => higher penalty
            double backlog = static_cast<double>(flow.queue.size());
            double score = priority_for(uid) * throttle * backlog / write_penalty;

            if (score > best_score) {
                best_score = score;
                best_uid = uid;
            }
        }

        if (best_uid < 0) return std::nullopt;
        return best_uid;
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
        decay_flow(flow, req.finish_ts);
        const double alpha = 0.2;
        double sample = (req.op == OpType::READ) ? 1.0 : 0.0;
        flow.read_ewma = (1.0 - alpha) * flow.read_ewma + alpha * sample;
        flow.ewma_bytes = std::max(0.0, flow.ewma_bytes - static_cast<double>(req.size_bytes));
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
