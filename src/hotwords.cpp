#include "vcc/hotwords.h"

#include <algorithm>
#include <cstdio>

#include "vcc/core.h"
#include "vcc/log.h"

namespace vcc {
namespace {

// Parses one line into a phrase.
//
// A trailing ":<number>" is the per-phrase score sherpa-onnx supports and this
// project does not use. Accepting and ignoring it keeps an older hotwords file
// working; warning about it means the user finds out rather than wondering why
// their number had no effect.
bool ParseLine(const std::string &raw, Hotword *out, std::string *why) {
  std::string line = raw;
  const size_t hash = line.find('#');
  if (hash != std::string::npos) line = line.substr(0, hash);
  line = Trim(line);
  if (line.empty()) return false;

  const size_t colon = line.rfind(':');
  if (colon != std::string::npos) {
    const std::string tail = Trim(line.substr(colon + 1));
    float ignored = 0.0f;
    if (!tail.empty() && ParseFloat(tail, &ignored)) {
      if (why) {
        *why = "per-phrase boost ':" + tail +
               "' ignored - the boost is one value for the whole list "
               "(asr.hotwords_score)";
      }
      line = Trim(line.substr(0, colon));
    }
  }

  const std::vector<std::string> words = SplitWhitespace(line);
  if (words.empty()) return false;
  out->phrase = Join(words);
  return true;
}

}  // namespace

bool HotwordList::LoadFile(const std::string &path,
                           std::vector<std::string> *warnings) {
  std::string data;
  if (!ReadFile(path, &data)) return false;
  LoadText(data, warnings);
  VCC_INFO << "loaded " << entries_.size() << " hotword phrase(s) from "
           << PathBase(path);
  return true;
}

void HotwordList::LoadText(const std::string &text,
                           std::vector<std::string> *warnings) {
  entries_.clear();
  std::vector<std::string> lines = Split(text, '\n');
  for (size_t i = 0; i < lines.size(); ++i) {
    if (!lines[i].empty() && lines[i].back() == '\r') lines[i].pop_back();
    Hotword hw;
    std::string why;
    if (!ParseLine(lines[i], &hw, &why)) continue;
    hw.line = static_cast<int>(i + 1);
    if (!why.empty() && warnings) {
      warnings->push_back("hotwords line " + std::to_string(hw.line) + ": " + why);
    }
    entries_.push_back(std::move(hw));
  }
}

std::string HotwordList::ToText() const {
  std::string out;
  for (const Hotword &hw : entries_) {
    out += hw.phrase;
    out += "\n";
  }
  return out;
}

std::string HotwordList::Serialize(float boost,
                                   std::vector<std::string> *warnings) const {
  char score[32];
  std::snprintf(score, sizeof(score), " :%.2f", boost);

  std::string out;
  for (const Hotword &hw : entries_) {
    if (hw.phrase.find('/') != std::string::npos) {
      // See the note in the header: '/' is the record separator on this API, so
      // a phrase containing one would be split into two bogus hotwords.
      if (warnings) {
        warnings->push_back("hotword '" + hw.phrase +
                            "' contains '/', which is the record separator - skipped");
      }
      continue;
    }
    if (!out.empty()) out += "/";
    out += ToUpper(hw.phrase);
    out += score;
  }
  return out;
}

void HotwordList::Add(const std::string &phrase) {
  const std::vector<std::string> words = SplitWhitespace(phrase);
  if (words.empty()) return;
  Hotword hw;
  hw.phrase = Join(words);
  entries_.push_back(std::move(hw));
}

size_t HotwordList::max_words() const {
  size_t most = 0;
  for (const Hotword &hw : entries_) {
    most = std::max(most, SplitWhitespace(hw.phrase).size());
  }
  return most;
}

}  // namespace vcc
