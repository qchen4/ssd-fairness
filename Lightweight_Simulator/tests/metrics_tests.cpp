#include "metrics.hpp"
#include "test_framework.hpp"
#include "types.hpp"

TEST_CASE(FairnessSkipsIdleUsers) {
    ssd::Metrics metrics(3);

    Request r0{};
    r0.user_id = 0;
    r0.arrival_ts = 0.0;
    r0.finish_ts = 0.001;
    r0.size_bytes = 4096;

    Request r2{};
    r2.user_id = 2;
    r2.arrival_ts = 0.0;
    r2.finish_ts = 0.002;
    r2.size_bytes = 8192;

    metrics.on_finish(r0);
    metrics.on_finish(r2);

    double expected = (12288.0 * 12288.0) /
                      (2.0 * (4096.0 * 4096.0 + 8192.0 * 8192.0));
    REQUIRE_NEAR(metrics.fairness_index(), expected, 1e-6);
    REQUIRE_EQ(metrics.total_bytes(1), 0u); // idle user ignored
}
