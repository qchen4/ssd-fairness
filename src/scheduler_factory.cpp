#include "scheduler_factory.hpp"

#include "scheduler_impl.hpp"

namespace ssd {

std::unique_ptr<Scheduler> make_scheduler(const std::string& policy) {
    if (policy == "rr") {
        return std::make_unique<RoundRobinScheduler>();
    }
    if (policy == "drr") {
        return std::make_unique<DeficitRoundRobinScheduler>();
    }
    if (policy == "qfq" || policy == "wfq") {
        return std::make_unique<WeightedFairScheduler>();
    }
    if (policy == "sgfs") {
        auto base = std::make_unique<WeightedFairScheduler>();
        return std::make_unique<StartGapScheduler>(std::move(base));
    }
    return nullptr;
    }
} // namespace ssd
