// Discovers usable ASR models by looking at what is actually on disk.
//
// The alternative -- a hand-maintained registry file -- goes stale the moment
// somebody drops a new model directory in. Sniffing filenames means
// `download_models.sh --only <anything>` is immediately visible to the
// dashboard with no second edit.
#pragma once

#include <string>
#include <vector>

namespace vcc {

// Which sherpa-onnx recogniser a model directory loads under.
//
// Only the two *transducer* families can be biased. That is a property of the
// DECODER, not of the encoder architecture: biasing is a prefix-tree boost
// applied to the beam as tokens are emitted, and only a transducer emits tokens
// one at a time in a beam. Hence `kZipformerCtc` -- the same Zipformer encoder --
// cannot be biased, while a NeMo transducer that is not a Zipformer at all can.
enum class ModelFamily {
  kUnknown,
  kOfflineTransducer,  // zipformer / nemo transducer, non-streaming. The
                       // shipped path: one phrase per clip, full right context.
  kOnlineTransducer,   // chunk-wise streaming export. Biasable too, but it
                       // loads under a different recogniser (see asr.h) and
                       // sees no right context, so it is a comparison baseline
                       // rather than the device path.
  kWhisper,
  kMoonshine,
  kSenseVoice,
  kNemoCtc,
  kZipformerCtc,
  kParaformer,
};

const char *ModelFamilyName(ModelFamily f);

enum class Precision { kInt8, kFp32 };
const char *PrecisionName(Precision p);

struct ModelProfile {
  std::string id;        // "<dir>" or "<dir>@fp32" when both precisions exist
  std::string dir_name;  // directory under models/
  std::string dir;       // absolute or root-relative path
  ModelFamily family = ModelFamily::kUnknown;
  Precision precision = Precision::kInt8;

  // Model files, absolute paths. Which ones are populated depends on `family`.
  std::string encoder;
  std::string decoder;
  std::string joiner;
  std::string model;              // single-file families (CTC, paraformer, ...)
  std::string preprocessor;       // moonshine
  std::string uncached_decoder;   // moonshine
  std::string cached_decoder;     // moonshine
  std::string merged_decoder;     // moonshine (newer exports)

  std::string tokens;
  std::string bpe_vocab;          // "" when unavailable
  std::string model_type;         // explicit hint for sherpa-onnx, may be ""
  std::string language;           // whisper only

  int64_t size_bytes = 0;

  // True when sherpa-onnx can bias this model towards our command vocabulary.
  bool supports_hotwords = false;
  // Set when the family supports hotwords but bpe.vocab is missing, i.e. the
  // feature is present in principle and broken in practice. Worth surfacing.
  std::string hotwords_blocker;

  // Human-readable one-liner for the dashboard.
  std::string Describe() const;
};

class ModelRegistry {
 public:
  // Scans every subdirectory of `models_dir`. Directories that do not look
  // like a model are skipped silently; ones that look like a model but are
  // incomplete land in `problems`.
  void Scan(const std::string &models_dir, std::vector<std::string> *problems = nullptr);

  const std::vector<ModelProfile> &models() const { return models_; }
  const ModelProfile *ById(const std::string &id) const;

  // Best default, in this order: biasable, int8, non-streaming, smallest.
  // Scan() sorts for exactly this, so the ordering *is* the policy -- see the
  // comment on the sort in models.cpp before changing it.
  const ModelProfile *PickDefault() const;

  // Resolves a user request. `id` may be "" (default), a full id, a directory
  // name, or a substring -- the dashboard sends full ids, humans type
  // fragments. `precision` may be "int8", "fp32" or "auto".
  const ModelProfile *Resolve(const std::string &id, const std::string &precision) const;

 private:
  std::vector<ModelProfile> models_;
};

}  // namespace vcc
