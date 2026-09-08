// WER is the number the whole project is judged on, so these cases pin its
// arithmetic against hand-worked examples rather than against itself.
#include "vcc/diff.h"

#include "vcc_test.h"

using namespace vcc;

namespace {

size_t CountOp(const std::vector<DiffSpan> &spans, DiffOp op) {
  size_t n = 0;
  for (const DiffSpan &s : spans) {
    if (s.op == op) ++n;
  }
  return n;
}

}  // namespace

VCC_TEST(diff, identical_text_is_all_equal) {
  const std::vector<DiffSpan> d = DiffWords("turn on guest network", "turn on guest network");
  VCC_CHECK_EQ(d.size(), size_t(4));
  VCC_CHECK_EQ(CountOp(d, DiffOp::kEqual), size_t(4));
  VCC_CHECK(!TranscriptsDiffer("turn on guest network", "turn on guest network"));
}

VCC_TEST(diff, punctuation_and_case_are_not_differences) {
  VCC_CHECK(!TranscriptsDiffer("TURN ON GUEST NETWORK.", "turn on guest network"));
}

VCC_TEST(diff, finds_a_single_substitution) {
  const std::vector<DiffSpan> d = DiffWords("turn on gas network", "turn on guest network");
  VCC_CHECK_EQ(CountOp(d, DiffOp::kSubstitute), size_t(1));
  VCC_CHECK_EQ(CountOp(d, DiffOp::kEqual), size_t(3));
  for (const DiffSpan &s : d) {
    if (s.op != DiffOp::kSubstitute) continue;
    VCC_CHECK_EQ(s.a, std::string("gas"));
    VCC_CHECK_EQ(s.b, std::string("guest"));
  }
}

VCC_TEST(diff, finds_insertions_and_deletions) {
  const std::vector<DiffSpan> ins = DiffWords("turn on wifi", "turn on the wifi");
  VCC_CHECK_EQ(CountOp(ins, DiffOp::kInsert), size_t(1));
  const std::vector<DiffSpan> del = DiffWords("turn on the wifi", "turn on wifi");
  VCC_CHECK_EQ(CountOp(del, DiffOp::kDelete), size_t(1));
}

VCC_TEST(diff, spans_are_in_reading_order) {
  const std::vector<DiffSpan> d = DiffWords("a b c", "a x c");
  VCC_CHECK_EQ(d.size(), size_t(3));
  VCC_CHECK_EQ(d[0].op, DiffOp::kEqual);
  VCC_CHECK_EQ(d[1].op, DiffOp::kSubstitute);
  VCC_CHECK_EQ(d[2].op, DiffOp::kEqual);
}

VCC_TEST(diff, handles_empty_sides) {
  VCC_CHECK_EQ(CountOp(DiffWords("", "hello world"), DiffOp::kInsert), size_t(2));
  VCC_CHECK_EQ(CountOp(DiffWords("hello world", ""), DiffOp::kDelete), size_t(2));
  VCC_CHECK(DiffWords("", "").empty());
}

VCC_TEST(wer, perfect_transcript_is_zero) {
  const ErrorRate r = ComputeWer("turn on guest network", "turn on guest network");
  VCC_CHECK_EQ(r.errors(), size_t(0));
  VCC_CHECK_NEAR(r.wer(), 0.0, 1e-9);
  VCC_CHECK_EQ(r.ref_words, size_t(4));
}

VCC_TEST(wer, one_substitution_in_four_words) {
  const ErrorRate r = ComputeWer("turn on guest network", "turn on gas network");
  VCC_CHECK_EQ(r.substitutions, size_t(1));
  VCC_CHECK_EQ(r.deletions, size_t(0));
  VCC_CHECK_EQ(r.insertions, size_t(0));
  VCC_CHECK_NEAR(r.wer(), 0.25, 1e-9);
}

VCC_TEST(wer, counts_all_three_error_kinds) {
  // ref: the quick brown fox
  // hyp: the quick red fox jumps      -> 1 sub (brown/red), 1 ins (jumps)
  const ErrorRate r = ComputeWer("the quick brown fox", "the quick red fox jumps");
  VCC_CHECK_EQ(r.substitutions, size_t(1));
  VCC_CHECK_EQ(r.insertions, size_t(1));
  VCC_CHECK_EQ(r.deletions, size_t(0));
  VCC_CHECK_NEAR(r.wer(), 0.5, 1e-9);
}

VCC_TEST(wer, can_exceed_one_hundred_percent) {
  // A rambling hypothesis genuinely has WER > 1. Clamping it would hide the
  // failure mode where biasing makes the decoder hallucinate extra words.
  const ErrorRate r = ComputeWer("wifi", "turn on the guest network now please");
  VCC_CHECK(r.wer() > 1.0);
}

VCC_TEST(wer, empty_reference_is_handled) {
  VCC_CHECK_NEAR(ComputeWer("", "").wer(), 0.0, 1e-9);
  VCC_CHECK_NEAR(ComputeWer("", "something").wer(), 1.0, 1e-9);
}

VCC_TEST(wer, empty_hypothesis_is_total_loss) {
  const ErrorRate r = ComputeWer("turn on guest network", "");
  VCC_CHECK_EQ(r.deletions, size_t(4));
  VCC_CHECK_NEAR(r.wer(), 1.0, 1e-9);
}

VCC_TEST(cer, counts_characters_not_words) {
  // "gues" vs "guest" is one whole word wrong but only one character wrong.
  // The two metrics disagreeing that way is the signal that says "the ending
  // was swallowed" rather than "a different word was heard".
  const ErrorRate wer = ComputeWer("guest", "gues");
  const ErrorRate cer = ComputeCer("guest", "gues");
  VCC_CHECK_NEAR(wer.wer(), 1.0, 1e-9);
  VCC_CHECK_NEAR(cer.wer(), 0.2, 1e-9);
}

VCC_TEST(cer, ignores_punctuation_between_decoders) {
  // One model emits punctuation, another does not; that must not read as error.
  VCC_CHECK_NEAR(ComputeCer("Turn on guest network.", "turn on guest network").wer(),
                 0.0, 1e-9);
}

VCC_TEST(wer, accumulator_pools_counts_rather_than_averaging_rates) {
  // A 1-error 2-word clip and a 1-error 20-word clip pool to 2/22, not to the
  // mean of 50% and 5%. Averaging per-clip rates would let a two-word clip
  // dominate the corpus.
  ErrorRateAccumulator acc;
  acc.Add(ComputeWer("turn on", "turn off"));
  acc.Add(ComputeWer(
      "one two three four five six seven eight nine ten "
      "eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty",
      "one two three four five six seven eight nine ten "
      "eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen zero"));
  VCC_CHECK_EQ(acc.clips, size_t(2));
  VCC_CHECK_EQ(acc.total.ref_words, size_t(22));
  VCC_CHECK_EQ(acc.total.errors(), size_t(2));
  VCC_CHECK_NEAR(acc.wer(), 2.0 / 22.0, 1e-9);
}
