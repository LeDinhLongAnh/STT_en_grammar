// Model discovery is filename sniffing, and filename conventions are exactly
// the kind of thing that drifts between sherpa-onnx releases. These cases pin
// the layouts we claim to support, using stub files in place of real weights.
#include "vcc/models.h"

#include <cstdio>

#include "vcc/core.h"
#include "vcc_test.h"

#ifdef _WIN32
#include <direct.h>
#else
#include <sys/stat.h>
#include <unistd.h>
#endif

using namespace vcc;

namespace {

void MakeDir(const std::string &p) {
#ifdef _WIN32
  _mkdir(p.c_str());
#else
  mkdir(p.c_str(), 0755);
#endif
}

void RemoveDir(const std::string &p) {
#ifdef _WIN32
  _rmdir(p.c_str());
#else
  rmdir(p.c_str());
#endif
}

struct TempTree {
  std::string root;
  std::vector<std::string> files;
  std::vector<std::string> dirs;

  TempTree() {
    root = PathJoin(".", "vcc_test_models.tmp");
    MakeDir(root);
    dirs.push_back(root);
  }
  ~TempTree() {
    for (auto it = files.rbegin(); it != files.rend(); ++it) std::remove(it->c_str());
    for (auto it = dirs.rbegin(); it != dirs.rend(); ++it) RemoveDir(*it);
  }

  void Model(const std::string &name, const std::vector<std::string> &members) {
    const std::string dir = PathJoin(root, name);
    MakeDir(dir);
    dirs.push_back(dir);
    for (const std::string &m : members) {
      const std::string path = PathJoin(dir, m);
      WriteFile(path, std::string(16, 'x'));
      files.push_back(path);
    }
  }
};

}  // namespace

VCC_TEST(models, detects_an_offline_transducer_with_biasing) {
  TempTree t;
  t.Model("sherpa-onnx-zipformer-small-en-2023-06-26",
          {"encoder-epoch-99-avg-1.int8.onnx", "decoder-epoch-99-avg-1.int8.onnx",
           "joiner-epoch-99-avg-1.int8.onnx", "tokens.txt", "bpe.model", "bpe.vocab"});

  ModelRegistry reg;
  reg.Scan(t.root);
  VCC_CHECK_EQ(reg.models().size(), size_t(1));

  const ModelProfile &m = reg.models()[0];
  VCC_CHECK_EQ(std::string(ModelFamilyName(m.family)), std::string("transducer"));
  VCC_CHECK_EQ(std::string(PrecisionName(m.precision)), std::string("int8"));
  VCC_CHECK(m.supports_hotwords);
  VCC_CHECK(m.hotwords_blocker.empty());
  VCC_CHECK(EndsWith(m.encoder, "encoder-epoch-99-avg-1.int8.onnx"));
  VCC_CHECK(EndsWith(m.joiner, "joiner-epoch-99-avg-1.int8.onnx"));
}

VCC_TEST(models, missing_bpe_vocab_blocks_biasing_with_an_explanation) {
  TempTree t;
  t.Model("sherpa-onnx-zipformer-small-en-2023-06-26",
          {"encoder-epoch-99-avg-1.int8.onnx", "decoder-epoch-99-avg-1.int8.onnx",
           "joiner-epoch-99-avg-1.int8.onnx", "tokens.txt"});

  ModelRegistry reg;
  reg.Scan(t.root);
  VCC_CHECK_EQ(reg.models().size(), size_t(1));
  VCC_CHECK(!reg.models()[0].supports_hotwords);
  VCC_CHECK(!reg.models()[0].hotwords_blocker.empty());
}

VCC_TEST(models, both_precisions_are_offered_when_both_exist) {
  TempTree t;
  t.Model("zipformer-en",
          {"encoder.int8.onnx", "decoder.int8.onnx", "joiner.int8.onnx",
           "encoder.onnx", "decoder.onnx", "joiner.onnx", "tokens.txt", "bpe.vocab"});
  ModelRegistry reg;
  reg.Scan(t.root);
  VCC_CHECK_EQ(reg.models().size(), size_t(2));
  // int8 is what we want by default on a Cortex-A55.
  VCC_CHECK_EQ(std::string(PrecisionName(reg.PickDefault()->precision)),
               std::string("int8"));
  VCC_CHECK(reg.Resolve("zipformer-en", "fp32") != nullptr);
  VCC_CHECK_EQ(reg.Resolve("zipformer-en", "fp32")->id,
               std::string("zipformer-en@fp32"));
}

