#include "vcc/json.h"

#include <limits>

#include "vcc_test.h"

using namespace vcc;

VCC_TEST(json, writer_emits_a_flat_object) {
  JsonWriter w;
  w.BeginObject();
  w.Field("name", "guest_network_on");
  w.Field("code", 101);
  // 0.8127, not 0.8125: an exact binary tie would round to even and the
  // test would be asserting the platform's tie-breaking rule, not ours.
  w.Field("score", 0.8127, 3);
  w.Field("ok", true);
  w.End();
  VCC_CHECK_EQ(w.str(),
               std::string("{\"name\":\"guest_network_on\",\"code\":101,"
                           "\"score\":0.813,\"ok\":true}"));
}

VCC_TEST(json, writer_nests_arrays_and_objects) {
  JsonWriter w;
  w.BeginObject();
  w.Key("items").BeginArray();
  w.BeginObject().Field("a", 1).End();
  w.BeginObject().Field("a", 2).End();
  w.End();
  w.End();
  VCC_CHECK_EQ(w.str(), std::string("{\"items\":[{\"a\":1},{\"a\":2}]}"));
}

VCC_TEST(json, writer_escapes_control_characters) {
  JsonWriter w;
  w.String("a\"b\\c\nd\te");
  VCC_CHECK_EQ(w.str(), std::string("\"a\\\"b\\\\c\\nd\\te\""));
}

VCC_TEST(json, writer_passes_utf8_through) {
  // Command phrases stay English, but warnings and device names do not have to.
  // Written as explicit UTF-8 bytes rather than source-encoded characters, so
  // the test does not depend on how the compiler treats the file's encoding.
  // Adjacent literals keep each \x escape from swallowing the next character.
  const std::string vietnamese =
      "b\xE1\xBA\xAD" "t m\xE1\xBA\xA1" "ng kh\xC3\xA1" "ch";
  JsonWriter w;
  w.String(vietnamese);
  VCC_CHECK_EQ(w.str(), "\"" + vietnamese + "\"");
}

VCC_TEST(json, writer_trims_trailing_zeros) {
  JsonWriter w;
  w.BeginArray().Number(1.5, 6).Number(2.0, 6).Number(0.0, 6).End();
  VCC_CHECK_EQ(w.str(), std::string("[1.5,2,0]"));
}

VCC_TEST(json, writer_encodes_non_finite_as_null) {
  JsonWriter w;
  w.Number(std::numeric_limits<double>::infinity(), 3);
  VCC_CHECK_EQ(w.str(), std::string("null"));
}

VCC_TEST(json, reader_extracts_scalars) {
  JsonObject o;
  VCC_CHECK(o.Parse("{\"model\":\"zipformer\",\"threads\":4,"
                    "\"score\":2.5,\"bias\":true}"));
  VCC_CHECK_EQ(o.GetString("model"), std::string("zipformer"));
  VCC_CHECK_EQ(o.GetInt("threads", 0), 4);
  VCC_CHECK_NEAR(o.GetNumber("score", 0.0), 2.5, 1e-9);
  VCC_CHECK(o.GetBool("bias", false));
  VCC_CHECK(o.Has("model"));
  VCC_CHECK(!o.Has("nope"));
}

VCC_TEST(json, reader_decodes_escapes) {
  JsonObject o;
  VCC_CHECK(o.Parse("{\"text\":\"turn \\\"on\\\"\\nguest\"}"));
  VCC_CHECK_EQ(o.GetString("text"), std::string("turn \"on\"\nguest"));
}

VCC_TEST(json, reader_skips_nested_containers) {
  JsonObject o;
  VCC_CHECK(o.Parse("{\"a\":{\"deep\":1},\"b\":[1,2,{\"c\":3}],\"z\":9}"));
  VCC_CHECK_EQ(o.GetInt("z", 0), 9);
}

VCC_TEST(json, reader_rejects_non_objects) {
  JsonObject o;
  VCC_CHECK(!o.Parse("[1,2,3]"));
  VCC_CHECK(!o.Parse("nonsense"));
  VCC_CHECK(!o.Parse(""));
}

VCC_TEST(json, reader_handles_empty_object) {
  JsonObject o;
  VCC_CHECK(o.Parse("{}"));
  VCC_CHECK_EQ(o.GetInt("anything", 42), 42);
}

VCC_TEST(json, roundtrip_through_the_writer) {
  JsonWriter w;
  w.BeginObject().Field("text", "turn off guest network").Field("n", 3).End();
  JsonObject o;
  VCC_CHECK(o.Parse(w.str()));
  VCC_CHECK_EQ(o.GetString("text"), std::string("turn off guest network"));
  VCC_CHECK_EQ(o.GetInt("n", 0), 3);
}
