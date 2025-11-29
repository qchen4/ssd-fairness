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
