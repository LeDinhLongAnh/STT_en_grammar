#include "vcc/wav.h"

#include <algorithm>
#include <cmath>
#include <cstring>

#include "sherpa-onnx/c-api/c-api.h"
#include "vcc/core.h"
#include "vcc/log.h"

namespace vcc {
namespace {

uint32_t Rd32(const uint8_t *p) {
  return static_cast<uint32_t>(p[0]) | (static_cast<uint32_t>(p[1]) << 8) |
         (static_cast<uint32_t>(p[2]) << 16) | (static_cast<uint32_t>(p[3]) << 24);
}
uint16_t Rd16(const uint8_t *p) {
  return static_cast<uint16_t>(static_cast<uint32_t>(p[0]) |
                               (static_cast<uint32_t>(p[1]) << 8));
}

void Wr32(std::string *s, uint32_t v) {
  s->push_back(static_cast<char>(v & 0xff));
  s->push_back(static_cast<char>((v >> 8) & 0xff));
  s->push_back(static_cast<char>((v >> 16) & 0xff));
  s->push_back(static_cast<char>((v >> 24) & 0xff));
}
void Wr16(std::string *s, uint16_t v) {
  s->push_back(static_cast<char>(v & 0xff));
  s->push_back(static_cast<char>((v >> 8) & 0xff));
}

constexpr uint16_t kFormatPcm = 1;
constexpr uint16_t kFormatFloat = 3;
constexpr uint16_t kFormatExtensible = 0xFFFE;

}  // namespace

bool DecodeWav(const void *data, size_t size, AudioBuffer *out,
               std::string *error) {
  auto fail = [&](const std::string &m) {
    if (error) *error = m;
    return false;
  };

  const uint8_t *p = static_cast<const uint8_t *>(data);
  if (size < 44) return fail("too short to be a WAV file");
  if (std::memcmp(p, "RIFF", 4) != 0) return fail("missing RIFF header");
  if (std::memcmp(p + 8, "WAVE", 4) != 0) return fail("not a WAVE file");

  uint16_t format = 0;
  uint16_t channels = 0;
  uint16_t bits = 0;
  uint32_t rate = 0;
  const uint8_t *pcm = nullptr;
  size_t pcm_size = 0;

  // Walk the chunk list rather than assuming the canonical 44-byte layout:
  // Windows capture apps love to insert LIST/fact chunks.
  size_t off = 12;
  while (off + 8 <= size) {
    const char id[5] = {static_cast<char>(p[off]), static_cast<char>(p[off + 1]),
                        static_cast<char>(p[off + 2]),
                        static_cast<char>(p[off + 3]), '\0'};
    uint32_t chunk = Rd32(p + off + 4);
    const size_t body = off + 8;
    if (body + chunk > size) chunk = static_cast<uint32_t>(size - body);

    if (std::memcmp(id, "fmt ", 4) == 0 && chunk >= 16) {
      format = Rd16(p + body + 0);
      channels = Rd16(p + body + 2);
      rate = Rd32(p + body + 4);
      bits = Rd16(p + body + 14);
      if (format == kFormatExtensible && chunk >= 40) {
        // the real format sits in the GUID's first two bytes
        format = Rd16(p + body + 24);
      }
    } else if (std::memcmp(id, "data", 4) == 0) {
      pcm = p + body;
      pcm_size = chunk;
    }
    off = body + chunk + (chunk & 1);  // chunks are word-aligned
  }

  if (pcm == nullptr) return fail("no data chunk");
  if (channels == 0) return fail("no fmt chunk / zero channels");
  if (rate == 0) return fail("sample rate is zero");

  const size_t bytes_per_sample = bits / 8u;
  if (bytes_per_sample == 0) return fail("unsupported bit depth 0");
  const size_t frame_bytes = bytes_per_sample * channels;
  if (frame_bytes == 0) return fail("degenerate frame size");
  const size_t frames = pcm_size / frame_bytes;

  out->sample_rate = static_cast<int>(rate);
  out->samples.assign(frames, 0.0f);

  for (size_t f = 0; f < frames; ++f) {
    double acc = 0.0;
    for (size_t c = 0; c < channels; ++c) {
      const uint8_t *s = pcm + f * frame_bytes + c * bytes_per_sample;
      double v = 0.0;
      if (format == kFormatFloat && bits == 32) {
        float fv = 0.0f;
        std::memcpy(&fv, s, 4);
        v = fv;
      } else if (format == kFormatFloat && bits == 64) {
        double dv = 0.0;
        std::memcpy(&dv, s, 8);
        v = dv;
      } else if (format == kFormatPcm) {
        switch (bits) {
          case 8:  v = (static_cast<int>(s[0]) - 128) / 128.0; break;
          case 16: v = static_cast<int16_t>(Rd16(s)) / 32768.0; break;
          case 24: {
            int32_t iv = (static_cast<int32_t>(s[0]) << 8) |
                         (static_cast<int32_t>(s[1]) << 16) |
                         (static_cast<int32_t>(s[2]) << 24);
            v = (iv >> 8) / 8388608.0;
            break;
          }
          case 32: v = static_cast<int32_t>(Rd32(s)) / 2147483648.0; break;
          default: return fail("unsupported PCM bit depth " + std::to_string(bits));
        }
      } else {
        return fail("unsupported WAV format tag " + std::to_string(format));
      }
      acc += v;
    }
    out->samples[f] = static_cast<float>(acc / channels);
  }
  return true;
}

bool ReadWavFile(const std::string &path, AudioBuffer *out, std::string *error) {
  std::string data;
  if (!ReadFile(path, &data)) {
    if (error) *error = "cannot open " + path;
    return false;
  }
  return DecodeWav(data.data(), data.size(), out, error);
}

std::string EncodeWav16(const AudioBuffer &buf) {
  const uint32_t n = static_cast<uint32_t>(buf.samples.size());
  const uint32_t data_bytes = n * 2;
  std::string s;
  s.reserve(44 + data_bytes);

  s += "RIFF";
  Wr32(&s, 36 + data_bytes);
  s += "WAVE";
  s += "fmt ";
  Wr32(&s, 16);
  Wr16(&s, kFormatPcm);
  Wr16(&s, 1);
  Wr32(&s, static_cast<uint32_t>(buf.sample_rate));
  Wr32(&s, static_cast<uint32_t>(buf.sample_rate) * 2);  // byte rate
  Wr16(&s, 2);                                           // block align
  Wr16(&s, 16);
  s += "data";
  Wr32(&s, data_bytes);

  for (float v : buf.samples) {
    const float c = std::max(-1.0f, std::min(1.0f, v));
    const int16_t q = static_cast<int16_t>(std::lround(c * 32767.0f));
    Wr16(&s, static_cast<uint16_t>(q));
  }
  return s;
}

bool WriteWavFile(const std::string &path, const AudioBuffer &buf) {
  return WriteFile(path, EncodeWav16(buf));
}

bool Resample(const AudioBuffer &in, int target_rate, AudioBuffer *out,
              std::string *error) {
  if (target_rate <= 0) {
    if (error) *error = "target rate must be positive";
    return false;
  }
  if (in.sample_rate == target_rate) {
    *out = in;
    return true;
  }
  if (in.samples.empty()) {
    out->samples.clear();
    out->sample_rate = target_rate;
    return true;
  }

  // filter_cutoff_hz = 0 and num_zeros = 0 tell sherpa-onnx to use its own
  // defaults (cutoff at 0.475 * min(rate_in, rate_out), 6 zeros).
  const SherpaOnnxLinearResampler *rs =
      SherpaOnnxCreateLinearResampler(in.sample_rate, target_rate, 0.0f, 0);
  if (rs == nullptr) {
    if (error) *error = "could not create resampler";
    return false;
  }
  const SherpaOnnxResampleOut *chunk = SherpaOnnxLinearResamplerResample(
      rs, in.samples.data(), static_cast<int32_t>(in.samples.size()), 1);
  if (chunk == nullptr) {
    SherpaOnnxDestroyLinearResampler(rs);
    if (error) *error = "resample failed";
    return false;
  }
  out->samples.assign(chunk->samples, chunk->samples + chunk->n);
  out->sample_rate = target_rate;
  SherpaOnnxLinearResamplerResampleFree(chunk);
  SherpaOnnxDestroyLinearResampler(rs);
  return true;
}

LevelStats MeasureLevels(const AudioBuffer &buf) {
  LevelStats st;
  if (buf.samples.empty()) return st;

  double peak = 0.0;
  double sq = 0.0;
  size_t hot = 0;
  for (float v : buf.samples) {
    const double a = std::fabs(static_cast<double>(v));
    peak = std::max(peak, a);
    sq += static_cast<double>(v) * v;
    if (a >= 0.999) ++hot;
  }
  const double rms = std::sqrt(sq / static_cast<double>(buf.samples.size()));
  auto to_db = [](double x) {
    return x <= 1e-9 ? -120.0f : static_cast<float>(20.0 * std::log10(x));
  };
  st.peak_dbfs = to_db(peak);
  st.rms_dbfs = to_db(rms);
  // A handful of full-scale samples happens; a sustained run is real clipping.
  st.clipped = hot > buf.samples.size() / 500 && hot > 8;
  return st;
}

void NormalizePeak(AudioBuffer *buf, float target_peak) {
  if (buf->samples.empty()) return;
  float peak = 0.0f;
  for (float v : buf->samples) peak = std::max(peak, std::fabs(v));
  if (peak < 1e-4f) return;  // silence: amplifying it only amplifies noise
  const float g = target_peak / peak;
  if (g > 8.0f) {
    // Anything needing >18 dB of make-up gain is background hiss, not speech.
    VCC_DEBUG << "skipping peak normalisation, gain would be " << g;
    return;
  }
  for (float &v : buf->samples) v *= g;
}

}  // namespace vcc
