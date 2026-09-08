#include "vcc/json.h"

#include <cmath>
#include <cstdio>

#include "vcc/core.h"

namespace vcc {

std::string JsonQuote(const std::string &s) {
  std::string out;
  out.reserve(s.size() + 2);
  out.push_back('"');
  for (unsigned char c : s) {
    switch (c) {
      case '"':  out += "\\\""; break;
      case '\\': out += "\\\\"; break;
      case '\n': out += "\\n"; break;
      case '\r': out += "\\r"; break;
      case '\t': out += "\\t"; break;
      case '\b': out += "\\b"; break;
      case '\f': out += "\\f"; break;
      default:
        if (c < 0x20) {
          char buf[8];
          std::snprintf(buf, sizeof(buf), "\\u%04x", c);
          out += buf;
        } else {
          // Bytes >= 0x80 pass through: our payloads are already UTF-8 and JSON
          // permits raw UTF-8 inside string literals.
          out.push_back(static_cast<char>(c));
        }
    }
  }
  out.push_back('"');
  return out;
}

void JsonWriter::Separate() {
  if (expect_value_) {
    expect_value_ = false;
    return;
  }
  if (stack_.empty()) return;
  if (stack_.back().second) out_.push_back(',');
  stack_.back().second = true;
}

JsonWriter &JsonWriter::BeginObject() {
  Separate();
  out_.push_back('{');
  stack_.emplace_back(true, false);
  return *this;
}

JsonWriter &JsonWriter::BeginArray() {
  Separate();
  out_.push_back('[');
  stack_.emplace_back(false, false);
  return *this;
}

JsonWriter &JsonWriter::End() {
  if (stack_.empty()) return *this;
  out_.push_back(stack_.back().first ? '}' : ']');
  stack_.pop_back();
  return *this;
}

JsonWriter &JsonWriter::Key(const std::string &k) {
  Separate();
  out_ += JsonQuote(k);
  out_.push_back(':');
  expect_value_ = true;
  return *this;
}

JsonWriter &JsonWriter::String(const std::string &v) {
  Separate();
  out_ += JsonQuote(v);
  return *this;
}

JsonWriter &JsonWriter::Number(double v, int decimals) {
  Separate();
  if (!std::isfinite(v)) {
    // JSON has no NaN/Infinity. null is the honest encoding.
    out_ += "null";
    return *this;
  }
  char buf[64];
  std::snprintf(buf, sizeof(buf), "%.*f", decimals < 0 ? 0 : decimals, v);
  // trim trailing zeros so the payload stays readable
  std::string s = buf;
  if (s.find('.') != std::string::npos) {
    while (!s.empty() && s.back() == '0') s.pop_back();
    if (!s.empty() && s.back() == '.') s.pop_back();
  }
  if (s.empty() || s == "-") s = "0";
  out_ += s;
  return *this;
}

JsonWriter &JsonWriter::Int(long long v) {
  Separate();
  out_ += std::to_string(v);
  return *this;
}

JsonWriter &JsonWriter::Bool(bool v) {
  Separate();
  out_ += v ? "true" : "false";
  return *this;
}

JsonWriter &JsonWriter::Null() {
  Separate();
  out_ += "null";
  return *this;
}

JsonWriter &JsonWriter::Raw(const std::string &json) {
  Separate();
  out_ += json.empty() ? "null" : json;
  return *this;
}

// --- reader ----------------------------------------------------------------

namespace {

void SkipWs(const std::string &s, size_t *i) {
  while (*i < s.size() && std::isspace(static_cast<unsigned char>(s[*i]))) ++*i;
}

// Reads a JSON string starting at s[*i] == '"'. Returns the decoded value.
bool ReadString(const std::string &s, size_t *i, std::string *out) {
  if (*i >= s.size() || s[*i] != '"') return false;
  ++*i;
  out->clear();
  while (*i < s.size()) {
    const char c = s[*i];
    if (c == '"') {
      ++*i;
      return true;
    }
    if (c == '\\') {
      if (*i + 1 >= s.size()) return false;
      const char e = s[*i + 1];
      *i += 2;
      switch (e) {
        case 'n': out->push_back('\n'); break;
        case 'r': out->push_back('\r'); break;
        case 't': out->push_back('\t'); break;
        case 'b': out->push_back('\b'); break;
        case 'f': out->push_back('\f'); break;
        case 'u': {
          // Only the BMP subset we would ever send; enough for the dashboard.
          if (*i + 4 > s.size()) return false;
          const std::string hex = s.substr(*i, 4);
          *i += 4;
          const unsigned cp = static_cast<unsigned>(std::strtoul(hex.c_str(), nullptr, 16));
          if (cp < 0x80) {
            out->push_back(static_cast<char>(cp));
          } else if (cp < 0x800) {
            out->push_back(static_cast<char>(0xC0 | (cp >> 6)));
            out->push_back(static_cast<char>(0x80 | (cp & 0x3F)));
          } else {
            out->push_back(static_cast<char>(0xE0 | (cp >> 12)));
            out->push_back(static_cast<char>(0x80 | ((cp >> 6) & 0x3F)));
            out->push_back(static_cast<char>(0x80 | (cp & 0x3F)));
          }
          break;
        }
        default: out->push_back(e); break;
      }
      continue;
    }
    out->push_back(c);
    ++*i;
  }
  return false;
}

// Consumes one value and returns its raw text. Nested containers are matched
// by depth counting, which is all we need to skip past them.
bool ReadRawValue(const std::string &s, size_t *i, std::string *out) {
  SkipWs(s, i);
  if (*i >= s.size()) return false;
  const size_t start = *i;
  if (s[*i] == '"') {
    std::string decoded;
    if (!ReadString(s, i, &decoded)) return false;
    *out = decoded;  // strings come back decoded, not raw
    return true;
  }
  if (s[*i] == '{' || s[*i] == '[') {
    int depth = 0;
    bool in_str = false;
    while (*i < s.size()) {
      const char c = s[*i];
      if (in_str) {
        if (c == '\\') ++*i;
        else if (c == '"') in_str = false;
      } else if (c == '"') {
        in_str = true;
      } else if (c == '{' || c == '[') {
        ++depth;
      } else if (c == '}' || c == ']') {
        --depth;
        if (depth == 0) {
          ++*i;
          *out = s.substr(start, *i - start);
          return true;
        }
      }
      ++*i;
    }
    return false;
  }
  while (*i < s.size() && s[*i] != ',' && s[*i] != '}' && s[*i] != ']') ++*i;
  *out = Trim(s.substr(start, *i - start));
  return true;
}

}  // namespace

bool JsonObject::Parse(const std::string &text) {
  members_.clear();
  size_t i = 0;
  SkipWs(text, &i);
  if (i >= text.size() || text[i] != '{') return false;
  ++i;
  while (true) {
    SkipWs(text, &i);
    if (i < text.size() && text[i] == '}') return true;
    std::string key;
    if (!ReadString(text, &i, &key)) return false;
    SkipWs(text, &i);
    if (i >= text.size() || text[i] != ':') return false;
    ++i;
    std::string value;
    if (!ReadRawValue(text, &i, &value)) return false;
    members_.emplace_back(key, value);
    SkipWs(text, &i);
    if (i < text.size() && text[i] == ',') {
      ++i;
      continue;
    }
    if (i < text.size() && text[i] == '}') return true;
    return i >= text.size();  // tolerate a truncated tail rather than throwing
  }
}

bool JsonObject::Has(const std::string &key) const {
  for (const auto &m : members_) {
    if (m.first == key) return true;
  }
  return false;
}

std::string JsonObject::GetString(const std::string &key,
                                  const std::string &def) const {
  for (const auto &m : members_) {
    if (m.first == key) return m.second;
  }
  return def;
}

double JsonObject::GetNumber(const std::string &key, double def) const {
  const std::string raw = GetString(key);
  if (raw.empty()) return def;
  float v = 0.0f;
  if (!ParseFloat(raw, &v)) return def;
  return v;
}

int JsonObject::GetInt(const std::string &key, int def) const {
  const std::string raw = GetString(key);
  if (raw.empty()) return def;
  int v = 0;
  if (ParseInt(raw, &v)) return v;
  float f = 0.0f;
  if (ParseFloat(raw, &f)) return static_cast<int>(f);
  return def;
}

bool JsonObject::GetBool(const std::string &key, bool def) const {
  const std::string raw = GetString(key);
  if (raw.empty()) return def;
  bool v = def;
  if (ParseBool(raw, &v)) return v;
  return def;
}

}  // namespace vcc
