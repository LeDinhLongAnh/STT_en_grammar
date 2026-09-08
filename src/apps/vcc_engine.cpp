// vcc_engine -- the API server behind the PyQt5 dashboard.
//
// It owns the model, the microphone and the filter, and exposes them over HTTP
// plus server-sent events on localhost. The dashboard in dashboard/ is a client;
// nothing here renders anything.
//
// Two things make this more than a thin REST wrapper:
//
//   * It keeps the audio of recent utterances in memory. Changing the hotword
//     list or the rewrite rules re-decodes what you already said, so tuning
//     does not require repeating yourself. That is the entire point of the tool.
//   * Because hotwords are per-decode, that re-decode needs no model reload.
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <csignal>
#include <cstdio>
#include <deque>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

#include "vcc/audio.h"
#include "vcc/core.h"
#include "vcc/http.h"
#include "vcc/json.h"
#include "vcc/log.h"
#include "vcc/pipeline.h"

namespace {

using namespace vcc;

std::atomic<bool> g_stop {false};
HttpServer *g_server = nullptr;

void OnSignal(int) {
  g_stop = true;
  if (g_server) g_server->Stop();
}

// --- event bus -------------------------------------------------------------
// One producer (the recording thread), a handful of SSE consumers. Each consumer
// gets its own bounded queue: a slow client must not stall audio capture.
class EventBus {
 public:
  class Subscription {
   public:
    explicit Subscription(EventBus *bus) : bus_(bus) { bus_->Attach(this); }
    ~Subscription() { bus_->Detach(this); }

    bool Next(std::string *event, std::string *data, int timeout_ms) {
      std::unique_lock<std::mutex> lock(mu_);
      if (!cv_.wait_for(lock, std::chrono::milliseconds(timeout_ms),
                        [this] { return !queue_.empty() || closed_; })) {
        return false;
      }
      if (queue_.empty()) return false;
      *event = queue_.front().first;
      *data = queue_.front().second;
      queue_.pop_front();
      return true;
    }

    void Push(const std::string &event, const std::string &data) {
      std::lock_guard<std::mutex> lock(mu_);
      if (queue_.size() > 256) queue_.pop_front();  // drop oldest, never block
      queue_.emplace_back(event, data);
      cv_.notify_one();
    }

    void Close() {
      std::lock_guard<std::mutex> lock(mu_);
      closed_ = true;
      cv_.notify_all();
    }

   private:
    EventBus *bus_;
    std::mutex mu_;
    std::condition_variable cv_;
    std::deque<std::pair<std::string, std::string>> queue_;
    bool closed_ = false;
  };

  void Publish(const std::string &event, const std::string &data) {
    std::lock_guard<std::mutex> lock(mu_);
    for (Subscription *s : subs_) s->Push(event, data);
  }

  void CloseAll() {
    std::lock_guard<std::mutex> lock(mu_);
    for (Subscription *s : subs_) s->Close();
  }

 private:
  void Attach(Subscription *s) {
    std::lock_guard<std::mutex> lock(mu_);
    subs_.push_back(s);
  }
  void Detach(Subscription *s) {
    std::lock_guard<std::mutex> lock(mu_);
    subs_.erase(std::remove(subs_.begin(), subs_.end(), s), subs_.end());
  }

  mutable std::mutex mu_;
  std::vector<Subscription *> subs_;
};

// --- utterance history -----------------------------------------------------
// Holding the audio is what makes "edit hotwords, see the effect on what I just
// said" possible. Bounded, because 16 kHz mono float is 64 KB per second and an
// afternoon of tuning would otherwise grow without limit.
struct Utterance {
  int index = 0;
  std::string source;   // "mic" or a filename
  double start_s = 0.0;
  AudioBuffer audio;
  Comparison result;
};

class History {
 public:
  explicit History(size_t cap) : cap_(cap) {}

  int Add(Utterance u) {
    std::lock_guard<std::mutex> lock(mu_);
    u.index = ++counter_;
    items_.push_back(std::move(u));
    while (items_.size() > cap_) items_.pop_front();
    return counter_;
  }

