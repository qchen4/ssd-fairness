#include "util.hpp"
#include "trace_reader.hpp"

namespace util {

std::vector<Request> load_trace_csv(const std::string& path) {
    return ssd::TraceReader{}.load_csv(path);
}

} // namespace util
