// Flat key/value config backed by an ini-ish file.
//
// Sections are namespaces, so
//     [asr]
//     num_threads = 4
// is addressable as "asr.num_threads". That keeps lookups explicit at the call
// site and lets the CLI override anything with --set asr.num_threads=3.
#pragma once

#include <map>
#include <string>
#include <vector>

namespace vcc {

class Config {
 public:
  // Loads and merges a file on top of whatever is already set. Returns false
  // only when the file cannot be read; malformed lines are reported through
  // `warnings` and skipped.
  bool LoadFile(const std::string &path, std::vector<std::string> *warnings = nullptr);

  // Applies "key=value". Returns false if the string has no '='.
  bool SetFromAssignment(const std::string &kv);

  void Set(const std::string &key, const std::string &value);
  bool Has(const std::string &key) const;

  std::string GetString(const std::string &key, const std::string &def = "") const;
  int GetInt(const std::string &key, int def) const;
  float GetFloat(const std::string &key, float def) const;
  bool GetBool(const std::string &key, bool def) const;

  // Resolves a path-valued key relative to `root` unless it is already absolute.
  std::string GetPath(const std::string &key, const std::string &root,
                      const std::string &def = "") const;

  const std::map<std::string, std::string> &values() const { return values_; }

  // Every key that was read at least once. Used by the dashboard to show the
  // effective configuration without dumping dead keys.
  std::vector<std::string> UsedKeys() const;

 private:
  std::map<std::string, std::string> values_;
  mutable std::map<std::string, bool> used_;
};

}  // namespace vcc
