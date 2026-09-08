#include "vcc/asr.h"

#include <algorithm>
#include <cstring>
#include <numeric>

#include "sherpa-onnx/c-api/c-api.h"
#include "vcc/core.h"
#include "vcc/log.h"

namespace vcc {
namespace {

// A chunk-wise encoder cannot emit the tail of an utterance until it has been
// handed enough future frames to fill its last chunk. Feed silence after the
// audio so the final word actually comes out; without this the streaming models
// truncate it, which looks exactly like a recognition error.
constexpr double kOnlineTailPaddingS = 0.5;

}  // namespace

struct AsrEngine::Impl {
  // Exactly one of these is non-null. Streaming exports load under the online
  // recognizer, which is a separate set of C entry points with its own decode
  // loop -- see the note in asr.h.
  const SherpaOnnxOfflineRecognizer *recognizer = nullptr;
  const SherpaOnnxOnlineRecognizer *online = nullptr;
  int sample_rate = 16000;

  // The C structs hold borrowed `const char *`. Every path we hand over has to
  // outlive the Create call, so the strings live here rather than in locals.
  std::string tokens, encoder, decoder, joiner, model;
  std::string preprocessor, uncached_decoder, cached_decoder, merged_decoder;
  std::string bpe_vocab, modeling_unit, model_type, provider, decoding_method;
  std::string language, task;

