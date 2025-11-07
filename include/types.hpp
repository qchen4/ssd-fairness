#pragma once
#include <cstdint>
#include <string>

// Timestamp type used across the project (microseconds since epoch)
using timestamp_t = int64_t;

enum class OpType : uint8_t { READ=0, WRITE=1 };

struct Request {
  int user_id;          // tenant id
  OpType op;
  double arrival_ts;    // seconds
  uint32_t size_bytes;  // request size (bytes)
  // runtime:
  double start_ts{0.0};
  double finish_ts{0.0};
};

struct SimConfig {
  int num_users = 4;
  int num_channels = 8;
  double read_bw_MBps = 1200.0;   // aggregate device BW assumption
  double write_bw_MBps = 800.0;   // aggregate
  // simple: service time = size / (agg_BW / num_channels)
};
