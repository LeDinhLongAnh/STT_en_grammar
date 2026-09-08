#include <exception>
#include <string>

#include "vcc/log.h"
#include "vcc_test.h"

namespace vcc_test {
namespace {

struct Failure : std::exception {
  std::string message;
  explicit Failure(std::string m) : message(std::move(m)) {}
  const char *what() const noexcept override { return message.c_str(); }
};

}  // namespace

std::vector<Case> &Registry() {
  static std::vector<Case> cases;
  return cases;
}

void Fail(const char *file, int line, const std::string &message) {
  throw Failure(std::string(file) + ":" + std::to_string(line) + "\n      " + message);
}

int RunAll(const std::string &filter) {
  int passed = 0;
  int failed = 0;
  int skipped = 0;
  std::string current_suite;

  for (const Case &c : Registry()) {
    const std::string full = c.suite + "." + c.name;
    if (!filter.empty() && full.find(filter) == std::string::npos) {
      ++skipped;
      continue;
    }
    if (c.suite != current_suite) {
      current_suite = c.suite;
      std::printf("\n%s\n", current_suite.c_str());
    }
    try {
      c.fn();
      std::printf("  ok    %s\n", c.name.c_str());
      ++passed;
    } catch (const Failure &f) {
      std::printf("  FAIL  %s\n    %s\n", c.name.c_str(), f.what());
      ++failed;
    } catch (const std::exception &e) {
      std::printf("  FAIL  %s\n    unexpected exception: %s\n", c.name.c_str(), e.what());
      ++failed;
    }
  }

  std::printf("\n%d passed, %d failed", passed, failed);
  if (skipped) std::printf(", %d skipped by filter", skipped);
  std::printf("\n");
  return failed == 0 ? 0 : 1;
}

}  // namespace vcc_test

int main(int argc, char **argv) {
  // Test output should be the assertions, not the library's own chatter.
  vcc::SetLogLevel(vcc::LogLevel::kError);
  vcc::SetLogColor(false);
  const std::string filter = argc > 1 ? argv[1] : "";
  return vcc_test::RunAll(filter);
}
