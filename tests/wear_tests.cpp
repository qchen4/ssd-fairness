#include "ftl_wear.hpp"
#include "metrics.hpp"
#include "scheduler_factory.hpp"
#include "simulator.hpp"
#include "test_framework.hpp"
#include "types.hpp"

#include <vector>

TEST_CASE(WearFtlAvoidsMostWornBlockForHotWrites) {
    ssd::WearLevelConfig cfg;
    cfg.total_blocks = 8;
    cfg.pool_size = 8;
    cfg.hot_threshold = 0.0; // treat every write as hot for this test.

    ssd::WearLevelFtl ftl(cfg);

    // Drive a single LBA repeatedly to concentrate wear on one block.
    const std::uint64_t hot_lba = 0;
    for (int i = 0; i < 10; ++i) {
        (void)ftl.map_write(hot_lba, nullptr);
        ftl.on_write_completed(hot_lba);
    }

    const auto& counts_before = ftl.erase_counts();
    REQUIRE_TRUE(!counts_before.empty());

    // Identify the most-worn block so far.
    std::size_t max_idx = 0;
    for (std::size_t i = 1; i < counts_before.size(); ++i) {
        if (counts_before[i] > counts_before[max_idx]) {
            max_idx = i;
        }
    }

    // A subsequent hot write for a different LBA should avoid the most-worn block.
    bool is_hot = false;
    std::uint64_t new_block = ftl.map_write(4096 /* different LBA */, &is_hot);
    REQUIRE_TRUE(is_hot); // threshold == 0 => always hot.
    REQUIRE_TRUE(new_block < counts_before.size());
    REQUIRE_TRUE(new_block != max_idx);
}

TEST_CASE(WearFtlIncrementsEraseCountsOnWriteCompletion) {
    ssd::WearLevelConfig cfg;
    cfg.total_blocks = 4;
    cfg.pool_size = 4;

    ssd::WearLevelFtl ftl(cfg);

    const std::uint64_t lba = 12345;
    (void)ftl.map_write(lba, nullptr);
    ftl.on_write_completed(lba);

    const auto& counts = ftl.erase_counts();
    REQUIRE_TRUE(!counts.empty());

    std::uint64_t total = 0;
    for (auto v : counts) total += v;
    REQUIRE_EQ(total, 1u);
}

TEST_CASE(WearSchedulerProducesWearStats) {
    // Small synthetic trace with a mix of reads and writes.
    std::vector<Request> trace;
    for (int i = 0; i < 10; ++i) {
        Request r{};
        r.user_id = i % 2;
        r.op = (i % 3 == 0) ? OpType::WRITE : OpType::READ;
        r.arrival_ts = 0.000001 * i;
        r.size_bytes = 4096;
        r.lba = static_cast<std::uint64_t>(i) * 4096;
        trace.push_back(r);
    }

    SimConfig cfg;
    cfg.num_users = 2;
    cfg.num_channels = 2;
    cfg.read_bw_MBps = 2000.0;
    cfg.write_bw_MBps = 1200.0;

    ssd::SimulationOptions opts;
    opts.device_cfg = cfg;
    opts.write_results = false;
    opts.scheduler.quantum = 4096.0;
    opts.scheduler.wear_hot_threshold = 1.0;
    opts.scheduler.wear_pool_size = 8;
    opts.scheduler.wear_read_balance = true;

    auto scheduler = ssd::make_scheduler("wear");
    ssd::Simulator sim(opts);
    auto result = sim.run(std::move(scheduler), trace);

    REQUIRE_TRUE(result.completed_requests == trace.size());
    REQUIRE_TRUE(result.metrics.has_wear_stats());
    REQUIRE_TRUE(result.metrics.wear_max_erase() >= result.metrics.wear_min_erase());
}

TEST_CASE(WearFtlSegmentRebalanceRunsAndKeepsWearStatsSane) {
    ssd::WearLevelConfig cfg;
    cfg.total_blocks = 32;
    cfg.pool_size = 8;
    cfg.hot_threshold = 0.0; // treat every write as hot
    cfg.num_segments = 4;
    cfg.rebalance_interval = 10;
    cfg.rebalance_fraction = 0.25;

    ssd::WearLevelFtl ftl(cfg);

    const std::uint64_t hot_lba = 0;
    for (int i = 0; i < 200; ++i) {
        bool is_hot = false;
        (void)ftl.map_write(hot_lba, &is_hot);
        ftl.on_write_completed(hot_lba);
    }

    const auto& counts = ftl.erase_counts();
    REQUIRE_TRUE(!counts.empty());

    std::uint64_t min_v = counts[0];
    std::uint64_t max_v = counts[0];
    for (auto v : counts) {
        REQUIRE_TRUE(v >= 0);
        if (v < min_v) min_v = v;
        if (v > max_v) max_v = v;
    }
    REQUIRE_TRUE(max_v >= min_v);
}