  // Re-decodes everything held, under whatever the filter settings are now.
  size_t Redecode(const Pipeline &pipe) {
    std::lock_guard<std::mutex> lock(mu_);
    for (Utterance &u : items_) {
      u.result = pipe.Process(u.audio, u.result.reference);
    }
    return items_.size();
  }

  // Cheap version: only the text stage changed, so the decodes still stand.
  size_t ReapplyRewrites(const Pipeline &pipe) {
    std::lock_guard<std::mutex> lock(mu_);
    for (Utterance &u : items_) {
      if (u.result.ok) pipe.ReapplyRewrites(&u.result);
    }
    return items_.size();
  }

  template <typename F>
  void ForEach(F fn) const {
    std::lock_guard<std::mutex> lock(mu_);
    for (const Utterance &u : items_) fn(u);
  }

  void Clear() {
    std::lock_guard<std::mutex> lock(mu_);
    items_.clear();
  }

  size_t size() const {
    std::lock_guard<std::mutex> lock(mu_);
    return items_.size();
  }

 private:
  mutable std::mutex mu_;
  std::deque<Utterance> items_;
  size_t cap_;
  int counter_ = 0;
};

// --- serialisation ---------------------------------------------------------

void WriteAsr(JsonWriter *w, const AsrResult &a) {
  w->BeginObject();
  w->Field("text", a.text);
  w->Field("decode_ms", a.decode_ms, 1);
  w->Field("rtf", a.rtf(), 3);
  w->Field("has_logprobs", a.has_logprobs);
  w->Field("avg_logprob", a.avg_logprob, 3);
  w->Field("min_logprob", a.min_logprob, 3);
  w->Key("tokens").BeginArray();
  for (const std::string &t : a.tokens) w->String(t);
  w->End();
  w->End();
}

void WriteComparison(JsonWriter *w, const Comparison &c) {
  w->BeginObject();
  w->Field("ok", c.ok);
  w->Field("error", c.error);
  w->Key("raw");
  WriteAsr(w, c.raw);
  w->Key("biased");
  WriteAsr(w, c.biased);
  w->Field("filtered", c.filtered);
  w->Field("changed", c.changed);
  w->Field("audio_s", c.raw.audio_s, 3);
  w->Field("total_ms", c.total_ms, 1);
  w->Field("peak_dbfs", c.levels.peak_dbfs, 1);
  w->Field("rms_dbfs", c.levels.rms_dbfs, 1);
  w->Field("clipped", c.levels.clipped);

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

  w->Field("has_reference", c.has_reference);
  if (c.has_reference) {
    w->Field("reference", c.reference);
    w->Field("wer_raw", c.wer_raw.wer(), 4);
    w->Field("wer_filtered", c.wer_filtered.wer(), 4);
  }
  w->End();
}

void WriteUtterance(JsonWriter *w, const Utterance &u) {
  w->BeginObject();
  w->Field("index", u.index);
  w->Field("source", u.source);
  w->Field("start_s", u.start_s, 2);
  w->Key("result");
  WriteComparison(w, u.result);
  w->End();
}

// --- the recorder ----------------------------------------------------------
//
// Push-to-talk, not voice-activity detection. This project is about what the
// recogniser does with the audio, and an endpointer in the middle adds a
// variable that has nothing to do with the accent problem. It also means every
// clip has exactly the boundaries the speaker chose, which matters when the clip
// goes into an evaluation corpus.

class Recorder {
 public:
  Recorder(Pipeline *pipe, EventBus *bus, History *history)
      : pipe_(pipe), bus_(bus), history_(history) {}
  ~Recorder() { Cancel(); }

  bool Start(int mic_index, std::string *error) {
    Cancel();
    CaptureOptions opts;
    opts.sample_rate = pipe_->config().GetInt("audio.sample_rate", 16000);
    opts.device_index = mic_index;
    // Deep enough that a decode cannot cause a dropout mid-take.
    opts.buffer_seconds = 70.0f;

    capture_ = AudioCapture::Create();
    if (!capture_->Start(opts, error)) {
      capture_.reset();
      return false;
    }
    max_samples_ = static_cast<size_t>(
        pipe_->config().GetFloat("audio.max_record_s", 60.0f) *
        static_cast<float>(capture_->sample_rate()));
    {
      std::lock_guard<std::mutex> lock(mu_);
      buffer_.samples.clear();
      buffer_.sample_rate = capture_->sample_rate();
    }
    stop_ = false;
    recording_ = true;
    mic_index_ = mic_index;
    mic_name_ = capture_->device().name;
    thread_ = std::thread(&Recorder::Run, this);
    return true;
  }

