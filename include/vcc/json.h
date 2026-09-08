// Just enough JSON for the dashboard API: a streaming writer and a flat
// reader.
//
// A full parser would be dead weight here -- the request bodies this server
// accepts are one level deep ({"model": "...", "threads": 4}), and pulling in a
// header-only library for that would cost more build time than it saves.
#pragma once

#include <string>
#include <vector>

namespace vcc {

// Escapes a string as a JSON string literal, including the surrounding quotes.
std::string JsonQuote(const std::string &s);

// Appends values in order, inserting commas and braces/brackets for you.
//
//   JsonWriter w;
//   w.BeginObject();
//   w.Key("text").String(result.text);
//   w.Key("score").Number(result.score, 3);
//   w.Key("ranked").BeginArray();
//   ...
//   w.End();          // closes the array
//   w.End();          // closes the object
//   std::string body = w.str();
class JsonWriter {
 public:
  JsonWriter &BeginObject();
  JsonWriter &BeginArray();
  JsonWriter &End();

  JsonWriter &Key(const std::string &k);

  JsonWriter &String(const std::string &v);
  JsonWriter &Number(double v, int decimals = 6);
  JsonWriter &Int(long long v);
  JsonWriter &Bool(bool v);
  JsonWriter &Null();
  // Inserts an already-serialised fragment verbatim. Used to pass sherpa-onnx's
  // own result JSON through without re-encoding it.
  JsonWriter &Raw(const std::string &json);

  // Shorthands for the common "key: value" case.
  JsonWriter &Field(const std::string &k, const std::string &v) { return Key(k).String(v); }
  JsonWriter &Field(const std::string &k, const char *v) { return Key(k).String(v ? v : ""); }
  JsonWriter &Field(const std::string &k, double v, int decimals = 6) {
    return Key(k).Number(v, decimals);
  }
  JsonWriter &Field(const std::string &k, int v) { return Key(k).Int(v); }
  JsonWriter &Field(const std::string &k, long long v) { return Key(k).Int(v); }
  JsonWriter &Field(const std::string &k, size_t v) {
    return Key(k).Int(static_cast<long long>(v));
  }
  JsonWriter &Field(const std::string &k, bool v) { return Key(k).Bool(v); }

  const std::string &str() const { return out_; }

 private:
  void Separate();

  std::string out_;
  // For each open container: is it an object, and has anything been written?
  std::vector<std::pair<bool, bool>> stack_;
  bool expect_value_ = false;  // a Key() was just written
};

// Flat object reader: pulls scalar members out of a one-level JSON object.
// Nested objects and arrays are skipped, not parsed. Returns false only when
// the input is not an object at all.
class JsonObject {
 public:
  bool Parse(const std::string &text);

  bool Has(const std::string &key) const;
  std::string GetString(const std::string &key, const std::string &def = "") const;
  double GetNumber(const std::string &key, double def) const;
  int GetInt(const std::string &key, int def) const;
  bool GetBool(const std::string &key, bool def) const;

 private:
  std::vector<std::pair<std::string, std::string>> members_;  // value as text
};

}  // namespace vcc
