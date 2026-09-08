// Small shared vocabulary used across the project: string helpers, a monotonic
// timer, and a filesystem-lite layer. Deliberately free of third-party deps so
// the same code compiles for the ARM target with nothing but a C++17 toolchain.
#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace vcc {

// --- strings ---------------------------------------------------------------

std::string Trim(const std::string &s);
std::string ToLower(std::string s);
std::string ToUpper(std::string s);
bool StartsWith(const std::string &s, const std::string &prefix);
bool EndsWith(const std::string &s, const std::string &suffix);

// Splits on every occurrence of `sep`. Empty fields are kept unless
// `skip_empty` is set. Fields are *not* trimmed.
std::vector<std::string> Split(const std::string &s, char sep,
                               bool skip_empty = false);

// Splits on runs of whitespace; never yields empty fields.
std::vector<std::string> SplitWhitespace(const std::string &s);

std::string Join(const std::vector<std::string> &parts,
                 const std::string &sep = " ");

// Everything before the first '#' or ';' that is not inside the payload.
// Used by the .ini / .txt config readers.
std::string StripComment(const std::string &line);

// --- numbers ---------------------------------------------------------------

bool ParseInt(const std::string &s, int *out);
bool ParseFloat(const std::string &s, float *out);
bool ParseBool(const std::string &s, bool *out);

// --- paths -----------------------------------------------------------------

// Always returns '/' separated paths. Windows accepts them everywhere we care
// about (CreateFile, ONNX Runtime, fopen), which keeps config files portable.
std::string PathJoin(const std::string &a, const std::string &b);
std::string PathBase(const std::string &p);
std::string PathDir(const std::string &p);
std::string NormalizeSlashes(std::string p);

bool FileExists(const std::string &path);
bool DirExists(const std::string &path);
int64_t FileSize(const std::string &path);

// Non-recursive listing. Returns names only, sorted. `dirs_only` filters to
// subdirectories.
std::vector<std::string> ListDir(const std::string &path, bool dirs_only);

// Reads the whole file. Returns false if it cannot be opened.
bool ReadFile(const std::string &path, std::string *out);
bool ReadLines(const std::string &path, std::vector<std::string> *out);
bool WriteFile(const std::string &path, const std::string &data);

// Directory of the running executable; the apps use it to locate config/,
// models/ and web/ regardless of the current working directory.
std::string ExecutableDir();

// Walks up from `start` looking for a directory that contains `marker`
// (e.g. "config/app.ini"). Returns "" when not found within `max_up` levels.
std::string FindProjectRoot(const std::string &start, const std::string &marker,
                            int max_up = 6);

// --- timing ----------------------------------------------------------------

class Timer {
 public:
  Timer();
  void Reset();
  double ElapsedMs() const;

 private:
  int64_t start_ns_;
};

int64_t NowMonotonicNs();
std::string IsoTimestampUtc();

}  // namespace vcc
