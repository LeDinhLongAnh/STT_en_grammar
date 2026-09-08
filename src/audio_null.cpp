// Fallback capture backend for platforms without one of the real backends.
//
// Kept as a compiling, honest no-op rather than an #error so the offline tools
// (vcc_cli, unit tests, the dashboard's file-upload path) build and run
// everywhere. Live mic capture reports a clear reason instead of failing at
// link time.
//
// The Cortex-A55 target replaces this with an ALSA backend; the interface in
// include/vcc/audio.h is what that has to satisfy.
#if !defined(_WIN32)

#include "vcc/audio.h"
#include "vcc/log.h"

namespace vcc {
namespace {

class NullCapture : public AudioCapture {
 public:
  bool Start(const CaptureOptions &, std::string *error) override {
    if (error) {
      *error =
          "no microphone backend compiled in for this platform "
          "(implement src/audio_alsa.cpp for the ARM target)";
    }
    return false;
  }
  void Stop() override {}
  bool running() const override { return false; }
  size_t Read(float *, size_t) override { return 0; }
  uint64_t overruns() const override { return 0; }
  const AudioDevice &device() const override { return device_; }
  int sample_rate() const override { return 0; }

 private:
  AudioDevice device_;
};

}  // namespace

const char *AudioBackendName() { return "null"; }

std::vector<AudioDevice> ListCaptureDevices(std::string *error) {
  if (error) *error = "no microphone backend on this platform";
  return {};
}

std::unique_ptr<AudioCapture> AudioCapture::Create() {
  return std::unique_ptr<AudioCapture>(new NullCapture());
}

}  // namespace vcc

#endif  // !_WIN32