  // Stops capture and decodes what was recorded. Returns the history index, or
  // -1 when nothing usable was captured.
  int StopAndDecode(std::string *error) {
    if (!recording_) {
      if (error) *error = "not recording";
      return -1;
    }
    Join();

    AudioBuffer audio;
    {
      std::lock_guard<std::mutex> lock(mu_);
      audio = std::move(buffer_);
      buffer_ = AudioBuffer();
    }
    if (audio.samples.empty()) {
      if (error) *error = "nothing was recorded";
      return -1;
    }

    Utterance u;
    u.source = "mic";
    u.result = pipe_->Process(audio);
    u.audio = std::move(audio);
    return history_->Add(std::move(u));
  }

  // Throws the take away without decoding it.
  void Cancel() {
    Join();
    std::lock_guard<std::mutex> lock(mu_);
    buffer_ = AudioBuffer();
  }

  bool recording() const { return recording_; }
  int mic_index() const { return mic_index_; }
  const std::string &mic_name() const { return mic_name_; }

  double recorded_s() const {
    std::lock_guard<std::mutex> lock(mu_);
    return buffer_.duration_s();
  }

 private:
  void Join() {
    if (thread_.joinable()) {
      stop_ = true;
      thread_.join();
    }
    if (capture_) {
      capture_->Stop();
      capture_.reset();
    }
    recording_ = false;
  }

  void Run() {
    std::vector<float> chunk(1600);  // 100 ms at 16 kHz
    auto last_level = std::chrono::steady_clock::now();

    while (!stop_) {
      const size_t n = capture_->Read(chunk.data(), chunk.size());
      if (n == 0) {
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
        continue;
      }
      bool full = false;
      {
        std::lock_guard<std::mutex> lock(mu_);
        buffer_.samples.insert(buffer_.samples.end(), chunk.begin(),
                               chunk.begin() + n);
        full = buffer_.samples.size() >= max_samples_;
      }

      // Level meter at ~10 Hz: enough to see the mic is alive without flooding
      // the event stream.
      const auto now = std::chrono::steady_clock::now();
      if (now - last_level > std::chrono::milliseconds(100)) {
        last_level = now;
        AudioBuffer window;
        window.sample_rate = capture_->sample_rate();
        window.samples.assign(chunk.begin(), chunk.begin() + n);
        const LevelStats st = MeasureLevels(window);
        JsonWriter w;
        w.BeginObject();
        w.Field("peak_dbfs", st.peak_dbfs, 1);
        w.Field("rms_dbfs", st.rms_dbfs, 1);
        w.Field("clipped", st.clipped);
        w.Field("overruns", static_cast<long long>(capture_->overruns()));
        w.Field("recorded_s", recorded_s(), 2);
        w.End();
        bus_->Publish("level", w.str());
      }

      if (full) {
        // A forgotten Stop must not grow without limit: 16 kHz mono float is
        // 64 KB per second.
        bus_->Publish("recording",
                      "{\"active\":false,\"reason\":\"cap reached\"}");
        break;
      }
    }
  }

