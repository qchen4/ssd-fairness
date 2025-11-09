#include "util.hpp"

#include <algorithm>
#include <cctype>
#include <fstream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

namespace util {

namespace {

constexpr uint32_t kSectorSizeBytes = 512;

void trim_in_place(std::string& s) {
    const auto start = s.find_first_not_of(" \t\r\n");
    if (start == std::string::npos) {
        s.clear();
        return;
    }
    const auto end = s.find_last_not_of(" \t\r\n");
    s.erase(end + 1);
    s.erase(0, start);
}

bool looks_like_header(const std::string& line) {
    std::stringstream ss(line);
    std::string first_field;
    if (!std::getline(ss, first_field, ',')) return true;
    trim_in_place(first_field);
    if (first_field.empty()) return true;
    try {
        size_t consumed = 0;
        std::stoll(first_field, &consumed);
        for (; consumed < first_field.size(); ++consumed) {
            if (!std::isspace(static_cast<unsigned char>(first_field[consumed])))
                return true;
        }
        return false;
    } catch (const std::exception&) {
        return true;
    }
}

double parse_timestamp_seconds(const std::string& value, size_t line_no) {
    try {
        double ts_us = std::stod(value);
        return ts_us / 1'000'000.0;
    } catch (const std::exception& e) {
        throw std::runtime_error("Failed to parse timestamp on line " +
                                 std::to_string(line_no) + ": " + e.what());
    }
}

int parse_user_id_field(const std::string& value, size_t line_no) {
    try {
        return std::stoi(value);
    } catch (const std::exception& e) {
        throw std::runtime_error("Failed to parse user_id on line " +
                                 std::to_string(line_no) + ": " + e.what());
    }
}

uint32_t parse_size_field(const std::string& value, size_t line_no) {
    try {
        unsigned long parsed = std::stoul(value);
        if (parsed > std::numeric_limits<uint32_t>::max()) {
            throw std::out_of_range("value exceeds uint32_t");
        }
        return static_cast<uint32_t>(parsed);
    } catch (const std::exception& e) {
        throw std::runtime_error("Failed to parse size on line " +
                                 std::to_string(line_no) + ": " + e.what());
    }
}

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
// converted to seconds to match the simulator's floating-point timeline. The
// parser accepts both the legacy 5-column format and the extended 6-column
// format that provides explicit user IDs.
std::vector<Request> load_trace_csv(const std::string& path) {
    std::ifstream in(path);
    if (!in.is_open()) {
        throw std::runtime_error("Failed to open trace file: " + path);
    }

    std::vector<Request> requests;
    std::unordered_map<std::string, int> process_user_ids;
    int next_auto_user_id = 0;

    std::string line;
    size_t line_no = 0;
    bool saw_data_line = false;

    auto append_request = [&requests](int uid, OpType op, double ts_seconds,
                                      uint32_t size_bytes) {
        Request req{};
        req.user_id = uid;
        req.op = op;
        req.arrival_ts = ts_seconds;
        req.size_bytes = size_bytes;
        req.start_ts = 0.0;
        req.finish_ts = 0.0;
        requests.push_back(req);
    };

    auto process_line = [&](const std::string& text, size_t current_line) {
        std::stringstream ss(text);
        std::vector<std::string> tokens;
        tokens.reserve(6);

        std::string token;
        while (std::getline(ss, token, ',')) {
            trim_in_place(token);
            tokens.push_back(token);
        }
        if (tokens.empty()) return;

        if (tokens.size() == 6) {
            double ts_seconds = parse_timestamp_seconds(tokens[0], current_line);
            const std::string& process_id = tokens[1];
            int declared_uid = parse_user_id_field(tokens[2], current_line);
            OpType op = parse_op(tokens[3]);
            uint32_t size_bytes = parse_size_field(tokens[5], current_line);

            auto [it, inserted] = process_user_ids.emplace(process_id, declared_uid);
            if (!inserted && it->second != declared_uid) {
                throw std::runtime_error("Line " + std::to_string(current_line) +
                                         ": process '" + process_id +
                                         "' has conflicting user_id values (" +
                                         std::to_string(it->second) + " vs " +
                                         std::to_string(declared_uid) + ")");
            }
            append_request(declared_uid, op, ts_seconds, size_bytes);
            return;
        }

        if (tokens.size() == 5) {
            double ts_seconds = parse_timestamp_seconds(tokens[0], current_line);
            const std::string& process_id = tokens[1];
            OpType op = parse_op(tokens[2]);
            uint32_t size_bytes = parse_size_field(tokens[4], current_line);

            auto [it, inserted] =
                process_user_ids.emplace(process_id, next_auto_user_id);
            if (inserted) ++next_auto_user_id;

            append_request(it->second, op, ts_seconds, size_bytes);
            return;
        }

        auto handle_blktrace = [&]() -> bool {
            std::stringstream ws(text);
            std::string device;
            if (!(ws >> device)) return false;
            if (device.find(',') == std::string::npos) return false;

            std::string cpu_str, seq_str, ts_str, pid_str, action, rwbs;
            if (!(ws >> cpu_str >> seq_str >> ts_str >> pid_str >> action >> rwbs))
                return false;

            double ts_seconds;
            try {
                ts_seconds = std::stod(ts_str);
            } catch (const std::exception&) {
                return false;
            }

            // Non-queue events are recognized but do not generate requests.
            if (action != "Q") {
                return true;
            }

            std::string lba_str, plus_token, length_str;
            if (!(ws >> lba_str >> plus_token >> length_str)) {
                throw std::runtime_error("Line " + std::to_string(current_line) +
                                         ": incomplete blktrace data for queue event");
            }
            if (plus_token != "+") {
                throw std::runtime_error("Line " + std::to_string(current_line) +
                                         ": expected '+' before sector count");
            }

            uint64_t sectors = 0;
            try {
                sectors = std::stoull(length_str);
            } catch (const std::exception& e) {
                throw std::runtime_error("Line " + std::to_string(current_line) +
                                         ": invalid sector count: " + e.what());
            }
            uint64_t bytes64 = sectors * static_cast<uint64_t>(kSectorSizeBytes);
            if (bytes64 > std::numeric_limits<uint32_t>::max()) {
                throw std::runtime_error("Line " + std::to_string(current_line) +
                                         ": request size exceeds uint32_t");
            }
            uint32_t size_bytes = static_cast<uint32_t>(bytes64);

            std::string cmd_token;
            std::string process_label = pid_str;
            if (ws >> cmd_token) {
                if (!cmd_token.empty() && cmd_token.front() == '[') {
                    if (cmd_token.back() == ']') {
                        cmd_token = cmd_token.substr(1, cmd_token.size() - 2);
                    } else {
                        cmd_token.erase(0, 1);
                    }
                }
                if (!cmd_token.empty()) {
                    process_label += ":" + cmd_token;
                }
            }

            std::transform(rwbs.begin(), rwbs.end(), rwbs.begin(),
                           [](unsigned char c) { return static_cast<char>(std::toupper(c)); });
            OpType op = (rwbs.find('W') != std::string::npos) ? OpType::WRITE : OpType::READ;

            auto [it, inserted] =
                process_user_ids.emplace(process_label, next_auto_user_id);
            if (inserted) ++next_auto_user_id;

            append_request(it->second, op, ts_seconds, size_bytes);
            return true;
        };

        if (handle_blktrace()) return;

        throw std::runtime_error("Line " + std::to_string(current_line) +
                                 ": expected CSV or blktrace format");
    };

    while (std::getline(in, line)) {
        ++line_no;
        if (!line.empty() && line.back() == '\r') line.pop_back();

        const auto first = line.find_first_not_of(" \t\r\n");
        if (first == std::string::npos) continue;
        if (line[first] == '#') continue;

        if (!saw_data_line && looks_like_header(line)) {
            continue;
        }

        process_line(line, line_no);
        saw_data_line = true;
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
