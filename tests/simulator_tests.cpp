#include "scheduler_factory.hpp"
#include "simulator.hpp"
#include "test_framework.hpp"
#include "trace_reader.hpp"
#include "types.hpp"

#include <algorithm>
#include <deque>
#include <filesystem>
#include <fstream>
#include <memory>
#include <stdexcept>
#include <vector>

namespace {

Request make_req(int uid, uint32_t size, double arrival, OpType op = OpType::READ) {
    Request r{};
    r.user_id = uid;
    r.op = op;
    r.arrival_ts = arrival;
    r.size_bytes = size;
    return r;
}

class RecordingScheduler : public ssd::Scheduler {
public:
    explicit RecordingScheduler(std::shared_ptr<int> configured = std::make_shared<int>(-1))
        : configured_users_(std::move(configured)) {}

    void set_users(int n) override {
        *configured_users_ = n;
        queues_.assign(std::max(n, 0), {});
    }

    void enqueue(const Request& r) override {
        if (r.user_id < 0) return;
        if (r.user_id >= static_cast<int>(queues_.size()))
            queues_.resize(r.user_id + 1);
        queues_[r.user_id].push_back(r);
    }

    std::optional<int> pick_user(double) override {
        for (int uid = 0; uid < static_cast<int>(queues_.size()); ++uid) {
            if (!queues_[uid].empty()) return uid;
        }
        return std::nullopt;
    }

    std::optional<Request> pop(int uid) override {
        if (uid < 0 || uid >= static_cast<int>(queues_.size()) || queues_[uid].empty())
            return std::nullopt;
        Request r = queues_[uid].front();
        queues_[uid].pop_front();
        return r;
    }

    bool empty() const override {
        for (const auto& q : queues_) {
            if (!q.empty()) return false;
        }
        return true;
    }

    std::shared_ptr<int> configured_handle() const { return configured_users_; }

private:
    std::shared_ptr<int> configured_users_;
    std::vector<std::deque<Request>> queues_;
};

} // namespace

TEST_CASE(SimulatorCompletesTraceAndCalculatesFairness) {
    std::vector<Request> trace = {
        make_req(0, 4096, 0.0),
        make_req(1, 4096, 0.0),
        make_req(0, 4096, 0.001),
        make_req(1, 8192, 0.001),
    };

    ssd::SimulationOptions opts;
    opts.device_cfg = SimConfig{2, 2, 2000.0, 1200.0};
    opts.write_results = false;

    auto scheduler = ssd::make_scheduler("rr");
    ssd::Simulator sim(opts);
    auto result = sim.run(std::move(scheduler), trace);

    REQUIRE_EQ(result.completed_requests, trace.size());

    double expected_fairness = (20480.0 * 20480.0) /
        (2.0 * (8192.0 * 8192.0 + 12288.0 * 12288.0));
    REQUIRE_NEAR(result.metrics.fairness_index(), expected_fairness, 1e-3);
    REQUIRE_TRUE(result.finished_at > 0.0);
}

TEST_CASE(TraceReaderSortsAndAssignsUsers) {
    auto tmp = std::filesystem::temp_directory_path() / "trace_reader_sort.csv";
    {
        std::ofstream out(tmp);
        out << "timestamp,process_id,type,address,size\n";
        out << "200,procB,WRITE,0,1024\n";
        out << "100,procA,READ,0,512\n";
        out << "150,procA,READ,0,512\n";
    }

    ssd::TraceReader reader;
    auto requests = reader.load_csv(tmp.string());

    REQUIRE_EQ(requests.size(), 3u);
    REQUIRE_NEAR(requests[0].arrival_ts, 100.0 / 1'000'000.0, 1e-9);
    REQUIRE_EQ(requests[0].user_id, requests[1].user_id);
    REQUIRE_TRUE(requests[2].user_id != requests[0].user_id);
}

TEST_CASE(TraceReaderHandlesDecimalTimestamps) {
    auto tmp = std::filesystem::temp_directory_path() / "trace_reader_decimal.csv";
    {
        std::ofstream out(tmp);
        out << "timestamp,process_id,type,address,size\n";
        out << "123.5,procA,READ,0,512\n";
        out << "200.25,procB,WRITE,0,1024\n";
    }

    ssd::TraceReader reader;
    auto requests = reader.load_csv(tmp.string());

    REQUIRE_EQ(requests.size(), 2u);
    REQUIRE_NEAR(requests.front().arrival_ts, 123.5 / 1'000'000.0, 1e-12);
}

TEST_CASE(TraceReaderRejectsNegativeUserIds) {
    auto tmp = std::filesystem::temp_directory_path() / "trace_reader_negative_uid.csv";
    {
        std::ofstream out(tmp);
        out << "timestamp,process_id,user_id,type,address,size\n";
        out << "100,procA,-1,READ,0,512\n";
    }

    ssd::TraceReader reader;
    bool threw = false;
    try {
        (void)reader.load_csv(tmp.string());
    } catch (const std::runtime_error&) {
        threw = true;
    }
    REQUIRE_TRUE(threw);
}

TEST_CASE(SimulatorRespectsUserOverride) {
    std::vector<Request> trace = {
        make_req(0, 4096, 0.0),
    };

    ssd::SimulationOptions opts;
    opts.device_cfg = SimConfig{0, 2, 2000.0, 1200.0};
    opts.scheduler.quantum = 4096.0;
    opts.write_results = false;
    opts.user_override = 5;

    ssd::Simulator sim(opts);
    auto configured = std::make_shared<int>(-1);
    auto scheduler = std::make_unique<RecordingScheduler>(configured);
    auto result = sim.run(std::move(scheduler), trace);

    REQUIRE_EQ(result.completed_requests, trace.size());
    REQUIRE_EQ(*configured, 5);
}
