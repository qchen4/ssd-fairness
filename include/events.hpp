#pragma once

#include "types.hpp"

#include <queue>
#include <vector>

namespace ssd {

struct Event {
    double time;      // completion timestamp (seconds)
    int channel;      // channel that completed
    Request request;  // completed request (with start/finish fields)
};

struct EventCompare {
    bool operator()(const Event& a, const Event& b) const {
        return a.time > b.time; // min-heap on time
    }
};

class EventQueue {
public:
    void push(const Event& ev) { queue_.push(ev); }

    bool empty() const { return queue_.empty(); }

    const Event& top() const { return queue_.top(); }

    Event pop() {
        auto ev = queue_.top();
        queue_.pop();
        return ev;
    }

private:
    std::priority_queue<Event, std::vector<Event>, EventCompare> queue_;
};

} // namespace ssd
