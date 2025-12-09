#pragma once

#include "scheduler.hpp"

#include <memory>
#include <string>

namespace ssd {

// make_scheduler constructs the requested policy or returns nullptr on error.
std::unique_ptr<Scheduler> make_scheduler(const std::string& policy);

} // namespace ssd
