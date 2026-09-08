// vcc_listen -- push-to-talk recorder: speak one phrase, see raw vs filtered.
//
// Press Enter, say the phrase, press Enter again. There is no voice-activity
// detector: this project is about what the recogniser does with the audio, not
// about finding the audio, and an endpointer in the middle only adds a variable
// that has nothing to do with the accent problem. It also means every clip has
// exactly the boundaries you chose, which is what you want when the clip is
// going into an evaluation corpus.
//
// --save-dir writes one WAV per take. That is how the corpus in tests/data gets
// built.
#include <atomic>
#include <chrono>
#include <cstdio>
#include <iostream>
#include <string>
#include <thread>
#include <vector>

#include "vcc/audio.h"
#include "vcc/core.h"
#include "vcc/log.h"
#include "vcc/pipeline.h"

namespace {

using namespace vcc;

void PrintUsage() {
  std::printf(R"(vcc_listen - push-to-talk contextual-biasing STT

USAGE
  vcc_listen [options]

  Press Enter to start recording, Enter again to stop and decode.
  Type 'q' then Enter to quit.

OPTIONS
  --list-mics          enumerate capture devices and exit
  --mic <index>        capture device index (default: config audio.mic_index)
  --model <id>         model to load
  --precision <p>      int8 | fp32 | auto
  --no-biasing         skip stage 1 (both outputs unbiased)
  --no-rewrites        skip stage 2 (filtered = biased)
  --save-dir <dir>     write every take as a WAV, for the evaluation corpus
  --root <dir>         project root
  --set key=value      override a config/app.ini key (repeatable)
  --quiet              errors only
  -h, --help           this text
)");
}

struct Args {
  std::string model, precision, root, save_dir;
  std::vector<std::string> sets;
  int mic = -2;  // -2 = not specified, -1 = system default
  bool list_mics = false;
  bool quiet = false;
  bool no_biasing = false;
  bool no_rewrites = false;
};

bool ParseArgs(int argc, char **argv, Args *a, std::string *error) {
  for (int i = 1; i < argc; ++i) {
    const std::string arg = argv[i];
    auto value = [&](const char *what) -> std::string {
      if (i + 1 >= argc) {
        *error = std::string("missing value after ") + what;
        return std::string();
      }
      return argv[++i];
    };
    if (arg == "-h" || arg == "--help") {
      PrintUsage();
      std::exit(0);
    } else if (arg == "--list-mics") {
      a->list_mics = true;
    } else if (arg == "--mic") {
      const std::string v = value("--mic");
      if (v.empty()) return false;
      if (!ParseInt(v, &a->mic)) {
        *error = "--mic expects an integer";
        return false;
      }
    } else if (arg == "--model") {
      a->model = value("--model");
    } else if (arg == "--precision") {
      a->precision = value("--precision");
    } else if (arg == "--save-dir") {
      a->save_dir = value("--save-dir");
    } else if (arg == "--root") {
      a->root = value("--root");
    } else if (arg == "--set") {
      const std::string v = value("--set");
      if (v.empty()) return false;
      a->sets.push_back(v);
    } else if (arg == "--no-biasing") {
      a->no_biasing = true;
    } else if (arg == "--no-rewrites") {
      a->no_rewrites = true;
    } else if (arg == "--quiet") {
      a->quiet = true;
    } else {
      *error = "unknown argument: " + arg;
      return false;
    }
    if (!error->empty()) return false;
  }
  return true;
}

void ListMics() {
  std::string err;
  const std::vector<AudioDevice> devices = ListCaptureDevices(&err);
  std::printf("audio backend: %s\n", AudioBackendName());
  if (devices.empty()) {
    std::printf("no capture devices%s%s\n", err.empty() ? "" : ": ", err.c_str());
    return;
  }
  std::printf("\n%-5s %-9s %-8s %s\n", "index", "rate", "channels", "name");
  std::printf("%s\n", std::string(78, '-').c_str());
  for (const AudioDevice &d : devices) {
    std::printf("%-5d %-9d %-8d %s%s\n", d.index, d.sample_rate, d.channels,
                d.name.c_str(), d.is_default ? "  (default)" : "");
  }
  std::printf("\nuse:  vcc_listen --mic <index>\n");
}

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

// Drains the capture ring buffer into `out` until `stop` is set, printing a
// live level readout so the speaker can see the mic is hearing them.
void RecordUntil(AudioCapture *capture, const std::atomic<bool> &stop,
                 size_t max_samples, AudioBuffer *out) {
  std::vector<float> chunk(2048);
  out->samples.clear();
  out->sample_rate = capture->sample_rate();

  auto last_print = std::chrono::steady_clock::now();
  while (!stop) {
    const size_t n = capture->Read(chunk.data(), chunk.size());
    if (n == 0) {
      std::this_thread::sleep_for(std::chrono::milliseconds(10));
      continue;
    }
    out->samples.insert(out->samples.end(), chunk.begin(), chunk.begin() + n);
    if (out->samples.size() >= max_samples) {
      std::printf("\n  (hit the %.0fs recording cap)\n",
                  static_cast<double>(max_samples) / out->sample_rate);
      return;
    }
    const auto now = std::chrono::steady_clock::now();
    if (now - last_print > std::chrono::milliseconds(150)) {
      last_print = now;
      AudioBuffer window;
      window.sample_rate = out->sample_rate;
      window.samples.assign(chunk.begin(), chunk.begin() + n);
      const LevelStats st = MeasureLevels(window);
      const int bars = static_cast<int>((st.peak_dbfs + 60.0f) / 60.0f * 30.0f);
      std::printf("\r  recording %5.1fs  [%-30s] %5.1f dBFS ",
                  out->duration_s(),
                  std::string(std::max(0, std::min(30, bars)), '#').c_str(),
                  st.peak_dbfs);
      std::fflush(stdout);
    }
  }
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
  if (args.list_mics) {
    ListMics();
    return 0;
  }

  Pipeline pipe;
  if (!pipe.Init(args.root, args.sets, &error)) {
    std::fprintf(stderr, "error: %s\n", error.c_str());
    return 1;
  }
  if (args.no_biasing) pipe.set_biasing_enabled(false);
  if (args.no_rewrites) pipe.set_rewrites_enabled(false);

  if (!pipe.LoadModel(args.model, args.precision, &error)) {
    std::fprintf(stderr, "error: %s\n", error.c_str());
    return 1;
  }

  CaptureOptions copts;
  copts.sample_rate = pipe.config().GetInt("audio.sample_rate", 16000);
  copts.device_index =
      args.mic == -2 ? pipe.config().GetInt("audio.mic_index", -1) : args.mic;
  // Deep enough that a decode cannot cause a dropout mid-take.
  copts.buffer_seconds = 70.0f;

  std::unique_ptr<AudioCapture> capture = AudioCapture::Create();
  if (!capture->Start(copts, &error)) {
    std::fprintf(stderr, "error: %s\n\nTry: vcc_listen --list-mics\n", error.c_str());
    return 1;
  }

  const bool biasing_on = pipe.biasing_enabled() && pipe.asr().biasing_available();
  std::printf("\nmodel    : %s\n", pipe.asr().profile().id.c_str());
  std::printf("biasing  : %s", biasing_on ? "on" : "off");
  if (biasing_on) {
    std::printf(" (%zu phrases at boost %.1f)", pipe.hotwords().size(),
                pipe.asr().options().hotwords_score);
  } else if (!pipe.asr().biasing_available()) {
    std::printf(" - %s", pipe.asr().biasing_blocker().c_str());
  }
  std::printf("\nrewrites : %s (%zu rules)\n", pipe.rewrites_enabled() ? "on" : "off",
              pipe.rewrites().size());
  std::printf("mic      : %s (%d Hz)\n", capture->device().name.c_str(),
              capture->sample_rate());
  if (!args.save_dir.empty()) {
    std::printf("saving   : %s\n", args.save_dir.c_str());
  }
  std::printf("\nEnter to start recording, Enter again to stop. 'q' to quit.\n");

  const double max_record_s = pipe.config().GetFloat("audio.max_record_s", 60.0f);
  const size_t max_samples =
      static_cast<size_t>(max_record_s * capture->sample_rate());

  int take = 0;
  int changed_count = 0;
  std::string line;

  while (true) {
    std::printf("\n[%d] ready > ", take + 1);
    std::fflush(stdout);
    if (!std::getline(std::cin, line)) break;
    if (!line.empty() && (line[0] == 'q' || line[0] == 'Q')) break;

    // Drop whatever accumulated while we were waiting, so the take starts now.
    std::vector<float> flush(4096);
    while (capture->Read(flush.data(), flush.size()) > 0) {
    }

    std::atomic<bool> stop {false};
    AudioBuffer audio;
    std::thread recorder([&] { RecordUntil(capture.get(), stop, max_samples, &audio); });
    std::getline(std::cin, line);
    stop = true;
    recorder.join();
    std::printf("\r%-70s\r", "");

    if (audio.samples.empty()) {
      std::printf("  nothing recorded\n");
      continue;
    }
    ++take;

    const Comparison c = pipe.Process(audio);
    std::printf("  %.2fs, peak %.0f dBFS\n", audio.duration_s(), c.levels.peak_dbfs);
    if (!c.ok) {
      std::printf("  error    : %s\n", c.error.c_str());
      continue;
    }
    std::printf("  raw      : \"%s\"\n", c.raw.text.c_str());
    std::printf("  filtered : \"%s\"\n", c.filtered.c_str());
    if (c.changed) {
      ++changed_count;
      std::printf("  diff     : %s\n", DiffLine(c.diff).c_str());
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
    if (c.levels.peak_dbfs < -35.0f) {
      std::printf("  note     : very quiet, move closer to the mic\n");
    }
    if (c.levels.clipped) {
      std::printf("  note     : clipping, lower the input gain\n");
    }

    if (!args.save_dir.empty()) {
      char name[64];
      std::snprintf(name, sizeof(name), "take-%04d.wav", take);
      const std::string path = PathJoin(args.save_dir, name);
      if (WriteWavFile(path, audio)) {
        std::printf("  saved    : %s\n", path.c_str());
        std::printf("             add a line to your manifest:\n");
        std::printf("             %s\t<what you actually said>\n", name);
      } else {
        std::printf("  could not write %s (does the directory exist?)\n", path.c_str());
      }
    }
  }

  capture->Stop();
  std::printf("\n%d take(s), the filter changed %d of them\n", take, changed_count);
  if (capture->overruns() > 0) {
    std::printf("note: %llu samples were dropped during capture\n",
                static_cast<unsigned long long>(capture->overruns()));
  }
  return 0;
}
