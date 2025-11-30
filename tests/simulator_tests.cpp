#include "scheduler_factory.hpp"
#include "simulator.hpp"
#include "test_framework.hpp"
#include "trace_reader.hpp"
#include "types.hpp"

#include <filesystem>
#include <fstream>
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
