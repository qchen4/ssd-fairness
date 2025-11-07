#pragma once

#include "types.hpp"

#include <queue>
#include <vector>

namespace ssd {

// Event captures a single completion notification emitted by the SSD.
struct Event {
    double time;      // Completion timestamp in seconds.
    int channel;      // Physical channel whose request finished.
    Request request;  // Copy of the request carrying runtime metadata.
};

struct EventCompare {
    bool operator()(const Event& a, const Event& b) const {
        return a.time > b.time; // min-heap on time
    }
};

// EventQueue maintains a min-heap ordered by completion time.
class EventQueue {
public:
    // Push inserts a new completion event into the queue.
    void push(const Event& ev) { queue_.push(ev); }

    // empty returns true when no events are pending.
    bool empty() const { return queue_.empty(); }

    // top returns a const reference to the earliest event.
    const Event& top() const { return queue_.top(); }

    // pop removes and returns the earliest event.
    Event pop() {
        auto ev = queue_.top();
        queue_.pop();
        return ev;
    }

private:
    std::priority_queue<Event, std::vector<Event>, EventCompare> queue_;
};

} // namespace ssd
