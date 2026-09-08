// Minimal RIFF/WAVE reader and writer.
//
// sherpa-onnx ships its own wave reader, but the dashboard receives audio as an
// in-memory upload and the test harness needs to write debug clips, so we keep
// a small self-contained implementation. Handles 8/16/24/32-bit PCM and 32-bit
// float, mono or multi-channel (downmixed), which covers everything Windows
// capture devices and the sherpa test_wavs throw at us.
#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace vcc {

struct AudioBuffer {
  std::vector<float> samples;  // mono, normalised to [-1, 1]
  int sample_rate = 0;

  bool empty() const { return samples.empty(); }
  double duration_s() const {
    return sample_rate > 0 ? static_cast<double>(samples.size()) / sample_rate : 0.0;
  }
};

// Decodes a WAV byte buffer. On failure returns false and sets `error`.
bool DecodeWav(const void *data, size_t size, AudioBuffer *out, std::string *error);

bool ReadWavFile(const std::string &path, AudioBuffer *out, std::string *error);

// Encodes as 16-bit PCM mono. Values outside [-1,1] are clipped.
std::string EncodeWav16(const AudioBuffer &buf);

bool WriteWavFile(const std::string &path, const AudioBuffer &buf);

// Simple high-quality-enough band-limited resample. Delegates to sherpa-onnx's
// LinearResampler when available (it is, we link the C API) so capture at
// 44.1/48 kHz reaches the model at 16 kHz without aliasing artefacts.
bool Resample(const AudioBuffer &in, int target_rate, AudioBuffer *out,
              std::string *error);

// Peak and RMS in dBFS. The dashboard shows both so a user can tell "the model
// is wrong" from "the microphone is not picking me up".
struct LevelStats {
  float peak_dbfs = -120.0f;
  float rms_dbfs = -120.0f;
  bool clipped = false;
};
LevelStats MeasureLevels(const AudioBuffer &buf);

// Normalises peak amplitude to `target_peak` (0..1). No-op on silence.
// Cheap insurance against a quiet laptop microphone starving the features.
void NormalizePeak(AudioBuffer *buf, float target_peak = 0.95f);

}  // namespace vcc
