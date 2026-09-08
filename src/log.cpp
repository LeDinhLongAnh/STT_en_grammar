#include "vcc/log.h"

#include <cstdio>
#include <mutex>

#include "vcc/core.h"

namespace vcc {
namespace {

std::mutex g_mu;
LogLevel g_level = LogLevel::kInfo;
bool g_color =
#ifdef _WIN32
    false;  // enabled explicitly by the apps once they know the terminal
#else
    true;
#endif

const char *ColorFor(LogLevel l) {
  switch (l) {
    case LogLevel::kTrace: return "\033[90m";
    case LogLevel::kDebug: return "\033[36m";
    case LogLevel::kInfo:  return "\033[32m";
    case LogLevel::kWarn:  return "\033[33m";
    case LogLevel::kError: return "\033[31m";
    default:               return "";
  }
}

}  // namespace

LogLevel ParseLogLevel(const std::string &s, LogLevel fallback) {
  const std::string t = ToLower(Trim(s));
  if (t == "trace") return LogLevel::kTrace;
  if (t == "debug") return LogLevel::kDebug;
  if (t == "info")  return LogLevel::kInfo;
  if (t == "warn" || t == "warning") return LogLevel::kWarn;
  if (t == "error") return LogLevel::kError;
  if (t == "off" || t == "none" || t == "quiet") return LogLevel::kOff;
  return fallback;
}

const char *LogLevelName(LogLevel l) {
  switch (l) {
    case LogLevel::kTrace: return "TRACE";
    case LogLevel::kDebug: return "DEBUG";
    case LogLevel::kInfo:  return "INFO ";
    case LogLevel::kWarn:  return "WARN ";
    case LogLevel::kError: return "ERROR";
    default:               return "OFF  ";
  }
}

void SetLogLevel(LogLevel l) { g_level = l; }
LogLevel GetLogLevel() { return g_level; }
void SetLogColor(bool enabled) { g_color = enabled; }

void LogWrite(LogLevel level, const char *file, int line,
              const std::string &msg) {
  if (level < g_level) return;
  const std::string where = PathBase(file ? file : "?");
  std::lock_guard<std::mutex> lock(g_mu);
  if (g_color) {
    std::fprintf(stderr, "%s[%s]\033[0m \033[90m%s:%d\033[0m %s\n",
                 ColorFor(level), LogLevelName(level), where.c_str(), line,
                 msg.c_str());
  } else {
    std::fprintf(stderr, "[%s] %s:%d %s\n", LogLevelName(level), where.c_str(),
                 line, msg.c_str());
  }
  std::fflush(stderr);
}

}  // namespace vcc
