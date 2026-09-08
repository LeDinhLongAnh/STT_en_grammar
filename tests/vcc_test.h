// A ~90-line test harness.
//
// gtest would be a 3 MB dependency and a CMake FetchContent step for what this
// project needs from it: register a function, run them all, report the first
// failing expression with file and line. Keeping it local also means the tests
// cross-compile with the rest of the code.
#pragma once

#include <cmath>
#include <cstdio>
#include <functional>
#include <string>
#include <type_traits>
#include <vector>

namespace vcc_test {

struct Case {
  std::string suite;
  std::string name;
  std::function<void()> fn;
};

std::vector<Case> &Registry();
void Fail(const char *file, int line, const std::string &message);
int RunAll(const std::string &filter);

struct Registrar {
  Registrar(const char *suite, const char *name, std::function<void()> fn) {
    Registry().push_back({suite, name, std::move(fn)});
  }
};

}  // namespace vcc_test

#define VCC_TEST(suite, name)                                          \
  static void suite##_##name##_body();                                 \
  static ::vcc_test::Registrar suite##_##name##_reg(                   \
      #suite, #name, suite##_##name##_body);                           \
  static void suite##_##name##_body()

// A failing check throws, so the rest of the case is skipped but the other
// cases still run.
#define VCC_CHECK(cond)                                                \
  do {                                                                 \
    if (!(cond)) {                                                     \
      ::vcc_test::Fail(__FILE__, __LINE__, "check failed: " #cond);     \
    }                                                                  \
  } while (0)

#define VCC_CHECK_EQ(a, b)                                             \
  do {                                                                 \
    const auto va_ = (a);                                              \
    const auto vb_ = (b);                                              \
    if (!(va_ == vb_)) {                                               \
      ::vcc_test::Fail(__FILE__, __LINE__,                              \
                       std::string(#a " == " #b "\n      left  : ") +   \
                           ::vcc_test::Show(va_) + "\n      right : " + \
                           ::vcc_test::Show(vb_));                      \
    }                                                                  \
  } while (0)

#define VCC_CHECK_NEAR(a, b, eps)                                      \
  do {                                                                 \
    const double va_ = static_cast<double>(a);                          \
    const double vb_ = static_cast<double>(b);                          \
    if (std::fabs(va_ - vb_) > (eps)) {                                 \
      ::vcc_test::Fail(__FILE__, __LINE__,                              \
                       std::string(#a " ~= " #b "\n      left  : ") +   \
                           std::to_string(va_) + "\n      right : " +   \
                           std::to_string(vb_));                        \
    }                                                                  \
  } while (0)

#define VCC_CHECK_GT(a, b)                                             \
  do {                                                                 \
    const auto va_ = (a);                                              \
    const auto vb_ = (b);                                              \
    if (!(va_ > vb_)) {                                                \
      ::vcc_test::Fail(__FILE__, __LINE__,                              \
                       std::string(#a " > " #b "\n      left  : ") +    \
                           ::vcc_test::Show(va_) + "\n      right : " + \
                           ::vcc_test::Show(vb_));                      \
    }                                                                  \
  } while (0)

namespace vcc_test {

inline std::string Show(const std::string &s) { return "\"" + s + "\""; }
inline std::string Show(const char *s) { return std::string("\"") + (s ? s : "") + "\""; }
inline std::string Show(bool b) { return b ? "true" : "false"; }

// Enums print as their underlying value: std::to_string has no overload for
// them, and a scoped enum will not convert on its own.
template <typename T>
inline typename std::enable_if<std::is_enum<T>::value, std::string>::type Show(
    const T &v) {
  return std::to_string(static_cast<long long>(v));
}

template <typename T>
inline typename std::enable_if<!std::is_enum<T>::value, std::string>::type Show(
    const T &v) {
  return std::to_string(v);
}
template <typename T>
inline std::string Show(const std::vector<T> &v) {
  std::string s = "[";
  for (size_t i = 0; i < v.size(); ++i) {
    if (i) s += ", ";
    s += Show(v[i]);
  }
  return s + "]";
}

}  // namespace vcc_test
