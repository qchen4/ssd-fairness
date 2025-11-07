#include "util.hpp"

#include <algorithm>
#include <cctype>
#include <fstream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>

namespace util {

namespace {

// Converts a textual op (e.g. "read") into the corresponding OpType value.
OpType parse_op(std::string value) {
    std::transform(value.begin(), value.end(), value.begin(),
                   [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
    if (value == "read")
        return OpType::READ;
    if (value == "write")
        return OpType::WRITE;
    throw std::runtime_error("Unknown op type: " + value);
}

} // namespace

// load_trace_csv converts the CSV trace format into Request records ordered by
// arrival timestamp. Timestamps are provided in microseconds, so they are
// converted to seconds to match the simulator's floating-point timeline.
std::vector<Request> load_trace_csv(const std::string& path) {
    std::ifstream in(path);
    if (!in.is_open()) {
        throw std::runtime_error("Failed to open trace file: " + path);
    }

    std::vector<Request> requests;
    std::unordered_map<std::string, int> user_ids;

    std::string line;
    // Skip header if present.
    if (!std::getline(in, line))
        return requests;

    while (std::getline(in, line)) {
        if (line.empty()) continue;

        std::stringstream ss(line);
        std::string timestamp_us, process_id, type_str, address_str, size_str;

        if (!std::getline(ss, timestamp_us, ',')) continue;
        if (!std::getline(ss, process_id, ',')) continue;
        if (!std::getline(ss, type_str, ',')) continue;
        if (!std::getline(ss, address_str, ',')) continue;
        if (!std::getline(ss, size_str, ',')) continue;

        double ts_seconds = std::stod(timestamp_us) / 1'000'000.0;
        int uid;
        auto it = user_ids.find(process_id);
        if (it == user_ids.end()) {
            uid = static_cast<int>(user_ids.size());
            user_ids.emplace(process_id, uid);
        } else {
            uid = it->second;
        }

        OpType op = parse_op(type_str);
        uint32_t size_bytes = static_cast<uint32_t>(std::stoul(size_str));

        Request req{};
        req.user_id = uid;
        req.op = op;
        req.arrival_ts = ts_seconds;
        req.size_bytes = size_bytes;
        req.start_ts = 0.0;
        req.finish_ts = 0.0;
        requests.push_back(req);
    }

    std::sort(requests.begin(), requests.end(),
              [](const Request& a, const Request& b) {
                  if (a.arrival_ts == b.arrival_ts)
                      return a.user_id < b.user_id;
                  return a.arrival_ts < b.arrival_ts;
              });

    return requests;
}

} // namespace util
