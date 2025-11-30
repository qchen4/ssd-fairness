// scheduler_factory.cpp: Builds scheduler instances based on policy names.
#include "scheduler_factory.hpp"

#include "scheduler_impl.hpp"

namespace ssd {

std::unique_ptr<Scheduler> make_scheduler(const std::string& policy) {
    if (policy == "fifo" || policy == "fcfs") {
        return std::make_unique<FifoScheduler>();
    }
    if (policy == "rr") {
        return std::make_unique<RoundRobinScheduler>();
    }
    if (policy == "drr") {
        return std::make_unique<DeficitRoundRobinScheduler>();
    }
    if (policy == "qfq" || policy == "wfq") {
        return std::make_unique<WeightedFairScheduler>();
    }
    if (policy == "flin") {
        return std::make_unique<FlinScheduler>();
    }
    return nullptr;
}
} // namespace ssd