  Pipeline *pipe_;
  EventBus *bus_;
  History *history_;
  std::unique_ptr<AudioCapture> capture_;
  std::thread thread_;
  std::atomic<bool> stop_ {false};
  std::atomic<bool> recording_ {false};
  mutable std::mutex mu_;
  AudioBuffer buffer_;
  size_t max_samples_ = 16000 * 60;
  int mic_index_ = -1;
  std::string mic_name_;
};

std::string StateJson(Pipeline *pipe, const Recorder &recorder, const History &history) {
  JsonWriter w;
  w.BeginObject();
  w.Field("sherpa_version", AsrEngine::SherpaVersion());
  w.Field("audio_backend", std::string(AudioBackendName()));
  w.Field("root", pipe->paths().root);
  w.Field("models_dir", pipe->paths().models_dir);
  w.Field("hotwords_file", pipe->paths().hotwords);
  w.Field("rewrites_file", pipe->paths().rewrites);

  w.Key("models").BeginArray();
  for (const ModelProfile &m : pipe->registry().models()) {
    w.BeginObject();
    w.Field("id", m.id);
    w.Field("family", std::string(ModelFamilyName(m.family)));
    w.Field("precision", std::string(PrecisionName(m.precision)));
    w.Field("size_mb", static_cast<double>(m.size_bytes) / (1024.0 * 1024.0), 1);
    w.Field("biasing_capable", m.supports_hotwords);
    w.Field("biasing_blocker", m.hotwords_blocker);
    w.Field("describe", m.Describe());
    w.End();
  }
  w.End();

  w.Key("loaded");
  if (pipe->asr().loaded()) {
    const ModelProfile &m = pipe->asr().profile();
    const AsrOptions &o = pipe->asr().options();
    w.BeginObject();
    w.Field("id", m.id);
    w.Field("family", std::string(ModelFamilyName(m.family)));
    w.Field("precision", std::string(PrecisionName(m.precision)));
    w.Field("decoding_method", o.decoding_method);
    w.Field("num_threads", o.num_threads);
    w.Field("hotwords_score", o.hotwords_score, 2);
    w.Field("blank_penalty", o.blank_penalty, 2);
    w.Field("load_ms", pipe->asr().load_ms(), 0);
    w.Field("biasing_available", pipe->asr().biasing_available());
    w.Field("biasing_blocker", pipe->asr().biasing_blocker());
    w.End();
  } else {
    w.Null();
  }

  w.Key("filter").BeginObject();
  w.Field("biasing", pipe->biasing_enabled());
  w.Field("rewrites", pipe->rewrites_enabled());
  w.Field("hotword_count", pipe->hotwords().size());
  w.Field("hotword_max_words", pipe->hotwords().max_words());
  w.Field("rewrite_count", pipe->rewrites().size());
  std::vector<std::string> hw_warnings;
  const std::string wire = pipe->SerializedHotwords(&hw_warnings);
  w.Field("active", !wire.empty());
  w.Key("warnings").BeginArray();
  for (const std::string &s : hw_warnings) w.String(s);
  w.End();
  w.End();

  std::string mic_error;
  const std::vector<AudioDevice> mics = ListCaptureDevices(&mic_error);
  w.Key("mics").BeginArray();
  for (const AudioDevice &d : mics) {
    w.BeginObject();
    w.Field("index", d.index);
    w.Field("name", d.name);
    w.Field("is_default", d.is_default);
    w.Field("sample_rate", d.sample_rate);
    w.Field("channels", d.channels);
    w.End();
  }
  w.End();
  w.Field("mic_error", mic_error);

  w.Key("recording").BeginObject();
  w.Field("active", recorder.recording());
  w.Field("mic_index", recorder.mic_index());
  w.Field("mic_name", recorder.mic_name());
  w.Field("recorded_s", recorder.recorded_s(), 2);
  w.Field("max_record_s", pipe->config().GetFloat("audio.max_record_s", 60.0f), 1);
  w.End();

  w.Field("history_size", history.size());

  w.Key("warnings").BeginArray();
  for (const std::string &s : pipe->warnings()) w.String(s);
  w.End();

  w.End();
  return w.str();
}

void PrintUsage() {
  std::printf(R"(vcc_engine - HTTP API server for the PyQt5 dashboard

USAGE
  vcc_engine [options]

OPTIONS
  --port <n>        listen port (default: config engine.port)
  --host <addr>     bind address (default: 127.0.0.1; anything else is unauthenticated)
  --model <id>      load this model at startup
  --precision <p>   int8 | fp32 | auto
  --root <dir>      project root
  --set key=value   override a config/app.ini key (repeatable)
  -h, --help        this text
)");
}

}  // namespace

