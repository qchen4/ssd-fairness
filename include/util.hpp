#pragma once

#include "types.hpp"

#include <string>
#include <vector>

namespace util {

// load_trace_csv parses the provided trace and returns requests sorted by arrival.
std::vector<Request> load_trace_csv(const std::string& path);

} // namespace util
