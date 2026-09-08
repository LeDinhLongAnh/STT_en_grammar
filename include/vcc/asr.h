// The STT core, with contextual biasing wired into it.
//
// Two decisions here are the whole project:
//
// 1. **Hotwords are passed per decode, not per model.** sherpa-onnx accepts a
//    hotword list on the stream as well as in the recogniser config, so the
//    recogniser is deliberately configured with NO hotwords file. Biasing is
//    then something we hand to an individual decode. Consequences:
//      * the same audio can be decoded unbiased and biased from one model in
//        memory, which is what makes a before/after comparison honest and what
//        keeps us inside the 200 MB budget;
//      * editing the hotword list costs nothing — no model reload, no 2-second
//        pause. Tuning becomes interactive.
//    (If a hotwords file *were* configured, the per-stream list would be
//    appended to it rather than replacing it, and there would be no way to get
//    an unbiased baseline without a second recogniser.)
//
// 2. **We bind the sherpa-onnx C API, not its C++ API.** It is extern "C", so
//    the same source links against a prebuilt MSVC DLL on the dev box and a
//    cross-compiled .so on the Cortex-A55 target, regardless of which compiler
//    or C++ runtime built the library.
//
// One engine, two recognisers. Non-streaming models load under the *offline*
// recogniser and decode in a single call; streaming (chunk-wise) exports load
// under the *online* recogniser, which needs the audio pumped through a
// ready/decode loop plus a tail of silence to flush its last chunk. Biasing
// works identically on both -- it is a property of the transducer decoder, not
// of the encoder -- so `Recognize()` hides the difference and only the RTF and
// the accuracy give it away. The device ships the offline path; the streaming
// one exists so the dashboard can answer "would streaming be good enough?"
// with a measurement instead of an opinion.
#pragma once

#include <memory>
#include <mutex>
#include <string>
#include <vector>

#include "vcc/models.h"
#include "vcc/wav.h"

namespace vcc {

struct AsrOptions {
  int num_threads = 4;
  std::string provider = "cpu";

  // Biasing requires modified_beam_search; greedy_search ignores hotwords
  // entirely. Load() refuses to pretend otherwise.
  std::string decoding_method = "modified_beam_search";
  int max_active_paths = 4;

  // Default boost for hotwords that do not carry their own score.
  float hotwords_score = 2.0f;

  // Small negative pressure on the blank symbol. Helps recover the swallowed
  // final consonants that characterise Vietnamese-accented English; 0 disables.
  float blank_penalty = 0.0f;

  bool debug = false;
};

struct AsrResult {
  std::string text;
  std::vector<std::string> tokens;
  std::vector<float> timestamps;
  std::vector<float> token_logprobs;  // empty when the model does not report them

  float avg_logprob = 0.0f;
  float min_logprob = 0.0f;
  bool has_logprobs = false;

  double decode_ms = 0.0;
  double audio_s = 0.0;
  double rtf() const { return audio_s > 0 ? (decode_ms / 1000.0) / audio_s : 0.0; }

  std::string json;  // sherpa-onnx's own result JSON, passed through verbatim
};

class AsrEngine {
 public:
  AsrEngine();
  ~AsrEngine();
  AsrEngine(const AsrEngine &) = delete;
  AsrEngine &operator=(const AsrEngine &) = delete;

  // Creates the recogniser. Replaces any previously loaded model. On failure the
  // engine is left unloaded and `error` explains why.
  bool Load(const ModelProfile &profile, const AsrOptions &opts, std::string *error);
  void Unload();
  bool loaded() const;

  // Decodes one utterance. `hotwords` is the serialised per-stream list from
  // HotwordList::Serialize() — pass an empty string for an unbiased baseline.
  //
  // Serialised internally: one ONNX Runtime session with several worker threads,
  // one utterance at a time, which is how the router will run it.
  bool Recognize(const AudioBuffer &audio, const std::string &hotwords,
                 AsrResult *out, std::string *error) const;

  // True when this model can be biased at all: contextual biasing needs a
  // transducer (offline or streaming), modified_beam_search, and a bpe.vocab
  // beside the model.
  // Miss any one and sherpa-onnx biases nothing while reporting no error, so
  // the reason is spelled out rather than left to be discovered.
  bool biasing_available() const { return biasing_available_; }
  const std::string &biasing_blocker() const { return biasing_blocker_; }

  const ModelProfile &profile() const { return profile_; }
  const AsrOptions &options() const { return opts_; }
  double load_ms() const { return load_ms_; }

  static std::string SherpaVersion();

 private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
  ModelProfile profile_;
  AsrOptions opts_;
  bool biasing_available_ = false;
  std::string biasing_blocker_;
  double load_ms_ = 0.0;
  mutable std::mutex decode_mu_;
};

}  // namespace vcc
