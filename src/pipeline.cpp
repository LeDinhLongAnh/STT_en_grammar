#include "vcc/pipeline.h"

#include "vcc/core.h"
#include "vcc/log.h"

namespace vcc {

Pipeline::Pipeline() = default;
Pipeline::~Pipeline() = default;

bool Pipeline::Init(const std::string &explicit_root,
                    const std::vector<std::string> &overrides, std::string *error) {
  auto fail = [&](const std::string &m) {
    if (error) *error = m;
    return false;
  };
  warnings_.clear();

  std::string root = NormalizeSlashes(Trim(explicit_root));
  if (root.empty()) root = FindProjectRoot(ExecutableDir(), "config/app.ini");
  if (root.empty()) root = FindProjectRoot(".", "config/app.ini");
  if (root.empty()) {
    return fail("cannot find the project root (looked for config/app.ini next to " +
                ExecutableDir() + " and in the current directory); pass --root <dir>");
  }
  paths_.root = root;

  const std::string ini = PathJoin(root, "config/app.ini");
  if (!config_.LoadFile(ini, &warnings_)) return fail("cannot read " + ini);
  for (const std::string &kv : overrides) {
    if (!config_.SetFromAssignment(kv)) {
      return fail("bad --set argument (expected key=value): " + kv);
    }
  }

  SetLogLevel(ParseLogLevel(config_.GetString("log.level", "info")));

  paths_.models_dir = config_.GetPath("paths.models_dir", root, "models");
  paths_.hotwords = config_.GetPath("paths.hotwords", root, "config/hotwords.txt");
  paths_.rewrites = config_.GetPath("paths.rewrites", root, "config/rewrites.txt");

  biasing_enabled_ = config_.GetBool("filter.biasing", true);
  rewrites_enabled_ = config_.GetBool("filter.rewrites", true);

  // The hotword list is the point of the project: an empty one is worth saying
  // out loud rather than quietly producing two identical transcripts.
  if (!hotwords_.LoadFile(paths_.hotwords, &warnings_)) {
    warnings_.push_back("no hotword list at " + paths_.hotwords +
                        " - biasing will have nothing to bias towards");
  } else if (hotwords_.empty()) {
    warnings_.push_back(PathBase(paths_.hotwords) +
                        " is empty - biasing will have no effect");
  }

  // Rewrites are optional; the compiled-in defaults are a working baseline.
  rewrites_ = RewriteTable::Default();
  if (FileExists(paths_.rewrites)) {
    RewriteTable from_file;
    if (from_file.LoadFile(paths_.rewrites, &warnings_)) {
      rewrites_ = std::move(from_file);
    } else {
      warnings_.push_back("could not read " + paths_.rewrites + ", using defaults");
    }
  }

  std::vector<std::string> problems;
  registry_.Scan(paths_.models_dir, &problems);
  for (const std::string &p : problems) warnings_.push_back("models: " + p);
  if (registry_.models().empty()) {
    warnings_.push_back("no usable models found in " + paths_.models_dir +
                        " - run scripts/download_models.sh");
  }

  for (const std::string &w : warnings_) VCC_WARN << w;
  return true;
}

AsrOptions Pipeline::AsrOptionsFromConfig() const {
  AsrOptions o;
  o.num_threads = config_.GetInt("asr.num_threads", o.num_threads);
  o.decoding_method = config_.GetString("asr.decoding_method", o.decoding_method);
  o.max_active_paths = config_.GetInt("asr.max_active_paths", o.max_active_paths);
  o.hotwords_score = config_.GetFloat("asr.hotwords_score", o.hotwords_score);
  o.blank_penalty = config_.GetFloat("asr.blank_penalty", o.blank_penalty);
  o.debug = config_.GetBool("asr.debug", o.debug);
  o.provider = config_.GetString("asr.provider", "cpu");
  return o;
}

bool Pipeline::LoadModel(const std::string &model_id, const std::string &precision,
                         std::string *error) {
  auto fail = [&](const std::string &m) {
    if (error) *error = m;
    return false;
  };

  const std::string want_id =
      model_id.empty() ? config_.GetString("asr.model", "") : model_id;
  const std::string want_prec =
      precision.empty() ? config_.GetString("asr.precision", "auto") : precision;

  const ModelProfile *profile = registry_.Resolve(want_id, want_prec);
  if (profile == nullptr) {
    if (registry_.models().empty()) {
      return fail("no models installed in " + paths_.models_dir +
                  " - run scripts/download_models.sh");
    }
    std::string known;
    for (const ModelProfile &m : registry_.models()) {
      if (!known.empty()) known += ", ";
      known += m.id;
    }
    return fail("no model matches '" + want_id + "' at precision '" + want_prec +
                "'. Available: " + known);
  }
  return asr_.Load(*profile, AsrOptionsFromConfig(), error);
}

std::string Pipeline::SerializedHotwords(std::vector<std::string> *warnings) const {
  if (!biasing_enabled_) return std::string();
  if (!asr_.biasing_available()) return std::string();
  return hotwords_.Serialize(AsrOptionsFromConfig().hotwords_score, warnings);
}

bool Pipeline::SaveHotwords(std::string *error) const {
  if (WriteFile(paths_.hotwords, hotwords_.ToText())) return true;
  if (error) *error = "cannot write " + paths_.hotwords;
  return false;
}

bool Pipeline::SaveRewrites(std::string *error) const {
  if (WriteFile(paths_.rewrites, rewrites_.ToText())) return true;
  if (error) *error = "cannot write " + paths_.rewrites;
  return false;
}

bool Pipeline::ReloadDataFiles(std::string *error) {
  HotwordList hw;
  if (!hw.LoadFile(paths_.hotwords, &warnings_)) {
    if (error) *error = "cannot read " + paths_.hotwords;
    return false;
  }
  RewriteTable rw = RewriteTable::Default();
  if (FileExists(paths_.rewrites)) {
    RewriteTable from_file;
    if (from_file.LoadFile(paths_.rewrites, &warnings_)) rw = std::move(from_file);
  }
  hotwords_ = std::move(hw);
  rewrites_ = std::move(rw);
  return true;
}

void Pipeline::ReapplyRewrites(Comparison *c) const {
  c->rewrite_hits.clear();
  c->filtered = rewrites_enabled_
                    ? rewrites_.Apply(c->biased.text, &c->rewrite_hits)
                    : c->biased.text;
  c->diff = DiffWords(c->raw.text, c->filtered);
  c->changed = TranscriptsDiffer(c->raw.text, c->filtered);
  if (c->has_reference) {
    c->wer_raw = ComputeWer(c->reference, c->raw.text);
    c->wer_filtered = ComputeWer(c->reference, c->filtered);
  }
}

Comparison Pipeline::Process(const AudioBuffer &audio,
                             const std::string &reference) const {
  Comparison c;
  Timer timer;

  c.levels = MeasureLevels(audio);
  if (!asr_.loaded()) {
    c.error = "no model loaded";
    return c;
  }
  if (audio.samples.empty()) {
    c.error = "empty audio";
    return c;
  }

  std::string err;

  // Baseline first: what the recogniser says with no help at all.
  if (!asr_.Recognize(audio, std::string(), &c.raw, &err)) {
    c.error = "unbiased decode failed: " + err;
    return c;
  }

  // Then the same audio, same model, with the hotword list pushed into the
  // decoder. An empty serialisation means biasing is off or unavailable, in
  // which case the second decode would be identical -- skip it and say so by
  // reusing the first result.
  const std::string hotwords = SerializedHotwords();
  if (hotwords.empty()) {
    c.biased = c.raw;
  } else if (!asr_.Recognize(audio, hotwords, &c.biased, &err)) {
    c.error = "biased decode failed: " + err;
    return c;
  }

  if (!reference.empty()) {
    c.has_reference = true;
    c.reference = reference;
  }
  ReapplyRewrites(&c);

  c.total_ms = timer.ElapsedMs();
  c.ok = true;
  return c;
}

}  // namespace vcc
