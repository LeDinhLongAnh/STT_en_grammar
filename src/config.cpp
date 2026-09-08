#include "vcc/config.h"

#include "vcc/core.h"
#include "vcc/log.h"

namespace vcc {

bool Config::LoadFile(const std::string &path,
                      std::vector<std::string> *warnings) {
  std::vector<std::string> lines;
  if (!ReadLines(path, &lines)) return false;

  std::string section;
  for (size_t i = 0; i < lines.size(); ++i) {
    const std::string line = StripComment(lines[i]);
    if (line.empty()) continue;

    if (line.front() == '[' && line.back() == ']') {
      section = ToLower(Trim(line.substr(1, line.size() - 2)));
      continue;
    }
    const size_t eq = line.find('=');
    if (eq == std::string::npos) {
      if (warnings) {
        warnings->push_back(path + ":" + std::to_string(i + 1) +
                            ": ignored line without '=': " + line);
      }
      continue;
    }
    std::string key = ToLower(Trim(line.substr(0, eq)));
    const std::string value = Trim(line.substr(eq + 1));
    if (key.empty()) {
      if (warnings) {
        warnings->push_back(path + ":" + std::to_string(i + 1) +
                            ": ignored line with empty key");
      }
      continue;
    }
    if (!section.empty()) key = section + "." + key;
    values_[key] = value;
  }
  return true;
}

bool Config::SetFromAssignment(const std::string &kv) {
  const size_t eq = kv.find('=');
  if (eq == std::string::npos) return false;
  Set(ToLower(Trim(kv.substr(0, eq))), Trim(kv.substr(eq + 1)));
  return true;
}

void Config::Set(const std::string &key, const std::string &value) {
  values_[ToLower(key)] = value;
}

bool Config::Has(const std::string &key) const {
  return values_.count(ToLower(key)) != 0;
}

std::string Config::GetString(const std::string &key,
                              const std::string &def) const {
  const std::string k = ToLower(key);
  used_[k] = true;
  const auto it = values_.find(k);
  return it == values_.end() ? def : it->second;
}

int Config::GetInt(const std::string &key, int def) const {
  const std::string raw = GetString(key);
  int v = def;
  if (raw.empty()) return def;
  if (!ParseInt(raw, &v)) {
    VCC_WARN << "config: " << key << "='" << raw << "' is not an int, using "
             << def;
    return def;
  }
  return v;
}

float Config::GetFloat(const std::string &key, float def) const {
  const std::string raw = GetString(key);
  float v = def;
  if (raw.empty()) return def;
  if (!ParseFloat(raw, &v)) {
    VCC_WARN << "config: " << key << "='" << raw << "' is not a number, using "
             << def;
    return def;
  }
  return v;
}

bool Config::GetBool(const std::string &key, bool def) const {
  const std::string raw = GetString(key);
  bool v = def;
  if (raw.empty()) return def;
  if (!ParseBool(raw, &v)) {
    VCC_WARN << "config: " << key << "='" << raw
             << "' is not a bool, using " << (def ? "true" : "false");
    return def;
  }
  return v;
}

std::string Config::GetPath(const std::string &key, const std::string &root,
                            const std::string &def) const {
  const std::string raw = GetString(key, def);
  if (raw.empty()) return raw;
  return PathJoin(root, raw);
}

std::vector<std::string> Config::UsedKeys() const {
  std::vector<std::string> out;
  out.reserve(used_.size());
  for (const auto &kv : used_) out.push_back(kv.first);
  return out;
}

}  // namespace vcc