int main(int argc, char **argv) {
  SetLogColor(false);

  std::string root, model, precision, host;
  std::vector<std::string> sets;
  int port = 0;

  for (int i = 1; i < argc; ++i) {
    const std::string arg = argv[i];
    const bool has_next = i + 1 < argc;
    if (arg == "-h" || arg == "--help") {
      PrintUsage();
      return 0;
    } else if (arg == "--port" && has_next) {
      if (!ParseInt(argv[++i], &port)) {
        std::fprintf(stderr, "error: --port expects an integer\n");
        return 1;
      }
    } else if (arg == "--host" && has_next) {
      host = argv[++i];
    } else if (arg == "--model" && has_next) {
      model = argv[++i];
    } else if (arg == "--precision" && has_next) {
      precision = argv[++i];
    } else if (arg == "--root" && has_next) {
      root = argv[++i];
    } else if (arg == "--set" && has_next) {
      sets.push_back(argv[++i]);
    } else if (arg == "--no-open") {
      // Accepted and ignored: this process never opened a browser. Kept so an
      // older launcher script does not fail.
    } else {
      std::fprintf(stderr, "error: unexpected argument '%s'\n\n", arg.c_str());
      PrintUsage();
      return 1;
    }
  }

  Pipeline pipe;
  std::string error;
  if (!pipe.Init(root, sets, &error)) {
    std::fprintf(stderr, "error: %s\n", error.c_str());
    return 1;
  }

  // Best effort: the UI is more useful than a dead process when models are
  // missing, and it can tell the user what to run.
  std::string load_error;
  if (!pipe.LoadModel(model, precision, &load_error)) {
    VCC_WARN << "no model loaded at startup: " << load_error;
  }

  EventBus bus;
  History history(40);
  Recorder recorder(&pipe, &bus, &history);
  HttpServer server;
  g_server = &server;
  server.set_max_body_bytes(64u * 1024u * 1024u);

  auto state = [&]() { return HttpResponse::Json(StateJson(&pipe, recorder, history)); };

  // --- state and configuration -------------------------------------------

  server.Route("GET", "/api/state", [&](const HttpRequest &) { return state(); });

  server.Route("POST", "/api/model", [&](const HttpRequest &req) {
    JsonObject body;
    body.Parse(req.body);
    if (body.Has("num_threads")) {
      pipe.config().Set("asr.num_threads", std::to_string(body.GetInt("num_threads", 4)));
    }
    if (body.Has("hotwords_score")) {
      pipe.config().Set("asr.hotwords_score",
                        std::to_string(body.GetNumber("hotwords_score", 2.0)));
    }
    if (body.Has("blank_penalty")) {
      pipe.config().Set("asr.blank_penalty",
                        std::to_string(body.GetNumber("blank_penalty", 0.0)));
    }
    if (body.Has("decoding_method")) {
      pipe.config().Set("asr.decoding_method", body.GetString("decoding_method"));
    }

    // A take in flight would be decoded against a recogniser that is being
    // torn down, so drop it rather than risk that.
    recorder.Cancel();

    std::string err;
    const bool ok =
        pipe.LoadModel(body.GetString("model"), body.GetString("precision"), &err);
    if (ok) history.Redecode(pipe);
    if (!ok) return HttpResponse::Error(400, err);
    return state();
  });

  // The filter switches and the hotword boost do NOT need a model reload,
  // because hotwords are passed per decode. Re-decoding the history is enough,
  // and it is what makes the before/after visible immediately.
  server.Route("POST", "/api/filter", [&](const HttpRequest &req) {
    JsonObject body;
    body.Parse(req.body);
    if (body.Has("biasing")) pipe.set_biasing_enabled(body.GetBool("biasing", true));
    if (body.Has("rewrites")) pipe.set_rewrites_enabled(body.GetBool("rewrites", true));
    if (body.Has("hotwords_score")) {
      pipe.config().Set("asr.hotwords_score",
                        std::to_string(body.GetNumber("hotwords_score", 2.0)));
    }
    const bool redecode = body.GetBool("redecode", true);
    if (redecode) history.Redecode(pipe);
    return state();
  });

  // --- the two editable data files ---------------------------------------

  server.Route("GET", "/api/hotwords", [&](const HttpRequest &) {
    return HttpResponse::Text(pipe.hotwords().ToText());
  });

  server.Route("POST", "/api/hotwords", [&](const HttpRequest &req) {
    std::vector<std::string> warnings;
    pipe.hotwords().LoadText(req.body, &warnings);
    if (req.Param("save") == "1") {
      std::string err;
      if (!pipe.SaveHotwords(&err)) return HttpResponse::Error(500, err);
    }
    // No model reload: this is the whole advantage of per-decode hotwords.
    history.Redecode(pipe);
    return state();
  });

  server.Route("GET", "/api/rewrites", [&](const HttpRequest &) {
    return HttpResponse::Text(pipe.rewrites().ToText());
  });

  server.Route("POST", "/api/rewrites", [&](const HttpRequest &req) {
    std::vector<std::string> warnings;
    pipe.rewrites().LoadText(req.body, &warnings);
    if (req.Param("save") == "1") {
      std::string err;
      if (!pipe.SaveRewrites(&err)) return HttpResponse::Error(500, err);
    }
    // Text-stage only: the decodes still stand, so this is nearly free.
    history.ReapplyRewrites(pipe);
    return state();
  });

  server.Route("GET", "/api/hotwords/wire", [&](const HttpRequest &) {
    // Exactly what the decoder is handed, one phrase per line for reading.
    std::vector<std::string> warnings;
    const std::string wire = pipe.SerializedHotwords(&warnings);
    std::string out;
    for (const std::string &p : Split(wire, '/', true)) out += p + "\n";
    for (const std::string &w : warnings) out += "# warning: " + w + "\n";
    return HttpResponse::Text(out);
  });

  server.Route("POST", "/api/reload", [&](const HttpRequest &) {
    std::string err;
    if (!pipe.ReloadDataFiles(&err)) return HttpResponse::Error(400, err);
    history.Redecode(pipe);
    return state();
  });

  // --- history ------------------------------------------------------------

  server.Route("GET", "/api/history", [&](const HttpRequest &) {
    JsonWriter w;
    w.BeginArray();
    history.ForEach([&](const Utterance &u) { WriteUtterance(&w, u); });
    w.End();
    return HttpResponse::Json(w.str());
  });

  server.Route("POST", "/api/history/clear", [&](const HttpRequest &) {
    history.Clear();
    return state();
  });

  // --- one-off decode of an uploaded WAV ---------------------------------

  server.Route("POST", "/api/recognize", [&](const HttpRequest &req) {
    if (req.body.empty()) {
      return HttpResponse::Error(400, "empty body (expected WAV bytes)");
    }
    AudioBuffer audio;
    std::string err;
    if (!DecodeWav(req.body.data(), req.body.size(), &audio, &err)) {
      return HttpResponse::Error(400, "not a readable WAV: " + err);
    }
    if (req.Param("normalize") == "1") NormalizePeak(&audio);
    const std::string name = req.Param("name", "upload.wav");
    const std::string reference = req.Param("reference");

    // One file, one utterance: the corpus is recorded a phrase at a time, so
    // there is nothing to segment. The array response is kept for the client's
    // sake -- it already handles a list, and a future caller might upload a
    // batch.
    Utterance u;
    u.source = name;
    u.result = pipe.Process(audio, reference);
    u.audio = std::move(audio);
    const int index = history.Add(std::move(u));

    JsonWriter w;
    w.BeginArray();
    history.ForEach([&](const Utterance &item) {
      if (item.index == index) WriteUtterance(&w, item);
    });
    w.End();
    return HttpResponse::Json(w.str());
  });

  // --- microphone ---------------------------------------------------------

  server.Route("POST", "/api/record/start", [&](const HttpRequest &req) {
    JsonObject body;
    body.Parse(req.body);
    const int mic = body.GetInt("mic", pipe.config().GetInt("audio.mic_index", -1));
    std::string err;
    if (!recorder.Start(mic, &err)) return HttpResponse::Error(400, err);
    bus.Publish("recording", "{\"active\":true}");
    return state();
  });

  // Stop, decode, and push the result out on the event stream so the client
  // does not have to poll for it.
  server.Route("POST", "/api/record/stop", [&](const HttpRequest &) {
    std::string err;
    const int index = recorder.StopAndDecode(&err);
    bus.Publish("recording", "{\"active\":false}");
    if (index < 0) return HttpResponse::Error(400, err);
    JsonWriter w;
    history.ForEach([&](const Utterance &item) {
      if (item.index == index) WriteUtterance(&w, item);
    });
    bus.Publish("utterance", w.str());
    return state();
  });

  server.Route("POST", "/api/record/cancel", [&](const HttpRequest &) {
    recorder.Cancel();
    bus.Publish("recording", "{\"active\":false}");
    return state();
  });

  server.RouteSse("/api/events", [&](const HttpRequest &, const SseWriter &write) {
    EventBus::Subscription sub(&bus);
    if (!write("hello", "{\"ok\":true}")) return;
    while (!g_stop) {
      std::string event, data;
      if (sub.Next(&event, &data, 15000)) {
        if (!write(event, data)) return;
      } else if (!write("ping", "{}")) {
        return;  // keepalive: an idle event stream gets dropped otherwise
      }
    }
  });

  // This process serves no UI: the dashboard is a separate Qt application. A
  // human who opens the port in a browser gets told where to go.
  server.SetFallback([&](const HttpRequest &req) {
    if (StartsWith(req.path, "/api/")) {
      return HttpResponse::Error(404, "no such endpoint: " + req.path);
    }
    return HttpResponse::Text(
        "vcc_engine: API only, no web UI.\n"
        "\n"
        "Run the dashboard instead:  python dashboard/main.py\n"
        "\n"
        "Endpoints:\n"
        "  GET  /api/state            engine, model, filter and mic status\n"
        "  GET  /api/history          every utterance held, decoded both ways\n"
        "  GET  /api/hotwords         the hotword list as text\n"
        "  POST /api/hotwords         replace it, then re-decode the history\n"
        "  GET  /api/hotwords/wire    what the decoder is actually handed\n"
        "  GET  /api/rewrites         the rewrite table as text\n"
        "  POST /api/rewrites         replace it, then re-apply stage 2\n"
        "  POST /api/filter           toggle the two stages, set the boost\n"
        "  POST /api/model            load a model\n"
        "  POST /api/recognize        decode an uploaded WAV\n"
        "  POST /api/record/start     begin a push-to-talk take\n"
        "  POST /api/record/stop      end it and decode\n"
        "  POST /api/record/cancel    throw the take away\n"
        "  GET  /api/events           events: level, recording, utterance\n");
  });

  const std::string bind_host =
      host.empty() ? pipe.config().GetString("engine.host", "127.0.0.1") : host;
  const int bind_port = port != 0 ? port : pipe.config().GetInt("engine.port", 8777);

  if (!server.Start(bind_host, bind_port, &error)) {
    std::fprintf(stderr, "error: %s\n", error.c_str());
    return 1;
  }

  std::signal(SIGINT, OnSignal);
#ifdef SIGTERM
  std::signal(SIGTERM, OnSignal);
#endif

  const std::string url = "http://" + bind_host + ":" + std::to_string(bind_port) + "/";
  std::printf("\n  Contextual-biasing STT engine\n");
  std::printf("  %s\n\n", url.c_str());
  std::printf("  sherpa-onnx %s | audio backend: %s\n", AsrEngine::SherpaVersion().c_str(),
              AudioBackendName());
  if (pipe.asr().loaded()) {
    std::printf("  model: %s (%s)\n", pipe.asr().profile().id.c_str(),
                pipe.asr().profile().Describe().c_str());
    std::printf("  biasing: %s\n", pipe.asr().biasing_available()
                                       ? "available"
                                       : pipe.asr().biasing_blocker().c_str());
  } else {
    std::printf("  model: none loaded - %s\n", load_error.c_str());
  }
  std::printf("\n  Ctrl-C to stop\n\n");
  std::fflush(stdout);

  server.Wait();
  bus.CloseAll();
  recorder.Cancel();
  return 0;
}
