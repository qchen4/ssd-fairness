#pragma once

#include <functional>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace testing {

struct TestFailure : public std::runtime_error {
    TestFailure(const std::string& msg, const char* file, int line)
        : std::runtime_error(file + (":" + std::to_string(line) + " ") + msg) {}
};

struct TestCase {
    std::string name;
    std::function<void()> fn;
};

inline std::vector<TestCase>& registry() {
    static std::vector<TestCase> tests;
    return tests;
}

struct Registrar {
    Registrar(const std::string& name, std::function<void()> fn) {
        registry().push_back(TestCase{name, std::move(fn)});
    }
};

template <typename A, typename B>
void require_eq(const A& a, const B& b, const char* expr, const char* file, int line) {
    if (!(a == b)) {
        std::ostringstream oss;
        oss << "Expected equality for " << expr << " but got " << a << " vs " << b;
        throw TestFailure(oss.str(), file, line);
    }
}

template <typename A, typename B>
void require_near(const A& a, const B& b, double eps, const char* expr, const char* file, int line) {
    double delta = static_cast<double>(a) - static_cast<double>(b);
    if (delta < 0) delta = -delta;
    if (delta > eps) {
        std::ostringstream oss;
        oss << "Expected " << expr << " to be within " << eps << " but delta was " << delta;
        throw TestFailure(oss.str(), file, line);
    }
}

inline void require_true(bool cond, const char* expr, const char* file, int line) {
    if (!cond) {
        throw TestFailure(std::string("Assertion failed: ") + expr, file, line);
    }
}

inline int run_all() {
    int failed = 0;
    for (const auto& test : registry()) {
        try {
            test.fn();
        } catch (const std::exception& e) {
            ++failed;
            std::cerr << "[FAIL] " << test.name << " - " << e.what() << "\n";
            continue;
        }
        std::cout << "[PASS] " << test.name << "\n";
    }
    std::cout << "Ran " << registry().size() << " tests: "
              << (registry().size() - failed) << " passed, "
              << failed << " failed\n";
    return failed;
}

} // namespace testing

#define TEST_CASE(name) \
    static void name(); \
    static ::testing::Registrar registrar_##name(#name, &name); \
    static void name()

#define REQUIRE_TRUE(expr) ::testing::require_true((expr), #expr, __FILE__, __LINE__)
#define REQUIRE_EQ(a, b) ::testing::require_eq((a), (b), #a " == " #b, __FILE__, __LINE__)
#define REQUIRE_NEAR(a, b, eps) ::testing::require_near((a), (b), (eps), #a " ~= " #b, __FILE__, __LINE__)
