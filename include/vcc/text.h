// The second stage of the filter: repairing what biasing could not.
//
// Contextual biasing works inside the decoder, so it can only promote token
// sequences the model is able to emit at all. Some substitutions survive it —
// a Vietnamese speaker's "guest" lands on "gas" often enough that the decoder
// picks "gas" even with "GUEST NETWORK" boosted. Those are cheap to fix
// afterwards, one rule at a time, and the rules are data.
//
// This is deliberately a *surgical* mechanism. The tempting alternative is a
// fuzzy nearest-neighbour pass over the whole transcript, which fixes the one
// case you were looking at and quietly corrupts words you were not.
#pragma once

#include <string>
#include <vector>

namespace vcc {

// Lowercase, split on non-alphanumerics. Apostrophes are absorbed into the word
// ("what's" -> "whats") so contractions do not fragment.
std::vector<std::string> BasicTokens(const std::string &raw);

// One substitution rule over the token stream.
struct RewriteRule {
  std::vector<std::string> from;  // token sequence to look for
  std::vector<std::string> to;    // replacement (may be empty to delete)
  std::string source;             // as written, for display
  int line = 0;
};

// A rule that actually fired, so the UI can show *why* the text changed rather
// than just that it did.
struct RewriteHit {
  std::string from;
  std::string to;
  size_t position = 0;  // token index in the pre-rewrite stream
};

class RewriteTable {
 public:
  // Parses config/rewrites.txt: `pattern => replacement` lines, '#' comments,
  // optional [section] headers which are ignored. Returns false only when the
  // file cannot be read; malformed lines are reported and skipped.
  bool LoadFile(const std::string &path, std::vector<std::string> *warnings = nullptr);
  void LoadText(const std::string &text, std::vector<std::string> *warnings = nullptr);
  std::string ToText() const;

  // Applies every rule repeatedly until the stream stops changing, bounded so a
  // cyclic table cannot hang the decoder loop. Longest patterns are tried first.
  std::string Apply(const std::string &text, std::vector<RewriteHit> *hits = nullptr) const;

  const std::vector<RewriteRule> &rules() const { return rules_; }
  size_t size() const { return rules_.size(); }
  bool empty() const { return rules_.empty(); }
  void clear() { rules_.clear(); }

  // The compiled-in baseline, used when no rewrites file is present. Covers the
  // substitutions this project has actually observed on Vietnamese-accented
  // English rather than everything imaginable.
  static RewriteTable Default();

 private:
  void SortLongestFirst();
  std::vector<RewriteRule> rules_;
};

}  // namespace vcc
