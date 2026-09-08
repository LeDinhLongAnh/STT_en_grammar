// vcc_cli -- headless front-end: decode WAV files both ways, and measure
// whether the filter actually helps.
//
// The measurement is the point. "Biasing makes it better" is an impression
// until it is a word error rate against a reference somebody typed in, so
// --eval is the tool this project lives or dies by.
#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <map>
#include <string>
#include <vector>

#include "vcc/core.h"
#include "vcc/json.h"
#include "vcc/log.h"
#include "vcc/pipeline.h"

namespace {

using namespace vcc;

void PrintUsage() {
  std::printf(R"(vcc_cli - contextual-biasing STT, raw vs filtered

USAGE
  vcc_cli [options] <file.wav> [more.wav ...]
  vcc_cli --eval tests/data/manifest.tsv
  vcc_cli --list-models

OPTIONS
  --model <id>        model to load (default: config asr.model, else best available)
  --precision <p>     int8 | fp32 | auto
  --eval <manifest>   measure WER over a TSV of "<wav>\t<reference transcript>"
  --min-gain <pct>    with --eval: exit 2 unless WER improves by at least this much
  --no-biasing        skip stage 1 (both outputs unbiased)
  --no-rewrites       skip stage 2 (filtered = biased)
  --normalize         peak-normalise input audio before decoding
  --json              machine-readable output
  --list-models       show the model registry and exit
  --show-hotwords     print the serialised hotword string and exit
  --root <dir>        project root (default: autodetected)
  --set key=value     override any config/app.ini key (repeatable)
  --quiet             errors only
  -h, --help          this text

EXIT STATUS
  0  success
  1  usage or runtime error
  2  --eval ran but the filter did not meet --min-gain
)");
}

struct Args {
  std::string model, precision, root, eval_manifest;
  std::vector<std::string> wavs, sets;
  bool normalize = false;
  bool json = false;
  bool list_models = false;
  bool show_hotwords = false;
  bool quiet = false;
  bool no_biasing = false;
  bool no_rewrites = false;
  double min_gain = -1.0;
};

bool ParseArgs(int argc, char **argv, Args *a, std::string *error) {
  auto need = [&](int i, const char *what) {
    if (i + 1 >= argc) {
      *error = std::string("missing value after ") + what;
      return false;
    }
    return true;
  };
  for (int i = 1; i < argc; ++i) {
    const std::string arg = argv[i];
    if (arg == "-h" || arg == "--help") {
      PrintUsage();
      std::exit(0);
    } else if (arg == "--model") {
      if (!need(i, "--model")) return false;
      a->model = argv[++i];
    } else if (arg == "--precision") {
      if (!need(i, "--precision")) return false;
      a->precision = argv[++i];
    } else if (arg == "--eval") {
      if (!need(i, "--eval")) return false;
      a->eval_manifest = argv[++i];
    } else if (arg == "--min-gain") {
      if (!need(i, "--min-gain")) return false;
      a->min_gain = std::atof(argv[++i]);
    } else if (arg == "--root") {
      if (!need(i, "--root")) return false;
      a->root = argv[++i];
    } else if (arg == "--set") {
      if (!need(i, "--set")) return false;
      a->sets.push_back(argv[++i]);
    } else if (arg == "--no-biasing") {
      a->no_biasing = true;
    } else if (arg == "--no-rewrites") {
      a->no_rewrites = true;
    } else if (arg == "--normalize") {
      a->normalize = true;
    } else if (arg == "--json") {
      a->json = true;
    } else if (arg == "--list-models") {
      a->list_models = true;
    } else if (arg == "--show-hotwords") {
      a->show_hotwords = true;
    } else if (arg == "--quiet") {
      a->quiet = true;
    } else if (!arg.empty() && arg[0] == '-') {
      *error = "unknown option: " + arg;
      return false;
    } else {
      a->wavs.push_back(arg);
    }
  }
  return true;
}

// A compact inline diff: words only present in one side are bracketed.
std::string DiffLine(const std::vector<DiffSpan> &spans) {
  std::string out;
  for (const DiffSpan &s : spans) {
    if (!out.empty()) out += " ";
    switch (s.op) {
      case DiffOp::kEqual:      out += s.a; break;
      case DiffOp::kSubstitute: out += "[" + s.a + " -> " + s.b + "]"; break;
      case DiffOp::kDelete:     out += "[-" + s.a + "]"; break;
      case DiffOp::kInsert:     out += "[+" + s.b + "]"; break;
    }
  }
  return out;
}

void PrintComparison(const Comparison &c, const std::string &label) {
  std::printf("\n%s  (%.2fs, peak %.0f dBFS)\n", label.c_str(), c.raw.audio_s,
              c.levels.peak_dbfs);
  std::printf("  raw      : \"%s\"\n", c.raw.text.c_str());
  std::printf("  filtered : \"%s\"\n", c.filtered.c_str());
  if (c.changed) {
    std::printf("  diff     : %s\n", DiffLine(c.diff).c_str());
  } else {
    std::printf("  diff     : (no change)\n");
  }
  if (!c.rewrite_hits.empty()) {
    std::string rules;
    for (const RewriteHit &h : c.rewrite_hits) {
      if (!rules.empty()) rules += ", ";
      rules += h.from + " => " + h.to;
    }
    std::printf("  rules    : %s\n", rules.c_str());
  }
  std::printf("  timing   : raw %.0f ms, biased %.0f ms (rtf %.2f)\n",
              c.raw.decode_ms, c.biased.decode_ms, c.biased.rtf());
  if (c.has_reference) {
    std::printf("  reference: \"%s\"\n", c.reference.c_str());
    std::printf("  WER      : raw %.1f%%  ->  filtered %.1f%%\n",
                c.wer_raw.wer() * 100.0, c.wer_filtered.wer() * 100.0);
  }
  if (c.levels.peak_dbfs < -35.0f) {
    std::printf("  note     : very quiet input, move closer to the mic\n");
  }
  if (c.levels.clipped) {
    std::printf("  note     : input is clipping, lower the input gain\n");
  }
}

void WriteComparisonJson(JsonWriter *w, const Comparison &c) {
  w->BeginObject();
  w->Field("ok", c.ok);
  w->Field("error", c.error);
  w->Field("raw", c.raw.text);
  w->Field("biased", c.biased.text);
  w->Field("filtered", c.filtered);
  w->Field("changed", c.changed);
  w->Field("audio_s", c.raw.audio_s, 3);
  w->Field("raw_decode_ms", c.raw.decode_ms, 1);
  w->Field("biased_decode_ms", c.biased.decode_ms, 1);
  w->Field("rtf", c.biased.rtf(), 3);
  w->Field("peak_dbfs", c.levels.peak_dbfs, 1);
  w->Field("rms_dbfs", c.levels.rms_dbfs, 1);
  w->Key("diff").BeginArray();
  for (const DiffSpan &s : c.diff) {
    w->BeginObject();
    w->Field("op", std::string(DiffOpName(s.op)));
    w->Field("a", s.a);
    w->Field("b", s.b);
    w->End();
  }
  w->End();
  w->Key("rules").BeginArray();
  for (const RewriteHit &h : c.rewrite_hits) {
    w->BeginObject();
    w->Field("from", h.from);
    w->Field("to", h.to);
    w->End();
  }
  w->End();
  if (c.has_reference) {
    w->Field("reference", c.reference);
    w->Field("wer_raw", c.wer_raw.wer(), 4);
    w->Field("wer_filtered", c.wer_filtered.wer(), 4);
  }
  w->End();
}

int RunFiles(Pipeline *pipe, const Args &args) {
  int failures = 0;
  JsonWriter w;
  if (args.json) w.BeginArray();

  for (const std::string &path : args.wavs) {
    AudioBuffer audio;
    std::string err;
    if (!ReadWavFile(path, &audio, &err)) {
      VCC_ERROR << path << ": " << err;
      ++failures;
      continue;
    }
    if (args.normalize) NormalizePeak(&audio);

    // One file, one utterance. The corpus is recorded a phrase at a time
    // (vcc_listen writes one WAV per push-to-talk take), so there is nothing
    // to segment.
    const Comparison c = pipe->Process(audio);
    if (!c.ok) {
      VCC_ERROR << path << ": " << c.error;
      ++failures;
      continue;
    }
    if (args.json) {
      WriteComparisonJson(&w, c);
    } else {
      PrintComparison(c, PathBase(path));
    }
  }

  if (args.json) {
    w.End();
    std::printf("%s\n", w.str().c_str());
  }
  return failures == 0 ? 0 : 1;
}

// --- evaluation ------------------------------------------------------------

struct EvalRow {
  std::string wav;
  std::string reference;
};

bool LoadManifest(const std::string &path, std::vector<EvalRow> *rows,
                  std::string *error) {
  std::vector<std::string> lines;
  if (!ReadLines(path, &lines)) {
    *error = "cannot read manifest " + path;
    return false;
  }
  const std::string base = PathDir(path);
  for (size_t i = 0; i < lines.size(); ++i) {
    std::string line = lines[i];
    const size_t hash = line.find('#');
    if (hash != std::string::npos) line = line.substr(0, hash);
    line = Trim(line);
    if (line.empty()) continue;

    // Tab-separated, because a reference transcript contains spaces.
    const size_t tab = line.find('\t');
    if (tab == std::string::npos) {
      VCC_WARN << PathBase(path) << ":" << (i + 1)
               << ": need <wav>TAB<reference transcript>";
      continue;
    }
    EvalRow r;
    r.wav = PathJoin(base, Trim(line.substr(0, tab)));
    r.reference = Trim(line.substr(tab + 1));
    if (r.reference.empty()) {
      VCC_WARN << PathBase(path) << ":" << (i + 1) << ": empty reference, skipped";
      continue;
    }
    rows->push_back(std::move(r));
  }
  return !rows->empty();
}

int RunEval(Pipeline *pipe, const Args &args) {
  std::vector<EvalRow> rows;
  std::string err;
  if (!LoadManifest(args.eval_manifest, &rows, &err)) {
    VCC_ERROR << (err.empty() ? "manifest has no usable rows" : err);
    return 1;
  }

  ErrorRateAccumulator raw_acc, filtered_acc;
  size_t unreadable = 0;
  size_t improved = 0, worsened = 0, unchanged = 0;
  double total_decode_ms = 0.0;
  double total_audio_s = 0.0;
  std::map<std::string, int> fixes;    // substitutions the filter repaired
  std::map<std::string, int> breaks;   // ...and ones it introduced

  std::printf("\n%-30s %-7s %-7s %s\n", "clip", "raw", "filt", "transcript");
  std::printf("%s\n", std::string(100, '-').c_str());

  for (const EvalRow &r : rows) {
    AudioBuffer audio;
    if (!ReadWavFile(r.wav, &audio, &err)) {
      std::printf("%-30s %-7s %-7s MISSING FILE\n", PathBase(r.wav).c_str(), "-", "-");
      ++unreadable;
      continue;
    }
    if (args.normalize) NormalizePeak(&audio);

    const Comparison c = pipe->Process(audio, r.reference);
    if (!c.ok) {
      std::printf("%-30s %-7s %-7s %s\n", PathBase(r.wav).c_str(), "-", "-",
                  c.error.c_str());
      ++unreadable;
      continue;
    }
    raw_acc.Add(c.wer_raw);
    filtered_acc.Add(c.wer_filtered);
    total_decode_ms += c.raw.decode_ms + c.biased.decode_ms;
    total_audio_s += c.raw.audio_s;

    const double before = c.wer_raw.wer();
    const double after = c.wer_filtered.wer();
    const char *mark = "  ";
    if (after < before) {
      ++improved;
      mark = "<-";  // the filter helped
    } else if (after > before) {
      ++worsened;
      mark = "!!";  // the filter hurt -- these are the rows that matter
    } else {
      ++unchanged;
    }

    std::printf("%-30s %6.1f%% %6.1f%% %s %s\n", PathBase(r.wav).c_str(),
                before * 100.0, after * 100.0, mark, c.filtered.c_str());
    if (after != before) {
      std::printf("%-30s   raw: %s\n", "", c.raw.text.c_str());
      std::printf("%-30s   ref: %s\n", "", c.reference.c_str());
    }

    // Which word substitutions did the filter change, in either direction?
    for (const DiffSpan &s : DiffWords(c.raw.text, c.filtered)) {
      if (s.op != DiffOp::kSubstitute) continue;
      const std::vector<DiffSpan> vs_ref = DiffWords(c.reference, c.filtered);
      bool now_correct = true;
      for (const DiffSpan &t : vs_ref) {
        if (t.op == DiffOp::kSubstitute && t.b == s.b) now_correct = false;
      }
      (now_correct ? fixes : breaks)[s.a + " -> " + s.b]++;
    }
  }

  const double before = raw_acc.wer();
  const double after = filtered_acc.wer();
  const double gain = before > 0.0 ? (before - after) / before * 100.0 : 0.0;

  std::printf("\n%s\n", std::string(100, '=').c_str());
  std::printf("clips evaluated : %zu", raw_acc.clips);
  if (unreadable) std::printf("  (%zu unreadable)", unreadable);
  std::printf("\n");
  std::printf("reference words : %zu\n", raw_acc.total.ref_words);
  std::printf("\n");
  std::printf("WER raw         : %5.1f%%   (%zu sub, %zu del, %zu ins)\n",
              before * 100.0, raw_acc.total.substitutions, raw_acc.total.deletions,
              raw_acc.total.insertions);
  std::printf("WER filtered    : %5.1f%%   (%zu sub, %zu del, %zu ins)\n",
              after * 100.0, filtered_acc.total.substitutions,
              filtered_acc.total.deletions, filtered_acc.total.insertions);
  std::printf("relative gain   : %+5.1f%%   <-- the number this project exists for\n",
              gain);
  std::printf("\n");
  std::printf("clips improved  : %zu\n", improved);
  std::printf("clips unchanged : %zu\n", unchanged);
  std::printf("clips worsened  : %zu   <-- drive this to zero before chasing gain\n",
              worsened);
  if (total_audio_s > 0) {
    std::printf("mean rtf        : %.3f  (both decodes, %.0f ms per clip)\n",
                (total_decode_ms / 1000.0) / total_audio_s,
                raw_acc.clips ? total_decode_ms / raw_acc.clips : 0.0);
  }

  auto dump = [](const char *title, const std::map<std::string, int> &m) {
    if (m.empty()) return;
    std::vector<std::pair<std::string, int>> v(m.begin(), m.end());
    std::sort(v.begin(), v.end(),
              [](const std::pair<std::string, int> &a,
                 const std::pair<std::string, int> &b) { return a.second > b.second; });
    std::printf("\n%s\n", title);
    for (const auto &e : v) std::printf("  %3dx  %s\n", e.second, e.first.c_str());
  };
  dump("substitutions the filter fixed:", fixes);
  dump("substitutions the filter introduced (look here first):", breaks);
  std::printf("\n");

  if (args.min_gain >= 0.0 && gain < args.min_gain) {
    VCC_ERROR << "relative WER gain " << gain << "% below required " << args.min_gain
              << "%";
    return 2;
  }
  return 0;
}

}  // namespace

