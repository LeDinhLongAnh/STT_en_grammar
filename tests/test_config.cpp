#include "vcc/config.h"

#include <cstdio>

#include "vcc/core.h"
#include "vcc_test.h"

using namespace vcc;

namespace {

// Writes an ini to a temp file and removes it again.
struct TempIni {
  std::string path;
  explicit TempIni(const std::string &body) {
    path = PathJoin(".", "vcc_test_config.tmp.ini");
    WriteFile(path, body);
  }
  ~TempIni() { std::remove(path.c_str()); }
};

}  // namespace

VCC_TEST(config, sections_become_key_prefixes) {
  TempIni f("[asr]\nnum_threads = 3\n\n[match]\naccept=0.8\n");
  Config c;
  VCC_CHECK(c.LoadFile(f.path));
  VCC_CHECK_EQ(c.GetInt("asr.num_threads", 1), 3);
  VCC_CHECK_NEAR(c.GetFloat("match.accept", 0.0f), 0.8, 1e-6);
}

VCC_TEST(config, comments_and_blank_lines_are_ignored) {
  TempIni f("; a comment\n\n[asr]\n# another\nnum_threads = 4  ; trailing\n");
  Config c;
  VCC_CHECK(c.LoadFile(f.path));
  VCC_CHECK_EQ(c.GetInt("asr.num_threads", 1), 4);
}

VCC_TEST(config, malformed_lines_are_reported_not_fatal) {
  TempIni f("[asr]\nthis line has no equals sign\nnum_threads = 2\n");
  Config c;
  std::vector<std::string> warnings;
  VCC_CHECK(c.LoadFile(f.path, &warnings));
  VCC_CHECK_EQ(warnings.size(), size_t(1));
  VCC_CHECK_EQ(c.GetInt("asr.num_threads", 0), 2);
}

VCC_TEST(config, missing_file_fails_cleanly) {
  Config c;
  VCC_CHECK(!c.LoadFile("definitely-not-here.ini"));
}

VCC_TEST(config, keys_are_case_insensitive) {
  TempIni f("[ASR]\nNum_Threads = 5\n");
  Config c;
  VCC_CHECK(c.LoadFile(f.path));
  VCC_CHECK_EQ(c.GetInt("asr.num_threads", 0), 5);
}

VCC_TEST(config, bool_spellings) {
  TempIni f("[a]\nx=true\ny=off\nz=1\nw=no\n");
  Config c;
  VCC_CHECK(c.LoadFile(f.path));
  VCC_CHECK(c.GetBool("a.x", false));
  VCC_CHECK(!c.GetBool("a.y", true));
  VCC_CHECK(c.GetBool("a.z", false));
  VCC_CHECK(!c.GetBool("a.w", true));
}

VCC_TEST(config, defaults_apply_to_unset_keys) {
  TempIni f("[asr]\nmodel =\n");
  Config c;
  VCC_CHECK(c.LoadFile(f.path));
  // An explicitly empty value stays empty: "no model configured" is a real
  // setting, distinct from "the key is absent".
  VCC_CHECK_EQ(c.GetString("asr.model", "fallback"), std::string(""));
  VCC_CHECK_EQ(c.GetInt("asr.nothing_here", 7), 7);
  VCC_CHECK_EQ(c.GetString("asr.nothing_here", "fallback"), std::string("fallback"));
}

VCC_TEST(config, bad_number_falls_back_to_default) {
  TempIni f("[asr]\nnum_threads = lots\n");
  Config c;
  VCC_CHECK(c.LoadFile(f.path));
  VCC_CHECK_EQ(c.GetInt("asr.num_threads", 4), 4);
}

VCC_TEST(config, command_line_override_wins) {
  TempIni f("[asr]\nnum_threads = 2\n");
  Config c;
  VCC_CHECK(c.LoadFile(f.path));
  VCC_CHECK(c.SetFromAssignment("asr.num_threads=8"));
  VCC_CHECK_EQ(c.GetInt("asr.num_threads", 0), 8);
  VCC_CHECK(!c.SetFromAssignment("no-equals-sign"));
}

VCC_TEST(config, relative_paths_are_resolved_against_the_root) {
  TempIni f("[paths]\nmodels_dir = models\nabs = /tmp/elsewhere\n");
  Config c;
  VCC_CHECK(c.LoadFile(f.path));
  VCC_CHECK_EQ(c.GetPath("paths.models_dir", "/opt/vcc"),
               std::string("/opt/vcc/models"));
  VCC_CHECK_EQ(c.GetPath("paths.abs", "/opt/vcc"), std::string("/tmp/elsewhere"));
}
