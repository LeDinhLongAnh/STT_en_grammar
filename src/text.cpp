#include "vcc/text.h"

#include <algorithm>
#include <cctype>

#include "vcc/core.h"
#include "vcc/log.h"

namespace vcc {
namespace {

// Substitutions observed on Vietnamese-accented English against this project's
// router vocabulary. Each one is here because the recogniser produced it more
// than once, not because it seemed plausible.
const char *kDefaultRules[][2] = {
    // words the recogniser splits that should be one token
    {"wi fi", "wifi"},
    {"why fi", "wifi"},
    {"wife i", "wifi"},
    {"net work", "network"},
    {"fire wall", "firewall"},
    {"band width", "bandwidth"},
    {"pass word", "password"},
    {"wire less", "wireless"},
    {"un block", "unblock"},
    {"re boot", "reboot"},
    {"re start", "restart"},
    {"you tube", "youtube"},
    {"face book", "facebook"},
    {"tik tok", "tiktok"},
    {"q o s", "qos"},
    // soft final consonants: "guest" is the worst offender in this vocabulary
    {"gues", "guest"},
    {"guess", "guest"},
    {"gest", "guest"},
    {"gas", "guest"},
    {"gust", "guest"},
    // devoicing and vowel drift
    {"reboard", "reboot"},
    {"rebood", "reboot"},
    {"divices", "devices"},
    {"divice", "device"},
    {"conection", "connection"},
    {"bandwith", "bandwidth"},
};

}  // namespace

std::vector<std::string> BasicTokens(const std::string &raw) {
  std::vector<std::string> out;
  std::string cur;
  for (unsigned char uc : raw) {
    const char c = static_cast<char>(std::tolower(uc));
    if (std::isalnum(static_cast<unsigned char>(c))) {
      cur.push_back(c);
    } else if (c == '\'') {
      continue;  // keep contractions glued
    } else {
      if (!cur.empty()) out.push_back(cur);
      cur.clear();
    }
  }
  if (!cur.empty()) out.push_back(cur);
  return out;
}

void RewriteTable::SortLongestFirst() {
  std::stable_sort(rules_.begin(), rules_.end(),
                   [](const RewriteRule &a, const RewriteRule &b) {
                     if (a.from.size() != b.from.size()) {
                       return a.from.size() > b.from.size();
                     }
                     return a.source.size() > b.source.size();
                   });
}

RewriteTable RewriteTable::Default() {
  RewriteTable t;
  for (const auto &r : kDefaultRules) {
    RewriteRule rule;
    rule.from = SplitWhitespace(ToLower(r[0]));
    rule.to = SplitWhitespace(ToLower(r[1]));
    rule.source = std::string(r[0]) + " => " + r[1];
    t.rules_.push_back(std::move(rule));
  }
  t.SortLongestFirst();
  return t;
}

bool RewriteTable::LoadFile(const std::string &path,
                            std::vector<std::string> *warnings) {
  std::string data;
  if (!ReadFile(path, &data)) return false;
  LoadText(data, warnings);
  VCC_INFO << "loaded " << rules_.size() << " rewrite rule(s) from "
           << PathBase(path);
  return true;
}

void RewriteTable::LoadText(const std::string &text,
                            std::vector<std::string> *warnings) {
  rules_.clear();
  std::vector<std::string> lines = Split(text, '\n');
  for (size_t i = 0; i < lines.size(); ++i) {
    std::string line = lines[i];
    if (!line.empty() && line.back() == '\r') line.pop_back();
    const size_t hash = line.find('#');
    if (hash != std::string::npos) line = line.substr(0, hash);
    const size_t semi = line.find(';');
    if (semi != std::string::npos) line = line.substr(0, semi);
    line = Trim(line);
    if (line.empty()) continue;
    // Section headers are tolerated so an older lexicon file still loads.
    if (line.front() == '[' && line.back() == ']') continue;

    const size_t arrow = line.find("=>");
    if (arrow == std::string::npos) {
      if (warnings) {
        warnings->push_back("rewrites line " + std::to_string(i + 1) +
                            ": expected 'pattern => replacement', got '" + line + "'");
      }
      continue;
    }
    RewriteRule rule;
    rule.from = SplitWhitespace(ToLower(Trim(line.substr(0, arrow))));
    rule.to = SplitWhitespace(ToLower(Trim(line.substr(arrow + 2))));
    rule.line = static_cast<int>(i + 1);
    rule.source = line;
    if (rule.from.empty()) {
      if (warnings) {
        warnings->push_back("rewrites line " + std::to_string(i + 1) +
                            ": empty pattern, skipped");
      }
      continue;
    }
    if (rule.from == rule.to) continue;  // identity rule, nothing to do
    rules_.push_back(std::move(rule));
  }
  SortLongestFirst();
}

std::string RewriteTable::ToText() const {
  std::string out;
  for (const RewriteRule &r : rules_) {
    out += Join(r.from) + " => " + Join(r.to) + "\n";
  }
  return out;
}

std::string RewriteTable::Apply(const std::string &text,
                                std::vector<RewriteHit> *hits) const {
  std::vector<std::string> toks = BasicTokens(text);
  if (hits) hits->clear();

  // Four passes is plenty for a table of single- and two-word rules, and it
  // makes a cyclic table terminate instead of spinning.
  const int kMaxPasses = 4;
  bool any_change = false;
  for (int pass = 0; pass < kMaxPasses; ++pass) {
    bool changed = false;
    for (const RewriteRule &rule : rules_) {
      if (rule.from.empty() || rule.from.size() > toks.size()) continue;
      for (size_t i = 0; i + rule.from.size() <= toks.size(); ++i) {
        if (!std::equal(rule.from.begin(), rule.from.end(), toks.begin() + i)) {
          continue;
        }
        if (hits) {
          RewriteHit hit;
          hit.from = Join(rule.from);
          hit.to = Join(rule.to);
          hit.position = i;
          hits->push_back(std::move(hit));
        }
        toks.erase(toks.begin() + i, toks.begin() + i + rule.from.size());
        toks.insert(toks.begin() + i, rule.to.begin(), rule.to.end());
        changed = true;
        any_change = true;
        if (!rule.to.empty()) i += rule.to.size() - 1;
      }
    }
    if (!changed) break;
  }

  // Casing: tokenisation lowercases, but this function's output is the product
  // of the whole filter and a downstream consumer should not see the case
  // change as a side effect of a rule firing somewhere else in the sentence.
  //
  // So: no rule fired -> hand back the input untouched, byte for byte. That is
  // the common path. A rule did fire -> rebuild from tokens and restore the
  // input's case convention, which for these models is either all-caps
  // (zipformer on LibriSpeech) or lowercase.
  //
  // Known limitation: a mixed-case input (Moonshine emits sentence case) loses
  // its capitalisation on the utterances where a rule fires. Preserving it
  // properly means splicing replacements into the original string rather than
  // rebuilding from tokens; not worth the complexity until something downstream
  // actually cares about case.
  if (!any_change) return text;

  const std::string joined = Join(toks);
  bool has_letter = false;
  bool all_upper = true;
  for (unsigned char c : text) {
    if (!std::isalpha(c)) continue;
    has_letter = true;
    if (std::islower(c)) {
      all_upper = false;
      break;
    }
  }
  return (has_letter && all_upper) ? ToUpper(joined) : joined;
}

}  // namespace vcc
