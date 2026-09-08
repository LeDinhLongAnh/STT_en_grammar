// The hotword list is the project's payload, and its wire format has a trap in
// it (see include/vcc/hotwords.h). These cases pin the format, because getting
// it subtly wrong makes biasing silently do nothing.
#include "vcc/hotwords.h"

#include "vcc/core.h"
#include "vcc_test.h"

using namespace vcc;

VCC_TEST(hotwords, parses_one_phrase_per_line) {
  HotwordList h;
  h.LoadText("GUEST NETWORK\nBANDWIDTH\n# a comment\n\nBLOCK INTERNET\n");
  VCC_CHECK_EQ(h.size(), size_t(3));
  VCC_CHECK_EQ(h.entries()[0].phrase, std::string("GUEST NETWORK"));
  VCC_CHECK_EQ(h.entries()[2].phrase, std::string("BLOCK INTERNET"));
}

VCC_TEST(hotwords, collapses_internal_whitespace) {
  HotwordList h;
  h.LoadText("  GUEST    NETWORK  \n");
  VCC_CHECK_EQ(h.entries()[0].phrase, std::string("GUEST NETWORK"));
}

VCC_TEST(hotwords, one_boost_applies_to_every_phrase) {
  // The design decision: sherpa-onnx supports a per-phrase score and this
  // project deliberately does not use it. One number is tunable against a
  // corpus; thirty are not.
  HotwordList h;
  h.LoadText("guest network\nbandwidth\n");
  VCC_CHECK_EQ(h.Serialize(2.5f),
               std::string("GUEST NETWORK :2.50/BANDWIDTH :2.50"));
}

VCC_TEST(hotwords, serialises_slash_separated_for_the_per_stream_api) {
  // THE FORMAT THAT MATTERS: sherpa-onnx's per-stream hotwords argument splits
  // on '/', not on newline. A newline-joined list would arrive as one giant
  // bogus hotword and bias nothing.
  HotwordList h;
  h.LoadText("guest network\nbandwidth\n");
  const std::string wire = h.Serialize(2.0f);
  VCC_CHECK_EQ(wire, std::string("GUEST NETWORK :2.00/BANDWIDTH :2.00"));
}

VCC_TEST(hotwords, serialisation_uppercases) {
  // The English BPE inventories these models ship with are uppercase; a
  // lowercase hotword tokenises to something the decoder never emits.
  HotwordList h;
  h.LoadText("guest network\n");
  VCC_CHECK_EQ(h.Serialize(2.0f), std::string("GUEST NETWORK :2.00"));
}

VCC_TEST(hotwords, a_legacy_per_phrase_score_is_ignored_with_a_warning) {
  // An older file must keep working, and the user must find out that their
  // number had no effect rather than wondering why.
  HotwordList h;
  std::vector<std::string> warnings;
  h.LoadText("GUEST NETWORK :6.0\nBANDWIDTH\n", &warnings);
  VCC_CHECK_EQ(h.size(), size_t(2));
  VCC_CHECK_EQ(h.entries()[0].phrase, std::string("GUEST NETWORK"));
  VCC_CHECK_EQ(warnings.size(), size_t(1));
  // Both phrases get the global boost, not 6.0.
  VCC_CHECK_EQ(h.Serialize(2.0f),
               std::string("GUEST NETWORK :2.00/BANDWIDTH :2.00"));
}

VCC_TEST(hotwords, a_colon_that_is_not_a_score_stays_in_the_phrase) {
  HotwordList h;
  h.LoadText("GUEST : NETWORK\n");
  VCC_CHECK_EQ(h.entries()[0].phrase, std::string("GUEST : NETWORK"));
}

VCC_TEST(hotwords, a_phrase_containing_a_slash_is_dropped_with_a_warning) {
  // '/' is the record separator, so such a phrase would become two hotwords.
  // Dropping it loudly beats corrupting the graph quietly.
  HotwordList h;
  h.LoadText("GUEST/NETWORK\nBANDWIDTH\n");
  std::vector<std::string> warnings;
  const std::string wire = h.Serialize(2.0f, &warnings);
  VCC_CHECK_EQ(wire, std::string("BANDWIDTH :2.00"));
  VCC_CHECK_EQ(warnings.size(), size_t(1));
}

VCC_TEST(hotwords, an_empty_list_serialises_to_nothing) {
  HotwordList h;
  VCC_CHECK(h.empty());
  VCC_CHECK_EQ(h.Serialize(2.0f), std::string(""));
}

VCC_TEST(hotwords, empty_serialisation_is_the_unbiased_signal) {
  // Pipeline::Process() treats an empty string as "skip the second decode", so
  // a list of nothing but comments must produce exactly that.
  HotwordList h;
  h.LoadText("# only comments\n\n   \n");
  VCC_CHECK(h.empty());
  VCC_CHECK(h.Serialize(2.0f).empty());
}

VCC_TEST(hotwords, round_trips_through_text) {
  HotwordList a;
  a.LoadText("GUEST NETWORK\nBANDWIDTH\n");
  HotwordList b;
  b.LoadText(a.ToText());
  VCC_CHECK_EQ(b.size(), a.size());
  VCC_CHECK_EQ(b.Serialize(2.0f), a.Serialize(2.0f));
}

VCC_TEST(hotwords, round_trip_drops_a_legacy_score) {
  // Saving from the dashboard normalises the file: the ignored suffix goes away
  // instead of lingering to confuse the next reader.
  HotwordList a;
  a.LoadText("GUEST NETWORK :6.0\n");
  VCC_CHECK_EQ(a.ToText(), std::string("GUEST NETWORK\n"));
}

VCC_TEST(hotwords, max_words_reports_the_longest_phrase) {
  HotwordList h;
  h.LoadText("A\nA B C\nA B\n");
  // A hotword longer than the utterances you expect will never fire, so this is
  // worth being able to check.
  VCC_CHECK_EQ(h.max_words(), size_t(3));
}

VCC_TEST(hotwords, add_normalises_whitespace) {
  HotwordList h;
  h.Add("  guest   network  ");
  VCC_CHECK_EQ(h.size(), size_t(1));
  VCC_CHECK_EQ(h.entries()[0].phrase, std::string("guest network"));
  h.Add("   ");
  VCC_CHECK_EQ(h.size(), size_t(1));  // nothing to add
}
