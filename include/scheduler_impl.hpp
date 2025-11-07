#pragma once

#include "scheduler.hpp"

#include <algorithm>
#include <deque>
#include <limits>
#include <memory>
#include <optional>
#include <unordered_map>
#include <vector>

namespace ssd {

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
    }

    // pick_user returns the next user id that has pending work.
    std::optional<int> pick_user(double) override {
        if (queues_.empty()) return std::nullopt;

        for (int i = 0; i < static_cast<int>(queues_.size()); ++i) {
            int candidate = (next_ + i) % queues_.size();
            if (!queues_[candidate].empty()) {
                next_ = (candidate + 1) % queues_.size();
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
        return best_uid;
    }

    std::optional<Request> pop(int uid) override {
        if (uid < 0 || uid >= static_cast<int>(queues_.size()) || queues_[uid].empty())
            return std::nullopt;
        TaggedRequest tagged = queues_[uid].front();
        queues_[uid].pop_front();
        if (queues_[uid].empty()) --active_flows_;
        return tagged.req;
    }

    bool empty() const override {
        for (const auto& q : queues_)
            if (!q.empty()) return false;
        return true;
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
        return mapped;
    }

    std::optional<Request> pop(int uid) override {
        int actual = uid;
        auto it = remap_.find(uid);
        if (it != remap_.end()) {
            actual = it->second;
            remap_.erase(it);
        }
        return base_->pop(actual);
    }

    bool empty() const override {
        return base_->empty();
    }

    void set_start_gap(int rotate_every, int gap) {
        rotate_every_ = std::max(1, rotate_every);
        gap_ = std::max(1, gap);
    }
};

} // namespace ssd