VCC_TEST(models, detects_whisper) {
  TempTree t;
  t.Model("sherpa-onnx-whisper-base.en",
          {"base.en-encoder.int8.onnx", "base.en-decoder.int8.onnx",
           "base.en-tokens.txt"});
  ModelRegistry reg;
  reg.Scan(t.root);
  VCC_CHECK_EQ(reg.models().size(), size_t(1));
  VCC_CHECK_EQ(std::string(ModelFamilyName(reg.models()[0].family)),
               std::string("whisper"));
  // Whisper has no biasing hook in sherpa-onnx; the UI must be able to say so.
  VCC_CHECK(!reg.models()[0].supports_hotwords);
}

VCC_TEST(models, detects_moonshine_with_a_merged_decoder) {
  TempTree t;
  t.Model("sherpa-onnx-moonshine-tiny-en-quantized-2026-02-27",
          {"encoder_model.ort", "decoder_model_merged.ort", "tokens.txt"});
  ModelRegistry reg;
  reg.Scan(t.root);
  VCC_CHECK_EQ(reg.models().size(), size_t(1));
  VCC_CHECK_EQ(std::string(ModelFamilyName(reg.models()[0].family)),
               std::string("moonshine"));
  VCC_CHECK(!reg.models()[0].merged_decoder.empty());
}

VCC_TEST(models, detects_moonshine_with_split_decoders) {
  TempTree t;
  t.Model("sherpa-onnx-moonshine-tiny-en-int8",
          {"preprocess.onnx", "encode.int8.onnx", "uncached_decode.int8.onnx",
           "cached_decode.int8.onnx", "tokens.txt"});
  ModelRegistry reg;
  reg.Scan(t.root);
  VCC_CHECK_EQ(reg.models().size(), size_t(1));
  const ModelProfile &m = reg.models()[0];
  VCC_CHECK(!m.uncached_decoder.empty());
  VCC_CHECK(!m.cached_decoder.empty());
  // "uncached_decode" must not be mistaken for the plain "cached_decode".
  VCC_CHECK(m.cached_decoder.find("uncached") == std::string::npos);
}

VCC_TEST(models, detects_a_streaming_transducer_from_the_chunk_geometry) {
  TempTree t;
  t.Model("sherpa-onnx-streaming-zipformer-en-2023-06-26",
          {"encoder-epoch-99-avg-1-chunk-16-left-128.int8.onnx",
           "decoder-epoch-99-avg-1-chunk-16-left-128.int8.onnx",
           "joiner-epoch-99-avg-1-chunk-16-left-128.int8.onnx", "tokens.txt",
           "bpe.vocab"});
  ModelRegistry reg;
  reg.Scan(t.root);
  VCC_CHECK_EQ(reg.models().size(), size_t(1));
  VCC_CHECK_EQ(std::string(ModelFamilyName(reg.models()[0].family)),
               std::string("online-transducer"));
  // Biasing is a decoder property, so a streaming transducer has it too.
  VCC_CHECK(reg.models()[0].supports_hotwords);
}

VCC_TEST(models, detects_a_streaming_transducer_named_only_by_its_directory) {
  // The 2023-02-21 export does not put the chunk geometry in the filenames --
  // "encoder-epoch-99-avg-1.int8.onnx" is indistinguishable from the offline
  // model's. Only the directory name says streaming, so that tell has to count.
  TempTree t;
  t.Model("sherpa-onnx-streaming-zipformer-en-2023-02-21",
          {"encoder-epoch-99-avg-1.int8.onnx", "decoder-epoch-99-avg-1.int8.onnx",
           "joiner-epoch-99-avg-1.int8.onnx", "tokens.txt", "bpe.vocab"});
  ModelRegistry reg;
  reg.Scan(t.root);
  VCC_CHECK_EQ(reg.models().size(), size_t(1));
  VCC_CHECK_EQ(std::string(ModelFamilyName(reg.models()[0].family)),
               std::string("online-transducer"));
}

VCC_TEST(models, a_streaming_model_never_becomes_the_default) {
  // The device decodes one whole phrase per clip, so streaming buys nothing and
  // costs right context. Even when it is the smaller of the two it must lose,
  // because picking it would silently switch the decode path.
  TempTree t;
  t.Model("sherpa-onnx-streaming-zipformer-en-2023-02-21",
          {"encoder-epoch-99-avg-1.int8.onnx", "decoder-epoch-99-avg-1.int8.onnx",
           "joiner-epoch-99-avg-1.int8.onnx", "tokens.txt", "bpe.vocab"});
  t.Model("zipformer-small-en", {"encoder.int8.onnx", "decoder.int8.onnx",
                                 "joiner.int8.onnx", "tokens.txt", "bpe.vocab"});
  // Make the offline one the *larger*, so size cannot be what decides it.
  WriteFile(PathJoin(PathJoin(t.root, "zipformer-small-en"), "encoder.int8.onnx"),
            std::string(65536, 'x'));

  ModelRegistry reg;
  reg.Scan(t.root);
  VCC_CHECK_EQ(reg.models().size(), size_t(2));
  VCC_CHECK_EQ(reg.PickDefault()->id, std::string("zipformer-small-en"));
  VCC_CHECK_EQ(std::string(ModelFamilyName(reg.PickDefault()->family)),
               std::string("transducer"));
  // ...but it is still selectable by name.
  VCC_CHECK(reg.Resolve("2023-02-21", "auto") != nullptr);
}