  ~Impl() {
    if (recognizer) SherpaOnnxDestroyOfflineRecognizer(recognizer);
    if (online) SherpaOnnxDestroyOnlineRecognizer(online);
  }
};

AsrEngine::AsrEngine() = default;
AsrEngine::~AsrEngine() = default;

bool AsrEngine::loaded() const {
  return impl_ && (impl_->recognizer != nullptr || impl_->online != nullptr);
}

void AsrEngine::Unload() {
  std::lock_guard<std::mutex> lock(decode_mu_);
  impl_.reset();
  biasing_available_ = false;
  biasing_blocker_.clear();
}

std::string AsrEngine::SherpaVersion() {
  const char *v = SherpaOnnxGetVersionStr();
  return v ? v : "unknown";
}

bool AsrEngine::Load(const ModelProfile &profile, const AsrOptions &opts,
                     std::string *error) {
  auto fail = [&](const std::string &m) {
    if (error) *error = m;
    VCC_ERROR << "asr load failed: " << m;
    return false;
  };

  Timer timer;
  std::lock_guard<std::mutex> lock(decode_mu_);

  auto impl = std::unique_ptr<Impl>(new Impl());
  profile_ = profile;
  opts_ = opts;
  biasing_available_ = false;
  biasing_blocker_.clear();

  if (profile.tokens.empty() || !FileExists(profile.tokens)) {
    return fail("tokens file missing: " + profile.tokens);
  }

  // --- can this model be biased? -----------------------------------------
  // Three conditions, all necessary, none of which sherpa-onnx will complain
  // about if unmet — it just silently biases nothing.
  std::string decoding_method =
      opts.decoding_method.empty() ? std::string("greedy_search") : opts.decoding_method;

  const bool is_transducer = profile.family == ModelFamily::kOfflineTransducer ||
                             profile.family == ModelFamily::kOnlineTransducer;

  if (!is_transducer) {
    biasing_blocker_ = std::string("contextual biasing needs a transducer; ") +
                       ModelFamilyName(profile.family) +
                       " models have no biasing hook in sherpa-onnx";
  } else if (profile.bpe_vocab.empty()) {
    biasing_blocker_ =
        "bpe.vocab is missing next to the model, so hotwords cannot be tokenised - "
        "run scripts/download_models.sh --only " + profile.dir_name;
  } else if (decoding_method != "modified_beam_search") {
    // Not an error: the user may have asked for greedy deliberately to see the
    // unbiased baseline in isolation. Say what it costs and move on.
    biasing_blocker_ = "decoding_method is '" + decoding_method +
                       "'; hotwords are only honoured by modified_beam_search";
  } else {
    biasing_available_ = true;
  }

  // --- struct wiring ------------------------------------------------------
  impl->tokens = profile.tokens;
  impl->provider = opts.provider.empty() ? "cpu" : opts.provider;
  impl->decoding_method = decoding_method;
  impl->model_type = profile.model_type;

  // --- streaming exports take the online recognizer -----------------------
  // Same biasing hook, different C entry points and a different decode loop.
  // Kept as an early return rather than folded into the switch below, because
  // the two recognisers share no config struct at all.
  if (profile.family == ModelFamily::kOnlineTransducer) {
    impl->encoder = profile.encoder;
    impl->decoder = profile.decoder;
    impl->joiner = profile.joiner;
    if (biasing_available_) {
      impl->bpe_vocab = profile.bpe_vocab;
      impl->modeling_unit = "bpe";
    }

    // sherpa-onnx calls exit() when ONNX Runtime cannot open a file, so the
    // paths are checked here too rather than only on the offline path.
    for (const std::string *p : {&impl->encoder, &impl->decoder, &impl->joiner,
                                 &impl->bpe_vocab}) {
      if (!p->empty() && !FileExists(*p)) return fail("model file not found: " + *p);
    }

    SherpaOnnxOnlineRecognizerConfig oc;
    std::memset(&oc, 0, sizeof(oc));
    oc.feat_config.sample_rate = 16000;
    oc.feat_config.feature_dim = 80;
    oc.model_config.num_threads = std::max(1, opts.num_threads);
    oc.model_config.debug = opts.debug ? 1 : 0;
    oc.model_config.provider = impl->provider.c_str();
    oc.model_config.tokens = impl->tokens.c_str();
    oc.model_config.transducer.encoder = impl->encoder.c_str();
    oc.model_config.transducer.decoder = impl->decoder.c_str();
    oc.model_config.transducer.joiner = impl->joiner.c_str();
    if (biasing_available_) {
      oc.model_config.modeling_unit = impl->modeling_unit.c_str();
      oc.model_config.bpe_vocab = impl->bpe_vocab.c_str();
    }
    oc.decoding_method = impl->decoding_method.c_str();
    oc.max_active_paths = std::max(1, opts.max_active_paths);
    oc.blank_penalty = opts.blank_penalty;
    oc.hotwords_score = opts.hotwords_score;
    oc.hotwords_file = nullptr;  // deliberately -- same reason as offline

    // Endpointing would split one clip into several results. Input is one
    // phrase per clip by design (this project has no VAD either), so the caller
    // owns the boundaries and the whole clip is a single segment.
    oc.enable_endpoint = 0;

    impl->online = SherpaOnnxCreateOnlineRecognizer(&oc);
    if (impl->online == nullptr) {
      return fail("sherpa-onnx refused the streaming configuration for '" +
                  profile.id + "' (set asr.debug=true for its own diagnostics)");
    }
    impl->sample_rate = oc.feat_config.sample_rate;
    impl_ = std::move(impl);
    load_ms_ = timer.ElapsedMs();

    VCC_INFO << "loaded '" << profile.id << "' (online-transducer/"
             << PrecisionName(profile.precision) << ") in " << load_ms_
             << " ms, method=" << impl_->decoding_method
             << ", threads=" << oc.model_config.num_threads
             << ", biasing=" << (biasing_available_ ? "available" : "unavailable");
    if (!biasing_available_) VCC_WARN << "biasing unavailable: " << biasing_blocker_;
    return true;
  }

  SherpaOnnxOfflineRecognizerConfig config;
  std::memset(&config, 0, sizeof(config));

  config.feat_config.sample_rate = 16000;
  config.feat_config.feature_dim = 80;
  config.model_config.num_threads = std::max(1, opts.num_threads);
  config.model_config.debug = opts.debug ? 1 : 0;
  config.model_config.provider = impl->provider.c_str();
  config.model_config.tokens = impl->tokens.c_str();
  if (!impl->model_type.empty()) config.model_config.model_type = impl->model_type.c_str();

  // The BPE vocabulary is what lets sherpa-onnx tokenise a hotword phrase into
  // the same subword units the decoder emits. Without it the only available
  // modeling_unit is "cjkchar", which splits English words into single letters
  // that never line up with the decoder's output -- biasing degrades to noise
  // while reporting success.
  if (biasing_available_) {
    impl->bpe_vocab = profile.bpe_vocab;
    impl->modeling_unit = "bpe";
    config.model_config.modeling_unit = impl->modeling_unit.c_str();
    config.model_config.bpe_vocab = impl->bpe_vocab.c_str();
  }

  config.decoding_method = impl->decoding_method.c_str();
  config.max_active_paths = std::max(1, opts.max_active_paths);
  config.blank_penalty = opts.blank_penalty;
  config.hotwords_score = opts.hotwords_score;

  // NOTE: config.hotwords_file is deliberately left null. See the header. A
  // configured file becomes a permanent floor that per-stream hotwords are
  // *added* to, which would make an unbiased baseline impossible.
  config.hotwords_file = nullptr;

  switch (profile.family) {
    case ModelFamily::kOfflineTransducer:
      impl->encoder = profile.encoder;
      impl->decoder = profile.decoder;
      impl->joiner = profile.joiner;
      config.model_config.transducer.encoder = impl->encoder.c_str();
      config.model_config.transducer.decoder = impl->decoder.c_str();
      config.model_config.transducer.joiner = impl->joiner.c_str();
      break;

    case ModelFamily::kWhisper:
      impl->encoder = profile.encoder;
      impl->decoder = profile.decoder;
      impl->language = profile.language.empty() ? "en" : profile.language;
      impl->task = "transcribe";
      config.model_config.whisper.encoder = impl->encoder.c_str();
      config.model_config.whisper.decoder = impl->decoder.c_str();
      config.model_config.whisper.language = impl->language.c_str();
      config.model_config.whisper.task = impl->task.c_str();
      config.model_config.whisper.tail_paddings = -1;
      impl->decoding_method = "greedy_search";  // beam search buys nothing here
      config.decoding_method = impl->decoding_method.c_str();
      break;

    case ModelFamily::kMoonshine:
      impl->preprocessor = profile.preprocessor;
      impl->encoder = profile.encoder;
      impl->uncached_decoder = profile.uncached_decoder;
      impl->cached_decoder = profile.cached_decoder;
      impl->merged_decoder = profile.merged_decoder;
      config.model_config.moonshine.encoder = impl->encoder.c_str();
      if (!impl->preprocessor.empty()) {
        config.model_config.moonshine.preprocessor = impl->preprocessor.c_str();
      }
      if (!impl->merged_decoder.empty()) {
        config.model_config.moonshine.merged_decoder = impl->merged_decoder.c_str();
      } else {
        config.model_config.moonshine.uncached_decoder = impl->uncached_decoder.c_str();
        config.model_config.moonshine.cached_decoder = impl->cached_decoder.c_str();
      }
      impl->decoding_method = "greedy_search";
      config.decoding_method = impl->decoding_method.c_str();
      break;

    case ModelFamily::kSenseVoice:
      impl->model = profile.model;
      config.model_config.sense_voice.model = impl->model.c_str();
      config.model_config.sense_voice.language = "en";
      config.model_config.sense_voice.use_itn = 0;
      break;

    case ModelFamily::kNemoCtc:
      impl->model = profile.model;
      config.model_config.nemo_ctc.model = impl->model.c_str();
      break;

    case ModelFamily::kZipformerCtc:
      impl->model = profile.model;
      config.model_config.zipformer_ctc.model = impl->model.c_str();
      break;

    case ModelFamily::kParaformer:
      impl->model = profile.model;
      config.model_config.paraformer.model = impl->model.c_str();
      break;

    default:
      return fail("unsupported model family for " + profile.id);
  }

  // sherpa-onnx calls exit() when ONNX Runtime cannot open a model file, so
  // check the paths ourselves first: a clear error beats a dead process.
  for (const std::string *p : {&impl->encoder, &impl->decoder, &impl->joiner,
                               &impl->model, &impl->preprocessor,
                               &impl->uncached_decoder, &impl->cached_decoder,
                               &impl->merged_decoder, &impl->bpe_vocab}) {
    if (!p->empty() && !FileExists(*p)) return fail("model file not found: " + *p);
  }

  impl->recognizer = SherpaOnnxCreateOfflineRecognizer(&config);
  if (impl->recognizer == nullptr) {
    return fail("sherpa-onnx refused the configuration for '" + profile.id +
                "' (set asr.debug=true for its own diagnostics)");
  }

  impl->sample_rate = config.feat_config.sample_rate;
  impl_ = std::move(impl);
  load_ms_ = timer.ElapsedMs();

  VCC_INFO << "loaded '" << profile.id << "' (" << ModelFamilyName(profile.family)
           << "/" << PrecisionName(profile.precision) << ") in " << load_ms_
           << " ms, method=" << impl_->decoding_method
           << ", threads=" << config.model_config.num_threads
           << ", biasing=" << (biasing_available_ ? "available" : "unavailable");
  if (!biasing_available_) VCC_WARN << "biasing unavailable: " << biasing_blocker_;
  return true;
}

bool AsrEngine::Recognize(const AudioBuffer &audio, const std::string &hotwords,
                          AsrResult *out, std::string *error) const {
  auto fail = [&](const std::string &m) {
    if (error) *error = m;
    return false;
  };
  if (!loaded()) return fail("no model loaded");
  if (audio.samples.empty()) return fail("empty audio");
  if (audio.sample_rate <= 0) return fail("audio has no sample rate");

  const AudioBuffer *use = &audio;
  AudioBuffer resampled;
  if (audio.sample_rate != impl_->sample_rate) {
    std::string err;
    if (!Resample(audio, impl_->sample_rate, &resampled, &err)) {
      return fail("resample to " + std::to_string(impl_->sample_rate) +
                  " Hz failed: " + err);
    }
    use = &resampled;
  }

  Timer timer;
  std::lock_guard<std::mutex> lock(decode_mu_);

  // --- streaming path -----------------------------------------------------
  // Same biasing contract as offline (empty string == unbiased baseline), but
  // the audio has to be pushed and then pumped: the recogniser tells us when it
  // has enough buffered frames for another chunk.
  if (impl_->online) {
    const SherpaOnnxOnlineStream *s =
        hotwords.empty()
            ? SherpaOnnxCreateOnlineStream(impl_->online)
            : SherpaOnnxCreateOnlineStreamWithHotwords(impl_->online,
                                                       hotwords.c_str());
    if (s == nullptr) return fail("could not create streaming decode stream");

    SherpaOnnxOnlineStreamAcceptWaveform(s, use->sample_rate, use->samples.data(),
                                         static_cast<int32_t>(use->samples.size()));
    // Silence after the speech, so the encoder can complete its last chunk and
    // emit the final word. See kOnlineTailPaddingS.
    const std::vector<float> tail(
        static_cast<size_t>(kOnlineTailPaddingS * use->sample_rate), 0.0f);
    SherpaOnnxOnlineStreamAcceptWaveform(s, use->sample_rate, tail.data(),
                                         static_cast<int32_t>(tail.size()));
    SherpaOnnxOnlineStreamInputFinished(s);

    while (SherpaOnnxIsOnlineStreamReady(impl_->online, s)) {
      SherpaOnnxDecodeOnlineStream(impl_->online, s);
    }

    const SherpaOnnxOnlineRecognizerResult *r =
        SherpaOnnxGetOnlineStreamResult(impl_->online, s);
    if (r == nullptr) {
      SherpaOnnxDestroyOnlineStream(s);
      return fail("streaming decoder returned no result");
    }

    out->text = r->text ? r->text : "";
    out->json = r->json ? r->json : "";
    out->tokens.clear();
    out->timestamps.clear();
    out->token_logprobs.clear();

    const int32_t n = std::max<int32_t>(0, r->count);
    if (r->tokens_arr) {
      out->tokens.reserve(static_cast<size_t>(n));
      for (int32_t i = 0; i < n; ++i) {
        out->tokens.push_back(r->tokens_arr[i] ? r->tokens_arr[i] : "");
      }
    }
    if (r->timestamps) out->timestamps.assign(r->timestamps, r->timestamps + n);
    // The online result carries no per-token log-probabilities, so anything
    // reading avg_logprob has to tolerate their absence rather than see zeros
    // as high confidence.
    out->has_logprobs = false;
    out->avg_logprob = 0.0f;
    out->min_logprob = 0.0f;

    SherpaOnnxDestroyOnlineRecognizerResult(r);
    SherpaOnnxDestroyOnlineStream(s);

    out->decode_ms = timer.ElapsedMs();
    out->audio_s = use->duration_s();
    VCC_DEBUG << "streamed " << out->audio_s << "s in " << out->decode_ms
              << " ms (rtf " << out->rtf() << ", biasing "
              << (hotwords.empty() ? "off" : "on") << "): '" << out->text << "'";
    return true;
  }

  // An empty hotword string takes the plain CreateStream path: no context graph
  // at all, which is the honest unbiased baseline.
  const SherpaOnnxOfflineStream *stream =
      hotwords.empty()
          ? SherpaOnnxCreateOfflineStream(impl_->recognizer)
          : SherpaOnnxCreateOfflineStreamWithHotwords(impl_->recognizer,
                                                      hotwords.c_str());
  if (stream == nullptr) return fail("could not create decoding stream");

  SherpaOnnxAcceptWaveformOffline(stream, use->sample_rate, use->samples.data(),
                                  static_cast<int32_t>(use->samples.size()));
  SherpaOnnxDecodeOfflineStream(impl_->recognizer, stream);

  const SherpaOnnxOfflineRecognizerResult *r = SherpaOnnxGetOfflineStreamResult(stream);
  if (r == nullptr) {
    SherpaOnnxDestroyOfflineStream(stream);
    return fail("decoder returned no result");
  }

  out->text = r->text ? r->text : "";
  out->json = r->json ? r->json : "";
  out->tokens.clear();
  out->timestamps.clear();
  out->token_logprobs.clear();

  const int32_t n = std::max<int32_t>(0, r->count);
  if (r->tokens_arr) {
    out->tokens.reserve(static_cast<size_t>(n));
    for (int32_t i = 0; i < n; ++i) {
      out->tokens.push_back(r->tokens_arr[i] ? r->tokens_arr[i] : "");
    }
  }
  if (r->timestamps) out->timestamps.assign(r->timestamps, r->timestamps + n);
  if (r->ys_log_probs && n > 0) {
    out->token_logprobs.assign(r->ys_log_probs, r->ys_log_probs + n);
    out->has_logprobs = true;
    out->avg_logprob =
        std::accumulate(out->token_logprobs.begin(), out->token_logprobs.end(), 0.0f) /
        static_cast<float>(n);
    out->min_logprob =
        *std::min_element(out->token_logprobs.begin(), out->token_logprobs.end());
  } else {
    out->has_logprobs = false;
    out->avg_logprob = 0.0f;
    out->min_logprob = 0.0f;
  }

  SherpaOnnxDestroyOfflineRecognizerResult(r);
  SherpaOnnxDestroyOfflineStream(stream);

  out->decode_ms = timer.ElapsedMs();
  out->audio_s = use->duration_s();
  VCC_DEBUG << "decoded " << out->audio_s << "s in " << out->decode_ms << " ms (rtf "
            << out->rtf() << ", biasing " << (hotwords.empty() ? "off" : "on")
            << "): '" << out->text << "'";
  return true;
}

}  // namespace vcc
