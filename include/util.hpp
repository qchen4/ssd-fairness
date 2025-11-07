#pragma once

#include "types.hpp"

#include <string>
#include <vector>

namespace util {

std::vector<Request> load_trace_csv(const std::string& path);

} // namespace util
