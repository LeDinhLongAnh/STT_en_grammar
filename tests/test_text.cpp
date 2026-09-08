#include "vcc/text.h"

#include "vcc/core.h"
#include "vcc_test.h"

using namespace vcc;

VCC_TEST(text, basic_tokens_strip_punctuation) {
  VCC_CHECK_EQ(Join(BasicTokens("Turn ON the Guest-Network, please!")),
               std::string("turn on the guest network please"));
}

VCC_TEST(text, contractions_are_glued) {
  VCC_CHECK_EQ(Join(BasicTokens("what's the wifi password?")),
               std::string("whats the wifi password"));
}

VCC_TEST(text, digits_survive_tokenisation) {
  VCC_CHECK_EQ(Join(BasicTokens("limit to 50")), std::string("limit to 50"));
}

VCC_TEST(rewrites, joins_split_words) {
  const RewriteTable t = RewriteTable::Default();
  VCC_CHECK_EQ(t.Apply("turn on wi fi"), std::string("turn on wifi"));
  VCC_CHECK_EQ(t.Apply("check band width"), std::string("check bandwidth"));
  VCC_CHECK_EQ(t.Apply("open you tube"), std::string("open youtube"));
}

VCC_TEST(rewrites, repairs_soft_final_consonants) {
  const RewriteTable t = RewriteTable::Default();
  VCC_CHECK_EQ(t.Apply("turn on gues network"), std::string("turn on guest network"));
  VCC_CHECK_EQ(t.Apply("gas network status"), std::string("guest network status"));
}

VCC_TEST(rewrites, reports_which_rules_fired) {
  const RewriteTable t = RewriteTable::Default();
  std::vector<RewriteHit> hits;
  const std::string out = t.Apply("gues net work", &hits);
  VCC_CHECK_EQ(out, std::string("guest network"));
  VCC_CHECK_EQ(hits.size(), size_t(2));
  // A rule that never fires should be visible as absent, which is what makes
  // pruning the table possible.
  bool saw_guest = false;
  for (const RewriteHit &h : hits) {
    if (h.from == "gues" && h.to == "guest") saw_guest = true;
  }
  VCC_CHECK(saw_guest);
}

VCC_TEST(rewrites, leaves_unrelated_text_alone) {
  const RewriteTable t = RewriteTable::Default();
  const std::string in = "the weather is nice today";
  VCC_CHECK_EQ(t.Apply(in), in);
}

VCC_TEST(rewrites, parses_a_file_body) {
  RewriteTable t;
  std::vector<std::string> warnings;
  t.LoadText("# a comment\n[section]\nfoo bar => baz\n  spaced  =>  out  \n", &warnings);
  VCC_CHECK_EQ(t.size(), size_t(2));
  VCC_CHECK(warnings.empty());
  VCC_CHECK_EQ(t.Apply("say foo bar now"), std::string("say baz now"));
  VCC_CHECK_EQ(t.Apply("spaced"), std::string("out"));
}

VCC_TEST(rewrites, malformed_lines_are_reported_not_fatal) {
  RewriteTable t;
  std::vector<std::string> warnings;
  t.LoadText("this line has no arrow\ngood => fine\n", &warnings);
  VCC_CHECK_EQ(t.size(), size_t(1));
  VCC_CHECK_EQ(warnings.size(), size_t(1));
}

VCC_TEST(rewrites, empty_replacement_deletes) {
  RewriteTable t;
  t.LoadText("um =>\n");
  VCC_CHECK_EQ(t.Apply("um turn on wifi"), std::string("turn on wifi"));
}

VCC_TEST(rewrites, longest_pattern_wins) {
  RewriteTable t;
  // "guest network" must beat the single-word "network" rule.
  t.LoadText("network => net\nguest network => gn\n");
  VCC_CHECK_EQ(t.Apply("guest network"), std::string("gn"));
}

VCC_TEST(rewrites, a_cyclic_table_terminates) {
  RewriteTable t;
  // Documented as unsupported, but it must not hang: application is capped.
  t.LoadText("a => b\nb => a\n");
  const std::string out = t.Apply("a");
  VCC_CHECK(out == "a" || out == "b");
}

VCC_TEST(rewrites, identity_rules_are_dropped_at_load) {
  RewriteTable t;
  t.LoadText("same => same\nreal => thing\n");
  VCC_CHECK_EQ(t.size(), size_t(1));
}

VCC_TEST(rewrites, round_trips_through_text) {
  RewriteTable a;
  a.LoadText("wi fi => wifi\ngues => guest\n");
  RewriteTable b;
  b.LoadText(a.ToText());
  VCC_CHECK_EQ(b.size(), a.size());
  VCC_CHECK_EQ(b.Apply("wi fi gues"), std::string("wifi guest"));
}

VCC_TEST(rewrites, unchanged_text_is_returned_verbatim) {
  const RewriteTable t = RewriteTable::Default();
  // The common path. Casing and punctuation must survive untouched, because
  // this string is the filter's product and something downstream consumes it.
  const std::string in = "After early nightfall, the yellow lamps.";
  VCC_CHECK_EQ(t.Apply(in), in);
}

VCC_TEST(rewrites, all_caps_input_stays_all_caps_when_a_rule_fires) {
  // The zipformer models emit uppercase. A rule firing must not silently
  // lowercase the whole transcript.
  const RewriteTable t = RewriteTable::Default();
  VCC_CHECK_EQ(t.Apply("TURN ON GUES NETWORK"), std::string("TURN ON GUEST NETWORK"));
}

VCC_TEST(rewrites, lowercase_input_stays_lowercase_when_a_rule_fires) {
  const RewriteTable t = RewriteTable::Default();
  VCC_CHECK_EQ(t.Apply("turn on gues network"), std::string("turn on guest network"));
}
