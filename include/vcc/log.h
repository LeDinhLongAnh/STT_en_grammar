// Minimal levelled logger. Thread-safe, writes to stderr, optional ANSI colour.
#pragma once

#include <sstream>
#include <string>

namespace vcc {

enum class LogLevel { kTrace = 0, kDebug, kInfo, kWarn, kError, kOff };

LogLevel ParseLogLevel(const std::string &s, LogLevel fallback = LogLevel::kInfo);
const char *LogLevelName(LogLevel l);

void SetLogLevel(LogLevel l);
LogLevel GetLogLevel();
void SetLogColor(bool enabled);

void LogWrite(LogLevel level, const char *file, int line, const std::string &msg);

namespace detail {
class LogStream {
 public:
  LogStream(LogLevel level, const char *file, int line)
      : level_(level), file_(file), line_(line) {}
  ~LogStream() { LogWrite(level_, file_, line_, oss_.str()); }
  std::ostringstream &stream() { return oss_; }

 private:
  LogLevel level_;
  const char *file_;
  int line_;
  std::ostringstream oss_;
};
}  // namespace detail

#define VCC_LOG(lvl)                                                     \
  if (::vcc::GetLogLevel() > (lvl)) {                                    \
  } else                                                                 \
    ::vcc::detail::LogStream((lvl), __FILE__, __LINE__).stream()

#define VCC_TRACE VCC_LOG(::vcc::LogLevel::kTrace)
#define VCC_DEBUG VCC_LOG(::vcc::LogLevel::kDebug)
#define VCC_INFO VCC_LOG(::vcc::LogLevel::kInfo)
#define VCC_WARN VCC_LOG(::vcc::LogLevel::kWarn)
#define VCC_ERROR VCC_LOG(::vcc::LogLevel::kError)

}  // namespace vcc
