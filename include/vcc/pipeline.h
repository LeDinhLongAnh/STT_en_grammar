// Audio in, two transcripts out.
//
// The pipeline's job is to make the effect of biasing visible:
//
//   audio ──┬─► ASR, no hotwords ─────────────────────────► raw
//           └─► ASR, hotwords ───► rewrite table ─────────► filtered
//                    stage 1          stage 2
//
// Both decodes run on the same loaded model, so the comparison isolates exactly
// one variable. Stage 2 is separately reported and separately switchable,
// because "biasing fixed it" and "a text rule fixed it" are different claims and
// only one of them survives a change of vocabulary.
#pragma once

#include <memory>
#include <string>
#include <vector>

#include "vcc/asr.h"
#include "vcc/config.h"
#include "vcc/diff.h"
#include "vcc/hotwords.h"
#include "vcc/models.h"
#include "vcc/text.h"
#include "vcc/wav.h"

namespace vcc {

// One utterance, decoded both ways.
struct Comparison {
  bool ok = false;
  std::string error;

  AsrResult raw;       // no hotwords
  AsrResult biased;    // hotwords applied inside the decoder

  std::string filtered;                 // biased text after the rewrite table
  std::vector<RewriteHit> rewrite_hits; // which rules fired, for the UI

  // raw -> filtered, the end-to-end effect of the whole filter.
  std::vector<DiffSpan> diff;
  bool changed = false;

  LevelStats levels;
  double total_ms = 0.0;

  // Populated only when a reference transcript is supplied (evaluation mode).
  bool has_reference = false;
  std::string reference;
  ErrorRate wer_raw;
  ErrorRate wer_filtered;

  // The text a caller should act on.
  const std::string &final_text() const { return filtered; }
};

struct Paths {
  std::string root;
  std::string models_dir;
  std::string hotwords;
  std::string rewrites;
};

class Pipeline {
 public:
  Pipeline();
  ~Pipeline();

  // Locates the project root, loads config/app.ini and the data files, then
  // scans models/. Does not load a model — call LoadModel() for that, so a
  // caller can list what is available first.
  bool Init(const std::string &explicit_root, const std::vector<std::string> &overrides,
            std::string *error);

  // Loads (or reloads) the recogniser. Empty id means "whatever config or the
  // registry considers best".
  bool LoadModel(const std::string &model_id, const std::string &precision,
                 std::string *error);

  // Decode one utterance both ways. `reference`, when non-empty, adds WER.
  Comparison Process(const AudioBuffer &audio, const std::string &reference = "") const;

  // Re-run only the parts that do not need the audio: the rewrite table over an
  // existing biased transcript. Used when the rewrite rules change.
  void ReapplyRewrites(Comparison *c) const;

  // --- data the caller may edit at runtime -------------------------------
  // Editing hotwords costs nothing: they are passed per decode, so the next
  // Process() picks them up with no model reload.
  HotwordList &hotwords() { return hotwords_; }
  const HotwordList &hotwords() const { return hotwords_; }
  RewriteTable &rewrites() { return rewrites_; }
  const RewriteTable &rewrites() const { return rewrites_; }

  bool SaveHotwords(std::string *error) const;
  bool SaveRewrites(std::string *error) const;
  bool ReloadDataFiles(std::string *error);

  // Serialised hotword string handed to the decoder, plus any warnings raised
  // while building it. Exposed so the dashboard can show precisely what the
  // decoder was given.
  std::string SerializedHotwords(std::vector<std::string> *warnings = nullptr) const;

  bool biasing_enabled() const { return biasing_enabled_; }
  void set_biasing_enabled(bool on) { biasing_enabled_ = on; }
  bool rewrites_enabled() const { return rewrites_enabled_; }
  void set_rewrites_enabled(bool on) { rewrites_enabled_ = on; }

  // --- accessors ---------------------------------------------------------
  const Paths &paths() const { return paths_; }
  Config &config() { return config_; }
  const Config &config() const { return config_; }
  const ModelRegistry &registry() const { return registry_; }
  const AsrEngine &asr() const { return asr_; }
  const std::vector<std::string> &warnings() const { return warnings_; }

  AsrOptions AsrOptionsFromConfig() const;

 private:
  Paths paths_;
  Config config_;
  ModelRegistry registry_;
  AsrEngine asr_;
  HotwordList hotwords_;
  RewriteTable rewrites_;
  bool biasing_enabled_ = true;
  bool rewrites_enabled_ = true;
  std::vector<std::string> warnings_;
};

}  // namespace vcc