int main(int argc, char **argv) {
  SetLogColor(false);

  Args args;
  std::string error;
  if (!ParseArgs(argc, argv, &args, &error)) {
    std::fprintf(stderr, "error: %s\n\n", error.c_str());
    PrintUsage();
    return 1;
  }
  if (args.quiet) SetLogLevel(LogLevel::kError);

  Pipeline pipe;
  if (!pipe.Init(args.root, args.sets, &error)) {
    std::fprintf(stderr, "error: %s\n", error.c_str());
    return 1;
  }
  if (args.no_biasing) pipe.set_biasing_enabled(false);
  if (args.no_rewrites) pipe.set_rewrites_enabled(false);

  if (args.list_models) {
    std::printf("sherpa-onnx %s\nmodels dir: %s\n\n",
                AsrEngine::SherpaVersion().c_str(), pipe.paths().models_dir.c_str());
    if (pipe.registry().models().empty()) {
      std::printf("  (none) - run scripts/download_models.sh\n");
      return 1;
    }
    for (const ModelProfile &m : pipe.registry().models()) {
      std::printf("  %-56s %s\n", m.id.c_str(), m.Describe().c_str());
      if (!m.hotwords_blocker.empty()) {
        std::printf("  %-56s   ! %s\n", "", m.hotwords_blocker.c_str());
      }
    }
    return 0;
  }

  if (args.wavs.empty() && args.eval_manifest.empty() && !args.show_hotwords) {
    std::fprintf(stderr, "error: nothing to do\n\n");
    PrintUsage();
    return 1;
  }

  if (!pipe.LoadModel(args.model, args.precision, &error)) {
    std::fprintf(stderr, "error: %s\n", error.c_str());
    return 1;
  }

  if (args.show_hotwords) {
    std::vector<std::string> warnings;
    const std::string wire = pipe.SerializedHotwords(&warnings);
    for (const std::string &w : warnings) std::fprintf(stderr, "warning: %s\n", w.c_str());
    // One phrase per line for reading; '/' is the on-the-wire separator.
    for (const std::string &phrase : Split(wire, '/', true)) {
      std::printf("%s\n", phrase.c_str());
    }
    std::fprintf(stderr, "\n%zu phrase(s) at boost %.1f, biasing %s\n",
                 pipe.hotwords().size(), pipe.asr().options().hotwords_score,
                 wire.empty() ? "INACTIVE" : "active");
    if (!pipe.asr().biasing_available()) {
      std::fprintf(stderr, "biasing unavailable: %s\n",
                   pipe.asr().biasing_blocker().c_str());
    }
    return 0;
  }

  if (!args.json) {
    std::printf("model    : %s (%s)\n", pipe.asr().profile().id.c_str(),
                pipe.asr().profile().Describe().c_str());
    std::printf("biasing  : %s", pipe.biasing_enabled() && pipe.asr().biasing_available()
                                     ? "on" : "off");
    if (pipe.biasing_enabled() && pipe.asr().biasing_available()) {
      std::printf(" (%zu phrases at boost %.1f)", pipe.hotwords().size(),
                  pipe.asr().options().hotwords_score);
    } else if (!pipe.asr().biasing_available()) {
      std::printf(" - %s", pipe.asr().biasing_blocker().c_str());
    }
    std::printf("\nrewrites : %s (%zu rules)\n",
                pipe.rewrites_enabled() ? "on" : "off", pipe.rewrites().size());
  }

  int rc = 0;
  if (!args.eval_manifest.empty()) rc = RunEval(&pipe, args);
  if (!args.wavs.empty()) {
    const int r = RunFiles(&pipe, args);
    if (rc == 0) rc = r;
  }
  return rc;
}
