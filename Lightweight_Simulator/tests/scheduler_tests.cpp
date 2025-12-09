#include "scheduler_impl.hpp"
#include "test_framework.hpp"
#include "types.hpp"

#include <optional>

namespace {

Request make_req(int uid, uint32_t size = 4096, double arrival = 0.0) {
    Request r{};
    r.user_id = uid;
    r.op = OpType::READ;
    r.arrival_ts = arrival;
    r.size_bytes = size;
    return r;
}

} // namespace

TEST_CASE(RoundRobinCyclesUsers) {
    ssd::RoundRobinScheduler sched;
    sched.set_users(3);

    sched.enqueue(make_req(0));
    sched.enqueue(make_req(1));
    sched.enqueue(make_req(2));

    auto u0 = sched.pick_user(0.0);
    REQUIRE_TRUE(u0.has_value());
    REQUIRE_EQ(*u0, 0);
    REQUIRE_TRUE(sched.pop(*u0).has_value());

    auto u1 = sched.pick_user(0.0);
    REQUIRE_TRUE(u1.has_value());
    REQUIRE_EQ(*u1, 1);
    REQUIRE_TRUE(sched.pop(*u1).has_value());

    auto u2 = sched.pick_user(0.0);
    REQUIRE_TRUE(u2.has_value());
    REQUIRE_EQ(*u2, 2);
    REQUIRE_TRUE(sched.pop(*u2).has_value());

    auto none = sched.pick_user(0.0);
    REQUIRE_TRUE(!none.has_value());
    REQUIRE_TRUE(sched.empty());
}

TEST_CASE(DeficitAccumulatesAcrossRounds) {
    ssd::DeficitRoundRobinScheduler sched;
    sched.set_users(1);
    sched.set_quantum(4096.0);

    sched.enqueue(make_req(0, 8192));

    auto first = sched.pick_user(0.0);
    REQUIRE_TRUE(!first.has_value()); // deficit not yet sufficient

    auto second = sched.pick_user(0.0);
    REQUIRE_TRUE(second.has_value());
    REQUIRE_EQ(*second, 0);

    auto req = sched.pop(*second);
    REQUIRE_TRUE(req.has_value());
    REQUIRE_EQ(req->size_bytes, 8192u);
    REQUIRE_TRUE(sched.empty());
}

TEST_CASE(WeightedFairHonorsWeights) {
    ssd::WeightedFairScheduler sched;
    sched.set_users(2);
    sched.set_weights({1.0, 2.0});

    sched.enqueue(make_req(0, 4096));
    sched.enqueue(make_req(1, 4096));

    auto first = sched.pick_user(0.0);
    REQUIRE_TRUE(first.has_value());
    REQUIRE_EQ(*first, 1); // higher weight finishes sooner
    REQUIRE_TRUE(sched.pop(*first).has_value());

    auto second = sched.pick_user(0.0);
    REQUIRE_TRUE(second.has_value());
    REQUIRE_EQ(*second, 0);
}

TEST_CASE(MinMaxSelectsMinimumRatio) {
    ssd::MinMaxScheduler sched;
    sched.set_users(3);

    // All flows start with service=0, so metric = (0+1)/1 = 1.0 for all
    sched.enqueue(make_req(0, 4096));
    sched.enqueue(make_req(1, 4096));
    sched.enqueue(make_req(2, 4096));

    // First selection: all have same metric, should pick first (0)
    auto first = sched.pick_user(0.0);
    REQUIRE_TRUE(first.has_value());
    auto req0 = sched.pop(*first);
    REQUIRE_TRUE(req0.has_value());
    REQUIRE_EQ(req0->user_id, 0);

    // Now flow 0 has service=4096, metric = (4096+1)/1 = 4097
    // Flows 1 and 2 have metric = (0+1)/1 = 1.0
    // Should pick flow 1 or 2 (whichever comes first)
    auto second = sched.pick_user(0.0);
    REQUIRE_TRUE(second.has_value());
    REQUIRE_TRUE(*second == 1 || *second == 2);
    auto req1 = sched.pop(*second);
    REQUIRE_TRUE(req1.has_value());

    // Now the selected flow has service, so the other should be selected
    auto third = sched.pick_user(0.0);
    REQUIRE_TRUE(third.has_value());
    auto req2 = sched.pop(*third);
    REQUIRE_TRUE(req2.has_value());
}

TEST_CASE(MinMaxRespectsWeights) {
    ssd::MinMaxScheduler sched;
    sched.set_users(2);
    sched.set_weights({1.0, 2.0});

    sched.enqueue(make_req(0, 4096));
    sched.enqueue(make_req(1, 4096));

    // Flow 0: metric = (0+1)/1 = 1.0
    // Flow 1: metric = (0+1)/2 = 0.5
    // Should pick flow 1 (lower metric = more under-served)
    auto first = sched.pick_user(0.0);
    REQUIRE_TRUE(first.has_value());
    REQUIRE_EQ(*first, 1); // Higher weight means lower metric when service is equal
    auto req1 = sched.pop(*first);
    REQUIRE_TRUE(req1.has_value());

    // After serving flow 1: service=4096, metric = (4096+1)/2 = 2048.5
    // Flow 0: metric = (0+1)/1 = 1.0
    // Should pick flow 0
    auto second = sched.pick_user(0.0);
    REQUIRE_TRUE(second.has_value());
    REQUIRE_EQ(*second, 0);
}
