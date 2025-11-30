#include "ftl_wear.hpp"
#include "metrics.hpp"
#include "scheduler_factory.hpp"
#include "simulator.hpp"
#include "test_framework.hpp"
#include "types.hpp"

#include <vector>

TEST_CASE(WearFtlAllocatesPhysicalPagesAndMapsReads) {
    ssd::WearLevelConfig cfg;
    cfg.total_blocks = 8;
    cfg.pool_size = 8;
    cfg.hot_threshold = 0.0;
    cfg.pages_per_block = 4;

    ssd::WearLevelFtl ftl(cfg);

    const std::uint64_t hot_lba = 0;
    for (int i = 0; i < 32; ++i) {
        bool is_hot = false;
        std::uint64_t block = ftl.map_write(hot_lba, &is_hot);
        REQUIRE_TRUE(block < cfg.total_blocks);
        REQUIRE_TRUE(is_hot);
    }

    const std::uint64_t other_lba = 123456;
    auto block_new = ftl.map_write(other_lba, nullptr);
    REQUIRE_TRUE(block_new < cfg.total_blocks);
    REQUIRE_EQ(ftl.map_read(other_lba), block_new);
}

TEST_CASE(WearFtlGcIncrementsEraseCounts) {
    ssd::WearLevelConfig cfg;
    cfg.total_blocks = 2;
    cfg.pool_size = 2;
    cfg.hot_threshold = 0.0;
    cfg.pages_per_block = 2;

    ssd::WearLevelFtl ftl(cfg);

    // Repeatedly overwrite the same LBA to force invalid pages and GC.
    const std::uint64_t lba = 42;
    for (int i = 0; i < 50; ++i) {
        (void)ftl.map_write(lba, nullptr);
    }

    const auto& counts = ftl.erase_counts();
    REQUIRE_TRUE(!counts.empty());

    bool saw_wear = false;
    for (auto v : counts) {
        if (v > 0) saw_wear = true;
    }
    REQUIRE_TRUE(saw_wear);
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
        REQUIRE_TRUE(static_cast<double>(v) >= 0.0);
        if (v < min_v) min_v = v;
        if (v > max_v) max_v = v;
    }
    REQUIRE_TRUE(max_v >= min_v);
}

TEST_CASE(WearFtlTriggersGcAndProducesNonZeroWearVariance) {
    ssd::WearLevelConfig cfg;
    cfg.total_blocks = 8;
    cfg.pages_per_block = 4; // total physical pages = 32
    cfg.pool_size = 4;
    cfg.hot_threshold = 0.0; // treat all writes as hot so WL is always active
    cfg.num_segments = 1;    // disable segment rebalance for this basic GC test
    cfg.rebalance_interval = 0;
    cfg.rebalance_fraction = 0.0;

    ssd::WearLevelFtl ftl(cfg);

    const int num_writes = 1000;
    for (int i = 0; i < num_writes; ++i) {
        std::uint64_t lba = static_cast<std::uint64_t>(i % 16); // small logical space
        bool is_hot = false;
        auto block = ftl.map_write(lba, &is_hot);
        (void)block;
        ftl.on_write_completed(lba);
    }

    const auto& counts = ftl.erase_counts();
    REQUIRE_TRUE(!counts.empty());

    std::uint64_t min_ec = counts[0];
    std::uint64_t max_ec = counts[0];
    for (auto ec : counts) {
        if (ec < min_ec) min_ec = ec;
        if (ec > max_ec) max_ec = ec;
    }

    // At least one erase happened and wear is non-uniform.
    REQUIRE_TRUE(max_ec > 0);
    REQUIRE_TRUE(max_ec > min_ec);

    // Metrics should see non-zero wear variance.
    ssd::Metrics m(1);
    m.record_wear_snapshot(counts);
    REQUIRE_TRUE(m.has_wear_stats());
    REQUIRE_TRUE(m.wear_variance() > 0.0);

    // Optional: confirm that GC actually ran during the test.
    REQUIRE_TRUE(ftl.gc_invocations_debug() > 0);
}

