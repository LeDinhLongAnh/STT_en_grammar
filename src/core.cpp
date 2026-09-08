#include "vcc/core.h"

#include <algorithm>
#include <cctype>
#include <chrono>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <sstream>

#ifdef _WIN32
#include <direct.h>
#include <windows.h>
#else
#include <dirent.h>
#include <limits.h>
#include <sys/stat.h>
#include <unistd.h>
#endif

namespace vcc {

// --- strings ---------------------------------------------------------------

std::string Trim(const std::string &s) {
  size_t b = 0;
  size_t e = s.size();
  while (b < e && std::isspace(static_cast<unsigned char>(s[b]))) ++b;
  while (e > b && std::isspace(static_cast<unsigned char>(s[e - 1]))) --e;
  return s.substr(b, e - b);
}

std::string ToLower(std::string s) {
  for (char &c : s) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
  return s;
}

std::string ToUpper(std::string s) {
  for (char &c : s) c = static_cast<char>(std::toupper(static_cast<unsigned char>(c)));
  return s;
}

bool StartsWith(const std::string &s, const std::string &prefix) {
  return s.size() >= prefix.size() && s.compare(0, prefix.size(), prefix) == 0;
}

bool EndsWith(const std::string &s, const std::string &suffix) {
  return s.size() >= suffix.size() &&
         s.compare(s.size() - suffix.size(), suffix.size(), suffix) == 0;
}

std::vector<std::string> Split(const std::string &s, char sep, bool skip_empty) {
  std::vector<std::string> out;
  std::string cur;
  for (char c : s) {
    if (c == sep) {
      if (!skip_empty || !cur.empty()) out.push_back(cur);
      cur.clear();
    } else {
      cur.push_back(c);
    }
  }
  if (!skip_empty || !cur.empty()) out.push_back(cur);
  return out;
}

std::vector<std::string> SplitWhitespace(const std::string &s) {
  std::vector<std::string> out;
  std::istringstream iss(s);
  std::string w;
  while (iss >> w) out.push_back(w);
  return out;
}

std::string Join(const std::vector<std::string> &parts, const std::string &sep) {
  std::string out;
  for (size_t i = 0; i < parts.size(); ++i) {
    if (i) out += sep;
    out += parts[i];
  }
  return out;
}

std::string StripComment(const std::string &line) {
  size_t cut = line.size();
  for (size_t i = 0; i < line.size(); ++i) {
    if (line[i] == '#' || line[i] == ';') {
      cut = i;
      break;
    }
  }
  return Trim(line.substr(0, cut));
}

// --- numbers ---------------------------------------------------------------

bool ParseInt(const std::string &s, int *out) {
  const std::string t = Trim(s);
  if (t.empty()) return false;
  char *end = nullptr;
  const long v = std::strtol(t.c_str(), &end, 10);
  if (end == nullptr || *end != '\0') return false;
  *out = static_cast<int>(v);
  return true;
}

bool ParseFloat(const std::string &s, float *out) {
  const std::string t = Trim(s);
  if (t.empty()) return false;
  char *end = nullptr;
  const double v = std::strtod(t.c_str(), &end);
  if (end == nullptr || *end != '\0') return false;
  *out = static_cast<float>(v);
  return true;
}

bool ParseBool(const std::string &s, bool *out) {
  const std::string t = ToLower(Trim(s));
  if (t == "1" || t == "true" || t == "yes" || t == "on") {
    *out = true;
    return true;
  }
  if (t == "0" || t == "false" || t == "no" || t == "off") {
    *out = false;
    return true;
  }
  return false;
}

// --- paths -----------------------------------------------------------------

std::string NormalizeSlashes(std::string p) {
  for (char &c : p) {
    if (c == '\\') c = '/';
  }
  // collapse duplicate separators, but keep a leading "//" (UNC) intact
  std::string out;
  out.reserve(p.size());
  for (size_t i = 0; i < p.size(); ++i) {
    if (p[i] == '/' && !out.empty() && out.back() == '/' && i != 1) continue;
    out.push_back(p[i]);
  }
  return out;
}

std::string PathJoin(const std::string &a, const std::string &b) {
  if (a.empty()) return NormalizeSlashes(b);
  if (b.empty()) return NormalizeSlashes(a);
  // an absolute right-hand side wins
  if (b[0] == '/' || b[0] == '\\' || (b.size() > 1 && b[1] == ':')) {
    return NormalizeSlashes(b);
  }
  std::string out = NormalizeSlashes(a);
  if (out.back() != '/') out.push_back('/');
  out += NormalizeSlashes(b);
  return NormalizeSlashes(out);
}

std::string PathBase(const std::string &p) {
  const std::string n = NormalizeSlashes(p);
  const size_t pos = n.find_last_of('/');
  return pos == std::string::npos ? n : n.substr(pos + 1);
}

std::string PathDir(const std::string &p) {
  const std::string n = NormalizeSlashes(p);
  const size_t pos = n.find_last_of('/');
  return pos == std::string::npos ? std::string(".") : n.substr(0, pos);
}

bool FileExists(const std::string &path) {
#ifdef _WIN32
  const DWORD a = GetFileAttributesA(path.c_str());
  return a != INVALID_FILE_ATTRIBUTES && !(a & FILE_ATTRIBUTE_DIRECTORY);
#else
  struct stat st;
  return stat(path.c_str(), &st) == 0 && S_ISREG(st.st_mode);
#endif
}

bool DirExists(const std::string &path) {
#ifdef _WIN32
  const DWORD a = GetFileAttributesA(path.c_str());
  return a != INVALID_FILE_ATTRIBUTES && (a & FILE_ATTRIBUTE_DIRECTORY);
#else
  struct stat st;
  return stat(path.c_str(), &st) == 0 && S_ISDIR(st.st_mode);
#endif
}

int64_t FileSize(const std::string &path) {
  std::ifstream f(path, std::ios::binary | std::ios::ate);
  if (!f) return -1;
  return static_cast<int64_t>(f.tellg());
}

std::vector<std::string> ListDir(const std::string &path, bool dirs_only) {
  std::vector<std::string> out;
#ifdef _WIN32
  WIN32_FIND_DATAA fd;
  const std::string pattern = PathJoin(path, "*");
  HANDLE h = FindFirstFileA(pattern.c_str(), &fd);
  if (h == INVALID_HANDLE_VALUE) return out;
  do {
    const std::string name = fd.cFileName;
    if (name == "." || name == "..") continue;
    const bool is_dir = (fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) != 0;
    if (dirs_only == is_dir) out.push_back(name);
  } while (FindNextFileA(h, &fd));
  FindClose(h);
#else
  DIR *d = opendir(path.c_str());
  if (!d) return out;
  while (struct dirent *e = readdir(d)) {
    const std::string name = e->d_name;
    if (name == "." || name == "..") continue;
    const bool is_dir = DirExists(PathJoin(path, name));
    if (dirs_only == is_dir) out.push_back(name);
  }
  closedir(d);
#endif
  std::sort(out.begin(), out.end());
  return out;
}

bool ReadFile(const std::string &path, std::string *out) {
  std::ifstream f(path, std::ios::binary);
  if (!f) return false;
  std::ostringstream ss;
  ss << f.rdbuf();
  *out = ss.str();
  return true;
}

bool ReadLines(const std::string &path, std::vector<std::string> *out) {
  std::string data;
  if (!ReadFile(path, &data)) return false;
  out->clear();
  std::string cur;
  for (char c : data) {
    if (c == '\n') {
      if (!cur.empty() && cur.back() == '\r') cur.pop_back();
      out->push_back(cur);
      cur.clear();
    } else {
      cur.push_back(c);
    }
  }
  if (!cur.empty()) {
    if (cur.back() == '\r') cur.pop_back();
    out->push_back(cur);
  }
  return true;
}

bool WriteFile(const std::string &path, const std::string &data) {
  std::ofstream f(path, std::ios::binary | std::ios::trunc);
  if (!f) return false;
  f.write(data.data(), static_cast<std::streamsize>(data.size()));
  return f.good();
}

std::string ExecutableDir() {
#ifdef _WIN32
  char buf[MAX_PATH * 2];
  const DWORD n = GetModuleFileNameA(nullptr, buf, sizeof(buf));
  if (n == 0 || n >= sizeof(buf)) return ".";
  return PathDir(std::string(buf, n));
#elif defined(__APPLE__)
  char buf[4096];
  uint32_t n = sizeof(buf);
  extern int _NSGetExecutablePath(char *, uint32_t *);
  if (_NSGetExecutablePath(buf, &n) != 0) return ".";
  return PathDir(buf);
#else
  char buf[4096];
  const ssize_t n = readlink("/proc/self/exe", buf, sizeof(buf) - 1);
  if (n <= 0) return ".";
  buf[n] = '\0';
  return PathDir(buf);
#endif
}

std::string FindProjectRoot(const std::string &start, const std::string &marker,
                            int max_up) {
  std::string dir = NormalizeSlashes(start);
  for (int i = 0; i <= max_up; ++i) {
    if (FileExists(PathJoin(dir, marker)) || DirExists(PathJoin(dir, marker))) {
      return dir;
    }
    const std::string up = PathDir(dir);
    if (up == dir) break;
    dir = up;
  }
  return std::string();
}

// --- timing ----------------------------------------------------------------

int64_t NowMonotonicNs() {
  using clock = std::chrono::steady_clock;
  return std::chrono::duration_cast<std::chrono::nanoseconds>(
             clock::now().time_since_epoch())
      .count();
}

Timer::Timer() : start_ns_(NowMonotonicNs()) {}
void Timer::Reset() { start_ns_ = NowMonotonicNs(); }
double Timer::ElapsedMs() const {
  return static_cast<double>(NowMonotonicNs() - start_ns_) / 1e6;
}

std::string IsoTimestampUtc() {
  const std::time_t t = std::time(nullptr);
  std::tm tm {};
#ifdef _WIN32
  gmtime_s(&tm, &t);
#else
  gmtime_r(&t, &tm);
#endif
  char buf[32];
  std::snprintf(buf, sizeof(buf), "%04d-%02d-%02dT%02d:%02d:%02dZ",
                tm.tm_year + 1900, tm.tm_mon + 1, tm.tm_mday, tm.tm_hour,
                tm.tm_min, tm.tm_sec);
  return buf;
}

}  // namespace vcc
