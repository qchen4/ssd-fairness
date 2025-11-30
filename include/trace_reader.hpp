#pragma once

#include "types.hpp"

#include <string>
#include <vector>

namespace ssd {

// TraceReader loads request traces into in-memory vectors. It currently
// understands the CSV and blkparse formats handled by util::load_trace_csv
// and keeps parsing logic encapsulated behind a simple interface so tests and
// tools can reuse it.
class TraceReader {
public:
    struct Options {
        bool sort_by_arrival = true; // enforce deterministic order
    };

    TraceReader();
    explicit TraceReader(Options opts);

    // load_csv reads the trace at |path| and returns a vector of Request
    // records. It throws on malformed data.
    std::vector<Request> load_csv(const std::string& path) const;

private:
    Options opts_;
};

} // namespace ssd
