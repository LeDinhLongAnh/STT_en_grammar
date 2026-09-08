// Comparing two transcripts, and scoring one against a reference.
//
// The project's claim is "biasing makes the recogniser understand a non-native
// speaker better". That claim is only worth anything as a number, and the number
// is word error rate against a reference the human wrote down. Everything here
// exists to produce that number and to show, word by word, where the two
// transcripts diverged.
#pragma once

#include <string>
#include <vector>

namespace vcc {

enum class DiffOp {
  kEqual,      // same word in both
  kSubstitute, // different word in the same position
  kInsert,     // present in `b` only
  kDelete,     // present in `a` only
};

const char *DiffOpName(DiffOp op);

struct DiffSpan {
  DiffOp op = DiffOp::kEqual;
  std::string a;  // word from the left transcript ("" for an insert)
  std::string b;  // word from the right transcript ("" for a delete)
};

// Word-level alignment of two transcripts, minimum edit distance, reported as a
// span list in reading order. This is what the dashboard renders as coloured
// text: the operative question when biasing changes an output is always "which
// words moved?", and a whole-string comparison cannot answer it.
std::vector<DiffSpan> DiffWords(const std::string &a, const std::string &b);

// True when the two transcripts differ in any word.
bool TranscriptsDiffer(const std::string &a, const std::string &b);

struct ErrorRate {
  size_t ref_words = 0;
  size_t substitutions = 0;
  size_t deletions = 0;
  size_t insertions = 0;

  size_t errors() const { return substitutions + deletions + insertions; }
  // Word error rate. Can exceed 1.0 when the hypothesis rambles — that is
  // correct behaviour for WER, not a bug to clamp away.
  double wer() const {
    return ref_words == 0 ? (errors() ? 1.0 : 0.0)
                          : static_cast<double>(errors()) / ref_words;
  }
};

// WER of `hypothesis` against `reference`, both tokenised with BasicTokens.
ErrorRate ComputeWer(const std::string &reference, const std::string &hypothesis);

// Character error rate, on the space-joined token streams. Worth reporting
// alongside WER because a soft final consonant ("gues" for "guest") is one
// character wrong but a whole word wrong, and the two metrics disagreeing that
// way is itself a useful signal about what kind of error you are looking at.
ErrorRate ComputeCer(const std::string &reference, const std::string &hypothesis);

// Aggregate over a corpus: sum the counts, then divide once. Averaging
// per-clip WERs instead would weight a two-word clip the same as a
// twenty-word one.
struct ErrorRateAccumulator {
  ErrorRate total;
  size_t clips = 0;

  void Add(const ErrorRate &r) {
    total.ref_words += r.ref_words;
    total.substitutions += r.substitutions;
    total.deletions += r.deletions;
    total.insertions += r.insertions;
    ++clips;
  }
  double wer() const { return total.wer(); }
};

}  // namespace vcc
