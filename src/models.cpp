#include "vcc/models.h"

#include <algorithm>
#include <cstdio>

#include "vcc/core.h"
#include "vcc/log.h"

namespace vcc {
namespace {

// All *.onnx / *.ort files directly inside a model dir.
std::vector<std::string> WeightFiles(const std::string &dir) {
  std::vector<std::string> out;
  for (const std::string &f : ListDir(dir, /*dirs_only=*/false)) {
    const std::string low = ToLower(f);
    if (EndsWith(low, ".onnx") || EndsWith(low, ".ort")) out.push_back(f);
  }
  return out;
}

// Does this name advertise quantised weights?
bool NameSaysInt8(const std::string &f) {
  const std::string low = ToLower(f);
  return low.find("int8") != std::string::npos ||
         low.find("quantized") != std::string::npos ||
         low.find("quantised") != std::string::npos;
}

// Precision of one weight file.
//
// Most sherpa-onnx exports mark it per file ("encoder.int8.onnx" next to
// "encoder.onnx"). Some newer ones -- the 2026 Moonshine builds, for instance --
// ship a single quantised weight set with plain filenames and put the marker in
// the directory name instead. `dir_default_int8` carries that case.
bool FileIsInt8(const std::string &f, bool dir_default_int8) {
  return NameSaysInt8(f) ? true : dir_default_int8;
}

// Picks the file whose name contains `role` at the requested precision.
// Longer matches win, so "uncached_decode" never shadows "decode".
std::string PickRole(const std::vector<std::string> &files, const std::string &dir,
                     const std::vector<std::string> &role_keys, bool want_int8,
                     bool dir_default_int8,
                     const std::vector<std::string> &exclude_keys = {}) {
  std::string best;
  size_t best_key_len = 0;
  for (const std::string &f : files) {
    const std::string low = ToLower(f);
    if (FileIsInt8(f, dir_default_int8) != want_int8) continue;
    bool excluded = false;
    for (const std::string &x : exclude_keys) {
      if (low.find(x) != std::string::npos) { excluded = true; break; }
    }
    if (excluded) continue;
    for (const std::string &k : role_keys) {
      if (low.find(k) == std::string::npos) continue;
      if (k.size() >= best_key_len) {
        best_key_len = k.size();
        best = PathJoin(dir, f);
      }
    }
  }
  return best;
}

int64_t DirSize(const std::string &dir) {
  int64_t total = 0;
  for (const std::string &f : ListDir(dir, false)) {
    const int64_t s = FileSize(PathJoin(dir, f));
    if (s > 0) total += s;
  }
  return total;
}

std::string FindTokens(const std::string &dir) {
  for (const std::string &f : ListDir(dir, false)) {
    const std::string low = ToLower(f);
    if (low == "tokens.txt" || EndsWith(low, "-tokens.txt") ||
        EndsWith(low, "_tokens.txt")) {
      return PathJoin(dir, f);
    }
  }
  return std::string();
}

// Builds one profile for a (dir, precision) pair, or returns false when that
// combination is not fully present.
bool BuildProfile(const std::string &models_dir, const std::string &name,
                  bool want_int8, ModelProfile *out, std::string *why) {
  const std::string dir = PathJoin(models_dir, name);
  const std::vector<std::string> files = WeightFiles(dir);
  if (files.empty()) return false;

  const std::string low_name = ToLower(name);

  // If no individual weight file declares a precision, fall back to what the
  // directory name says. Without this the 2026 Moonshine builds -- whose files
  // are plain .ort but whose directory is "...-quantized-..." -- would be
  // advertised as fp32 and sorted below genuinely larger models.
  bool any_file_marked = false;
  for (const std::string &f : files) {
    if (NameSaysInt8(f)) { any_file_marked = true; break; }
  }
  const bool dir_int8 = !any_file_marked && NameSaysInt8(name);

  out->dir_name = name;
  out->dir = dir;
  out->precision = want_int8 ? Precision::kInt8 : Precision::kFp32;
  out->id = want_int8 ? name : name + "@fp32";
  out->tokens = FindTokens(dir);
  const std::string bpe = PathJoin(dir, "bpe.vocab");
  if (FileExists(bpe)) out->bpe_vocab = bpe;
  out->size_bytes = DirSize(dir);

  // --- moonshine ----------------------------------------------------------
  if (low_name.find("moonshine") != std::string::npos) {
    out->family = ModelFamily::kMoonshine;
    out->preprocessor = PickRole(files, dir, {"preprocess"}, want_int8, dir_int8);
    out->encoder = PickRole(files, dir, {"encoder_model", "encode"}, want_int8, dir_int8,
                            {"uncached", "cached", "decode"});
    out->uncached_decoder = PickRole(files, dir, {"uncached_decode"}, want_int8, dir_int8);
    out->cached_decoder =
        PickRole(files, dir, {"cached_decode"}, want_int8, dir_int8, {"uncached"});
    out->merged_decoder =
        PickRole(files, dir, {"decoder_model_merged", "merged_decode"}, want_int8, dir_int8);
    const bool split_ok = !out->uncached_decoder.empty() && !out->cached_decoder.empty();
    if (out->encoder.empty() || (!split_ok && out->merged_decoder.empty())) {
      if (why) *why = "moonshine layout incomplete (need encoder + decoder)";
      return false;
    }
    if (out->tokens.empty()) {
      if (why) *why = "no tokens.txt";
      return false;
    }
    return true;
  }

  // --- whisper ------------------------------------------------------------
  if (low_name.find("whisper") != std::string::npos) {
    out->family = ModelFamily::kWhisper;
    out->encoder = PickRole(files, dir, {"encoder"}, want_int8, dir_int8);
    out->decoder = PickRole(files, dir, {"decoder"}, want_int8, dir_int8);
    out->language = "en";
    if (out->encoder.empty() || out->decoder.empty()) {
      if (why) *why = "whisper needs both encoder and decoder at this precision";
      return false;
    }
    if (out->tokens.empty()) {
      if (why) *why = "no tokens.txt";
      return false;
    }
    return true;
  }

  // --- sense-voice --------------------------------------------------------
  if (low_name.find("sense-voice") != std::string::npos ||
      low_name.find("sense_voice") != std::string::npos) {
    out->family = ModelFamily::kSenseVoice;
    out->model = PickRole(files, dir, {"model"}, want_int8, dir_int8);
    if (out->model.empty() || out->tokens.empty()) {
      if (why) *why = "sense-voice needs model.onnx + tokens.txt";
      return false;
    }
    return true;
  }

  // --- transducer (encoder + decoder + joiner) ----------------------------
  const std::string enc = PickRole(files, dir, {"encoder"}, want_int8, dir_int8);
  const std::string dec = PickRole(files, dir, {"decoder"}, want_int8, dir_int8);
  const std::string joi = PickRole(files, dir, {"joiner"}, want_int8, dir_int8);
  if (!enc.empty() && !dec.empty() && !joi.empty()) {
    // Streaming exports load under the *online* recognizer instead, which is a
    // different set of C entry points and a different decode loop. Two
    // independent tells, because neither is universal: icefall's
    // pruned_transducer_stateless7_streaming names the chunk geometry in the
    // filename, while the 2023-02-21 export does not and only the directory
    // says "streaming".
    const std::string enc_low = ToLower(PathBase(enc));
    const bool streaming = enc_low.find("chunk") != std::string::npos ||
                           low_name.find("streaming") != std::string::npos ||
                           low_name.find("online") != std::string::npos;
    out->family =
        streaming ? ModelFamily::kOnlineTransducer : ModelFamily::kOfflineTransducer;
    out->encoder = enc;
    out->decoder = dec;
    out->joiner = joi;
    if (low_name.find("nemo") != std::string::npos ||
        low_name.find("parakeet") != std::string::npos) {
      out->model_type = "nemo_transducer";
    }
    if (out->tokens.empty()) {
      if (why) *why = "no tokens.txt";
      return false;
    }
    return true;
  }

  // --- single-file CTC families ------------------------------------------
  const std::string single = PickRole(files, dir, {"model", "ctc"}, want_int8, dir_int8);
  if (!single.empty() && !out->tokens.empty()) {
    if (low_name.find("zipformer") != std::string::npos &&
        low_name.find("ctc") != std::string::npos) {
      out->family = ModelFamily::kZipformerCtc;
    } else if (low_name.find("paraformer") != std::string::npos) {
      out->family = ModelFamily::kParaformer;
    } else if (low_name.find("nemo") != std::string::npos) {
      out->family = ModelFamily::kNemoCtc;
    } else {
      if (why) *why = "single-model directory of unrecognised family";
      return false;
    }
    out->model = single;
    return true;
  }

  return false;
}

}  // namespace

const char *ModelFamilyName(ModelFamily f) {
  switch (f) {
    case ModelFamily::kOfflineTransducer: return "transducer";
    case ModelFamily::kOnlineTransducer:  return "online-transducer";
    case ModelFamily::kWhisper:           return "whisper";
    case ModelFamily::kMoonshine:         return "moonshine";
    case ModelFamily::kSenseVoice:        return "sense-voice";
    case ModelFamily::kNemoCtc:           return "nemo-ctc";
    case ModelFamily::kZipformerCtc:      return "zipformer-ctc";
    case ModelFamily::kParaformer:        return "paraformer";
    default:                              return "unknown";
  }
}

const char *PrecisionName(Precision p) {
  return p == Precision::kInt8 ? "int8" : "fp32";
}

std::string ModelProfile::Describe() const {
  char buf[128];
  std::snprintf(buf, sizeof(buf), "%s / %s / %.0f MB", ModelFamilyName(family),
                PrecisionName(precision),
                static_cast<double>(size_bytes) / (1024.0 * 1024.0));
  std::string s = buf;
  if (supports_hotwords) {
    s += " / hotwords";
  } else if (!hotwords_blocker.empty()) {
    s += " / hotwords blocked";
  }
  return s;
}

void ModelRegistry::Scan(const std::string &models_dir,
                         std::vector<std::string> *problems) {
  models_.clear();
  if (!DirExists(models_dir)) {
    if (problems) problems->push_back("models directory not found: " + models_dir);
    return;
  }

  for (const std::string &name : ListDir(models_dir, /*dirs_only=*/true)) {
    if (!name.empty() && name[0] == '.') continue;  // .cache and friends
    const std::string dir = PathJoin(models_dir, name);

    bool any = false;
    for (const bool want_int8 : {true, false}) {
      ModelProfile p;
      std::string why;
      if (!BuildProfile(models_dir, name, want_int8, &p, &why)) {
        if (!why.empty() && want_int8 && problems) {
          problems->push_back(name + ": " + why);
        }
        continue;
      }
      // Both transducer families expose the same contextual-biasing hook.
      p.supports_hotwords = p.family == ModelFamily::kOfflineTransducer ||
                            p.family == ModelFamily::kOnlineTransducer;
      if (p.supports_hotwords && p.bpe_vocab.empty()) {
        p.supports_hotwords = false;
        p.hotwords_blocker =
            "bpe.vocab missing - run scripts/download_models.sh --only " + name;
      }
      models_.push_back(std::move(p));
      any = true;
    }
    // A directory that yields no profile is not necessarily a problem: the
    // models tree also holds things that are not recognisers.
    (void)any;
  }

  // Ordering doubles as the default-model policy, so it encodes what we
  // actually want on a 200 MB target:
  //   1. biasing-capable first  -- without it the whole feature is off
  //   2. int8 first             -- fp32 weights do not fit the budget
  //   3. NON-STREAMING first    -- the device decodes one whole phrase per clip,
  //      so a streaming model buys nothing and costs right context. Picking one
  //      by accident would also silently switch the decode path.
  //   4. SMALLEST first         -- the budget is the binding constraint, and a
  //      bigger model also resists bias harder (see the boost note in README)
  //   5. id, only to break exact ties reproducibly across filesystems
  //
  // Sorting by id at step 4 would make the default depend on alphabetical
  // accident: "zipformer-en" (67 MB) sorts ahead of "zipformer-small-en"
  // (27 MB), which is the opposite of what the budget wants.
  std::sort(models_.begin(), models_.end(),
            [](const ModelProfile &a, const ModelProfile &b) {
              if (a.supports_hotwords != b.supports_hotwords) {
                return a.supports_hotwords;
              }
              if (a.precision != b.precision) {
                return a.precision == Precision::kInt8;
              }
              const bool a_stream = a.family == ModelFamily::kOnlineTransducer;
              const bool b_stream = b.family == ModelFamily::kOnlineTransducer;
              if (a_stream != b_stream) return b_stream;
              if (a.size_bytes != b.size_bytes) return a.size_bytes < b.size_bytes;
              return a.id < b.id;
            });

  VCC_INFO << "model registry: " << models_.size() << " usable profile(s) in "
           << models_dir;
}

const ModelProfile *ModelRegistry::ById(const std::string &id) const {
  for (const ModelProfile &m : models_) {
    if (m.id == id) return &m;
  }
  return nullptr;
}

const ModelProfile *ModelRegistry::PickDefault() const {
  return models_.empty() ? nullptr : &models_.front();  // Scan() sorted for this
}

const ModelProfile *ModelRegistry::Resolve(const std::string &id,
                                           const std::string &precision) const {
  const std::string want_prec = ToLower(Trim(precision));
  const bool need_int8 = want_prec == "int8";
  const bool need_fp32 = want_prec == "fp32";

  auto precision_ok = [&](const ModelProfile &m) {
    if (need_int8) return m.precision == Precision::kInt8;
    if (need_fp32) return m.precision == Precision::kFp32;
    return true;
  };

  if (Trim(id).empty()) {
    for (const ModelProfile &m : models_) {
      if (precision_ok(m)) return &m;
    }
    return PickDefault();
  }

  const std::string needle = ToLower(Trim(id));
  // exact id, then exact directory, then substring -- in that order so a full
  // id from the dashboard is never reinterpreted as a fuzzy request.
  for (const ModelProfile &m : models_) {
    if (ToLower(m.id) == needle && precision_ok(m)) return &m;
  }
  for (const ModelProfile &m : models_) {
    if (ToLower(m.dir_name) == needle && precision_ok(m)) return &m;
  }
  for (const ModelProfile &m : models_) {
    if (ToLower(m.id).find(needle) != std::string::npos && precision_ok(m)) return &m;
  }
  return nullptr;
}

}  // namespace vcc