VCC_TEST(models, a_non_recogniser_directory_is_ignored) {
  // The models tree can hold things that are not offline recognisers. Those
  // must not appear in the registry, and must not be reported as broken.
  TempTree t;
  t.Model("silero-vad", {"silero_vad.onnx"});
  ModelRegistry reg;
  std::vector<std::string> problems;
  reg.Scan(t.root, &problems);
  VCC_CHECK(reg.models().empty());
  VCC_CHECK(problems.empty());
}

VCC_TEST(models, the_default_is_the_smallest_biasing_capable_model) {
  // The ordering IS the default-model policy. Adding a second capable model
  // must not change the default by alphabetical accident: on a 200 MB target
  // the smaller one wins.
  TempTree t;
  t.Model("zipformer-en", {"encoder.int8.onnx", "decoder.int8.onnx",
                           "joiner.int8.onnx", "tokens.txt", "bpe.vocab"});
  t.Model("zipformer-small-en", {"encoder.int8.onnx", "decoder.int8.onnx",
                                 "joiner.int8.onnx", "tokens.txt", "bpe.vocab"});
  // Make "zipformer-en" the larger of the two, as it is in reality.
  WriteFile(PathJoin(PathJoin(t.root, "zipformer-en"), "encoder.int8.onnx"),
            std::string(4096, 'x'));

  ModelRegistry reg;
  reg.Scan(t.root);
  VCC_CHECK_EQ(reg.models().size(), size_t(2));
  VCC_CHECK(reg.PickDefault() != nullptr);
  VCC_CHECK_EQ(reg.PickDefault()->id, std::string("zipformer-small-en"));
}

VCC_TEST(models, a_biasing_capable_model_outranks_a_smaller_incapable_one) {
  // Capability beats size: a model we cannot bias turns the feature off, which
  // is worse than a few extra megabytes.
  TempTree t;
  t.Model("tiny-moonshine", {"encoder_model.ort", "decoder_model_merged.ort",
                             "tokens.txt"});
  t.Model("zipformer-small-en", {"encoder.int8.onnx", "decoder.int8.onnx",
                                 "joiner.int8.onnx", "tokens.txt", "bpe.vocab"});
  WriteFile(PathJoin(PathJoin(t.root, "zipformer-small-en"), "encoder.int8.onnx"),
            std::string(8192, 'x'));

  ModelRegistry reg;
  reg.Scan(t.root);
  VCC_CHECK(reg.PickDefault() != nullptr);
  VCC_CHECK_EQ(reg.PickDefault()->id, std::string("zipformer-small-en"));
  VCC_CHECK(reg.PickDefault()->supports_hotwords);
}

VCC_TEST(models, resolve_prefers_exact_ids_over_substrings) {
  TempTree t;
  t.Model("zipformer-en", {"encoder.int8.onnx", "decoder.int8.onnx",
                           "joiner.int8.onnx", "tokens.txt", "bpe.vocab"});
  t.Model("zipformer-en-large", {"encoder.int8.onnx", "decoder.int8.onnx",
                                 "joiner.int8.onnx", "tokens.txt", "bpe.vocab"});
  ModelRegistry reg;
  reg.Scan(t.root);
  VCC_CHECK_EQ(reg.Resolve("zipformer-en", "auto")->id, std::string("zipformer-en"));
  VCC_CHECK_EQ(reg.Resolve("large", "auto")->id, std::string("zipformer-en-large"));
  VCC_CHECK(reg.Resolve("does-not-exist", "auto") == nullptr);
}

VCC_TEST(models, empty_directory_is_not_an_error) {
  TempTree t;
  ModelRegistry reg;
  std::vector<std::string> problems;
  reg.Scan(t.root, &problems);
  VCC_CHECK(reg.models().empty());
  VCC_CHECK(reg.PickDefault() == nullptr);
}

VCC_TEST(models, missing_directory_is_reported) {
  ModelRegistry reg;
  std::vector<std::string> problems;
  reg.Scan("./definitely-not-a-models-dir", &problems);
  VCC_CHECK_EQ(problems.size(), size_t(1));
}
