// Microphone capture.
//
// Two backends behind one interface:
//   * WASAPI  (Windows)  -- full device friendly names, any mix format,
//                           resampled down to 16 kHz mono for the model.
//   * ALSA    (Linux)    -- what the Cortex-A55 target will use.
// A null backend keeps the rest of the project buildable anywhere else.
//
// Callers never see the device's native format: Read() always hands back mono
// float samples at the rate requested in CaptureOptions.
#pragma once

#include <cstdint>
#include <memory>
#include <string>
#include <vector>

namespace vcc {

struct AudioDevice {
  int index = -1;
  std::string id;        // backend-specific opaque id
  std::string name;      // what to show a human
  bool is_default = false;
  int channels = 0;      // native channel count, 0 when unknown
  int sample_rate = 0;   // native rate, 0 when unknown
};

struct CaptureOptions {
  int device_index = -1;   // -1 = system default
  int sample_rate = 16000;
  // Ring buffer depth. Capture keeps running while a decode is in flight, so
  // this has to cover the worst-case decode time plus slack.
  float buffer_seconds = 10.0f;
};

// Backend name for logs and the dashboard: "wasapi", "alsa", or "null".
const char *AudioBackendName();

// Enumerates capture devices. Returns an empty list on the null backend.
std::vector<AudioDevice> ListCaptureDevices(std::string *error = nullptr);

class AudioCapture {
 public:
  static std::unique_ptr<AudioCapture> Create();

  virtual ~AudioCapture() = default;

  virtual bool Start(const CaptureOptions &opts, std::string *error) = 0;
  virtual void Stop() = 0;
  virtual bool running() const = 0;

  // Moves up to `max_samples` mono samples out of the ring buffer. Returns the
  // number written. Never blocks; returns 0 when nothing has arrived yet.
  virtual size_t Read(float *dst, size_t max_samples) = 0;

  // Samples dropped because the consumer fell behind. Non-zero here means the
  // decode loop is too slow for the configured buffer -- worth showing.
  virtual uint64_t overruns() const = 0;

  virtual const AudioDevice &device() const = 0;
  virtual int sample_rate() const = 0;
};

}  // namespace vcc
