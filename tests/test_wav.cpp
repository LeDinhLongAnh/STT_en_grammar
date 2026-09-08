#include "vcc/wav.h"

#include <cmath>

#include "vcc/core.h"
#include "vcc_test.h"

using namespace vcc;

namespace {

AudioBuffer Tone(int rate, double seconds, double hz, float amplitude) {
  AudioBuffer b;
  b.sample_rate = rate;
  const size_t n = static_cast<size_t>(rate * seconds);
  b.samples.resize(n);
  for (size_t i = 0; i < n; ++i) {
    b.samples[i] = amplitude *
                   static_cast<float>(std::sin(2.0 * 3.14159265358979 * hz * i / rate));
  }
  return b;
}

}  // namespace

VCC_TEST(wav, roundtrip_preserves_shape) {
  const AudioBuffer in = Tone(16000, 0.25, 440.0, 0.5f);
  const std::string bytes = EncodeWav16(in);

  AudioBuffer out;
  std::string err;
  VCC_CHECK(DecodeWav(bytes.data(), bytes.size(), &out, &err));
  VCC_CHECK_EQ(out.sample_rate, 16000);
  VCC_CHECK_EQ(out.samples.size(), in.samples.size());

  // 16-bit quantisation caps the achievable error at ~1/32768 per sample.
  double worst = 0.0;
  for (size_t i = 0; i < in.samples.size(); ++i) {
    worst = std::max(worst, std::fabs(double(in.samples[i]) - out.samples[i]));
  }
  VCC_CHECK(worst < 1e-4);
}

VCC_TEST(wav, rejects_garbage) {
  AudioBuffer out;
  std::string err;
  const std::string junk(64, 'x');
  VCC_CHECK(!DecodeWav(junk.data(), junk.size(), &out, &err));
  VCC_CHECK(!err.empty());
}

VCC_TEST(wav, rejects_truncated_input) {
  AudioBuffer out;
  std::string err;
  const std::string tiny = "RIFF";
  VCC_CHECK(!DecodeWav(tiny.data(), tiny.size(), &out, &err));
}

VCC_TEST(wav, tolerates_extra_chunks) {
  // Windows recorders like to insert LIST/INFO between fmt and data. Splice one
  // in and check the chunk walker steps over it.
  AudioBuffer in = Tone(16000, 0.05, 300.0, 0.4f);
  std::string bytes = EncodeWav16(in);

  const size_t data_at = bytes.find("data");
  VCC_CHECK(data_at != std::string::npos);

  std::string extra = "LIST";
  const uint32_t extra_len = 8;
  for (int i = 0; i < 4; ++i) extra.push_back(char((extra_len >> (8 * i)) & 0xff));
  extra += "INFOxxxx";

  std::string spliced = bytes.substr(0, data_at) + extra + bytes.substr(data_at);
  // fix up the RIFF size field
  const uint32_t riff = static_cast<uint32_t>(spliced.size() - 8);
  for (int i = 0; i < 4; ++i) spliced[4 + i] = char((riff >> (8 * i)) & 0xff);

  AudioBuffer out;
  std::string err;
  VCC_CHECK(DecodeWav(spliced.data(), spliced.size(), &out, &err));
  VCC_CHECK_EQ(out.samples.size(), in.samples.size());
}

VCC_TEST(wav, levels_are_measured_in_dbfs) {
  const AudioBuffer half = Tone(16000, 0.1, 500.0, 0.5f);
  const LevelStats st = MeasureLevels(half);
  VCC_CHECK_NEAR(st.peak_dbfs, -6.0, 0.5);   // 0.5 amplitude == -6 dBFS
  VCC_CHECK_NEAR(st.rms_dbfs, -9.0, 0.6);    // sine RMS is peak/sqrt(2)
  VCC_CHECK(!st.clipped);
}

VCC_TEST(wav, silence_reports_the_floor) {
  AudioBuffer silence;
  silence.sample_rate = 16000;
  silence.samples.assign(1000, 0.0f);
  const LevelStats st = MeasureLevels(silence);
  VCC_CHECK_NEAR(st.peak_dbfs, -120.0, 0.01);
}

VCC_TEST(wav, clipping_is_detected) {
  AudioBuffer hot = Tone(16000, 0.2, 200.0, 4.0f);  // way over full scale
  for (float &v : hot.samples) v = std::max(-1.0f, std::min(1.0f, v));
  VCC_CHECK(MeasureLevels(hot).clipped);
}

VCC_TEST(wav, normalise_peak_scales_up_quiet_audio) {
  AudioBuffer quiet = Tone(16000, 0.1, 400.0, 0.2f);
  NormalizePeak(&quiet, 0.9f);
  VCC_CHECK_NEAR(MeasureLevels(quiet).peak_dbfs, -0.92, 0.3);
}

VCC_TEST(wav, normalise_peak_leaves_silence_alone) {
  AudioBuffer silence;
  silence.sample_rate = 16000;
  silence.samples.assign(500, 0.0f);
  NormalizePeak(&silence);
  for (float v : silence.samples) VCC_CHECK_EQ(v, 0.0f);
}

VCC_TEST(wav, resample_changes_rate_and_length) {
  const AudioBuffer in = Tone(48000, 0.2, 440.0, 0.5f);
  AudioBuffer out;
  std::string err;
  VCC_CHECK(DecodeWav(EncodeWav16(in).data(), EncodeWav16(in).size(), &out, &err));

  AudioBuffer down;
  VCC_CHECK(Resample(in, 16000, &down, &err));
  VCC_CHECK_EQ(down.sample_rate, 16000);
  // 0.2 s at 16 kHz, allowing for the resampler's filter delay.
  VCC_CHECK(down.samples.size() > 3000 && down.samples.size() < 3400);
}

VCC_TEST(wav, resample_is_a_noop_at_the_same_rate) {
  const AudioBuffer in = Tone(16000, 0.05, 300.0, 0.3f);
  AudioBuffer out;
  std::string err;
  VCC_CHECK(Resample(in, 16000, &out, &err));
  VCC_CHECK_EQ(out.samples.size(), in.samples.size());
}
