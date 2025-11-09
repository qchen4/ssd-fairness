#pragma once

#include "types.hpp"

#include <string>
#include <vector>

namespace util {

// load_trace_csv parses the provided trace (legacy/new CSV or blkparse output)
// and returns requests sorted by arrival timestamp.
std::vector<Request> load_trace_csv(const std::string& path);

} // namespace util
