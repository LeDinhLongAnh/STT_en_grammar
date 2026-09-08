#include "vcc/diff.h"

#include <algorithm>

#include "vcc/core.h"
#include "vcc/text.h"

namespace vcc {
namespace {

// Standard edit-distance table over token sequences, with a traceback.
// Sequences here are single utterances (a few dozen words at most), so the
// quadratic table is a few kilobytes and the simple version is the right one.
struct EditTable {
  std::vector<std::vector<size_t>> cost;
  size_t n = 0;
  size_t m = 0;

  EditTable(const std::vector<std::string> &a, const std::vector<std::string> &b)
      : n(a.size()), m(b.size()) {
    cost.assign(n + 1, std::vector<size_t>(m + 1, 0));
    for (size_t i = 0; i <= n; ++i) cost[i][0] = i;
    for (size_t j = 0; j <= m; ++j) cost[0][j] = j;
    for (size_t i = 1; i <= n; ++i) {
      for (size_t j = 1; j <= m; ++j) {
        const size_t sub = cost[i - 1][j - 1] + (a[i - 1] == b[j - 1] ? 0 : 1);
        cost[i][j] = std::min({sub, cost[i - 1][j] + 1, cost[i][j - 1] + 1});
      }
    }
  }
};

}  // namespace

const char *DiffOpName(DiffOp op) {
  switch (op) {
    case DiffOp::kEqual:      return "equal";
    case DiffOp::kSubstitute: return "substitute";
    case DiffOp::kInsert:     return "insert";
    case DiffOp::kDelete:     return "delete";
  }
  return "unknown";
}

std::vector<DiffSpan> DiffWords(const std::string &a, const std::string &b) {
  const std::vector<std::string> ta = BasicTokens(a);
  const std::vector<std::string> tb = BasicTokens(b);
  const EditTable table(ta, tb);

  std::vector<DiffSpan> out;
  size_t i = ta.size();
  size_t j = tb.size();
  while (i > 0 || j > 0) {
    if (i > 0 && j > 0) {
      const size_t sub = table.cost[i - 1][j - 1] + (ta[i - 1] == tb[j - 1] ? 0 : 1);
      if (table.cost[i][j] == sub) {
        DiffSpan s;
        s.op = ta[i - 1] == tb[j - 1] ? DiffOp::kEqual : DiffOp::kSubstitute;
        s.a = ta[i - 1];
        s.b = tb[j - 1];
        out.push_back(std::move(s));
        --i;
        --j;
        continue;
      }
    }
    // Prefer deletions before insertions on ties so the output reads in a
    // stable order regardless of which side is longer.
    if (i > 0 && table.cost[i][j] == table.cost[i - 1][j] + 1) {
      DiffSpan s;
      s.op = DiffOp::kDelete;
      s.a = ta[i - 1];
      out.push_back(std::move(s));
      --i;
    } else if (j > 0) {
      DiffSpan s;
      s.op = DiffOp::kInsert;
      s.b = tb[j - 1];
      out.push_back(std::move(s));
      --j;
    } else {
      break;
    }
  }
  std::reverse(out.begin(), out.end());
  return out;
}

bool TranscriptsDiffer(const std::string &a, const std::string &b) {
  return BasicTokens(a) != BasicTokens(b);
}

ErrorRate ComputeWer(const std::string &reference, const std::string &hypothesis) {
  ErrorRate r;
  const std::vector<DiffSpan> spans = DiffWords(reference, hypothesis);
  r.ref_words = BasicTokens(reference).size();
  for (const DiffSpan &s : spans) {
    switch (s.op) {
      case DiffOp::kSubstitute: ++r.substitutions; break;
      case DiffOp::kDelete:     ++r.deletions; break;
      case DiffOp::kInsert:     ++r.insertions; break;
      case DiffOp::kEqual:      break;
    }
  }
  return r;
}

ErrorRate ComputeCer(const std::string &reference, const std::string &hypothesis) {
  // Compare the normalised token streams rather than the raw strings, so
  // punctuation and casing differences between two decoders do not show up as
  // character errors.
  const std::string ref = Join(BasicTokens(reference));
  const std::string hyp = Join(BasicTokens(hypothesis));

  std::vector<std::string> ra, hb;
  ra.reserve(ref.size());
  hb.reserve(hyp.size());
  for (char c : ref) ra.push_back(std::string(1, c));
  for (char c : hyp) hb.push_back(std::string(1, c));

  const EditTable table(ra, hb);
  ErrorRate r;
  r.ref_words = ra.size();

  size_t i = ra.size();
  size_t j = hb.size();
  while (i > 0 || j > 0) {
    if (i > 0 && j > 0) {
      const size_t sub = table.cost[i - 1][j - 1] + (ra[i - 1] == hb[j - 1] ? 0 : 1);
      if (table.cost[i][j] == sub) {
        if (ra[i - 1] != hb[j - 1]) ++r.substitutions;
        --i;
        --j;
        continue;
      }
    }
    if (i > 0 && table.cost[i][j] == table.cost[i - 1][j] + 1) {
      ++r.deletions;
      --i;
    } else if (j > 0) {
      ++r.insertions;
      --j;
    } else {
      break;
    }
  }
  return r;
}

}  // namespace vcc
