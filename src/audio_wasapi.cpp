// WASAPI capture backend (Windows).
//
// Shared-mode capture, event-driven, on a dedicated thread.
//
// The target format is **16 kHz, 16-bit, mono** -- what the acoustic models were
// trained on, and what the ALSA capture on the router will hand over. Two paths
// reach it:
//
//   1. Ask WASAPI for it directly. In shared mode a client may request an
//      arbitrary PCM format if it sets AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM, and
//      the audio engine inserts its own resampler. This is the preferred path:
//      Windows' resampler is better than ours and the conversion happens before
//      the data crosses into our process.
//   2. If the driver refuses that, fall back to the device mix format (usually
//      48 kHz stereo float32), downmix, and resample ourselves.
//
// Either way the samples are **quantised to 16-bit before leaving this file**.
// That is not cosmetic: it makes the dev-box audio path bit-identical to the
// router's, and it makes a clip saved with WriteWavFile (16-bit PCM) decode to
// exactly what was decoded live. Without it, the evaluation corpus would be
// subtly different audio from what you heard the result for.
#ifdef _WIN32

#include <atomic>
#include <cmath>
#include <cstring>
#include <mutex>
#include <thread>
#include <vector>

// Include order is load-bearing here, hence the clang-format guard:
// functiondiscoverykeys_devpkey.h uses DEFINE_PROPERTYKEY without including
// what defines it, so mmdeviceapi.h (which pulls in propkeydef.h) has to come
// first. Alphabetising these headers breaks the build.
// clang-format off
#include <windows.h>
#include <objbase.h>
#include <mmdeviceapi.h>
#include <functiondiscoverykeys_devpkey.h>
#include <audioclient.h>
#include <mmreg.h>
#include <ksmedia.h>
// clang-format on

#include "sherpa-onnx/c-api/c-api.h"
#include "vcc/audio.h"
#include "vcc/core.h"
#include "vcc/log.h"

namespace vcc {
namespace {

constexpr int64_t kRefTimesPerSec = 10000000;  // 100-ns units in one second

std::string Narrow(const wchar_t *w) {
  if (w == nullptr) return std::string();
  const int n = WideCharToMultiByte(CP_UTF8, 0, w, -1, nullptr, 0, nullptr, nullptr);
  if (n <= 1) return std::string();
  std::string s(static_cast<size_t>(n - 1), '\0');
  WideCharToMultiByte(CP_UTF8, 0, w, -1, &s[0], n, nullptr, nullptr);
  return s;
}

// COM has to be initialised per-thread. Apartment threading is what audio
// endpoints expect, and RAII keeps the uninit paired with the init.
class ComScope {
 public:
  ComScope() {
    const HRESULT hr = CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED);
    // RPC_E_CHANGED_MODE means somebody else already picked a model; that is
    // fine, we just must not uninitialise on their behalf.
    owned_ = SUCCEEDED(hr);
  }
  ~ComScope() {
    if (owned_) CoUninitialize();
  }

 private:
  bool owned_ = false;
};

template <typename T>
void SafeRelease(T **p) {
  if (*p) {
    (*p)->Release();
    *p = nullptr;
  }
}

struct EnumeratedDevices {
  std::vector<AudioDevice> list;
  std::vector<std::wstring> ids;  // parallel to `list`
};

bool EnumerateDevices(EnumeratedDevices *out, std::string *error) {
  auto fail = [&](const std::string &m) {
    if (error) *error = m;
    return false;
  };

  IMMDeviceEnumerator *enumerator = nullptr;
  HRESULT hr = CoCreateInstance(__uuidof(MMDeviceEnumerator), nullptr, CLSCTX_ALL,
                                __uuidof(IMMDeviceEnumerator),
                                reinterpret_cast<void **>(&enumerator));
  if (FAILED(hr)) return fail("CoCreateInstance(MMDeviceEnumerator) failed");

  std::wstring default_id;
  IMMDevice *def = nullptr;
  if (SUCCEEDED(enumerator->GetDefaultAudioEndpoint(eCapture, eCommunications, &def))) {
    LPWSTR id = nullptr;
    if (SUCCEEDED(def->GetId(&id))) {
      default_id = id;
      CoTaskMemFree(id);
    }
    SafeRelease(&def);
  }

  IMMDeviceCollection *collection = nullptr;
  hr = enumerator->EnumAudioEndpoints(eCapture, DEVICE_STATE_ACTIVE, &collection);
  if (FAILED(hr)) {
    SafeRelease(&enumerator);
    return fail("EnumAudioEndpoints failed");
  }

  UINT count = 0;
  collection->GetCount(&count);
  for (UINT i = 0; i < count; ++i) {
    IMMDevice *dev = nullptr;
    if (FAILED(collection->Item(i, &dev))) continue;

    AudioDevice d;
    d.index = static_cast<int>(out->list.size());

    LPWSTR wid = nullptr;
    std::wstring wid_str;
    if (SUCCEEDED(dev->GetId(&wid))) {
      wid_str = wid;
      d.id = Narrow(wid);
      CoTaskMemFree(wid);
    }
    d.is_default = !default_id.empty() && wid_str == default_id;

    IPropertyStore *props = nullptr;
    if (SUCCEEDED(dev->OpenPropertyStore(STGM_READ, &props))) {
      PROPVARIANT v;
      PropVariantInit(&v);
      if (SUCCEEDED(props->GetValue(PKEY_Device_FriendlyName, &v)) &&
          v.vt == VT_LPWSTR) {
        d.name = Narrow(v.pwszVal);
      }
      PropVariantClear(&v);
      SafeRelease(&props);
    }
    if (d.name.empty()) d.name = "Capture device " + std::to_string(d.index);

    // Native format, purely informational for the UI.
    IAudioClient *client = nullptr;
    if (SUCCEEDED(dev->Activate(__uuidof(IAudioClient), CLSCTX_ALL, nullptr,
                                reinterpret_cast<void **>(&client)))) {
      WAVEFORMATEX *mix = nullptr;
      if (SUCCEEDED(client->GetMixFormat(&mix)) && mix) {
        d.channels = mix->nChannels;
        d.sample_rate = static_cast<int>(mix->nSamplesPerSec);
        CoTaskMemFree(mix);
      }
      SafeRelease(&client);
    }

    out->list.push_back(std::move(d));
    out->ids.push_back(wid_str);
    SafeRelease(&dev);
  }

  SafeRelease(&collection);
  SafeRelease(&enumerator);
  return true;
}

class WasapiCapture : public AudioCapture {
 public:
  ~WasapiCapture() override { Stop(); }

  bool Start(const CaptureOptions &opts, std::string *error) override {
    Stop();
    auto fail = [&](const std::string &m) {
      if (error) *error = m;
      VCC_ERROR << "wasapi: " << m;
      Teardown();
      return false;
    };

    opts_ = opts;
    target_rate_ = opts.sample_rate > 0 ? opts.sample_rate : 16000;

    com_ = std::unique_ptr<ComScope>(new ComScope());

    EnumeratedDevices devices;
    std::string err;
    if (!EnumerateDevices(&devices, &err)) return fail(err);
    if (devices.list.empty()) return fail("no active capture devices");

    int idx = opts.device_index;
    if (idx < 0) {
      idx = 0;
      for (size_t i = 0; i < devices.list.size(); ++i) {
        if (devices.list[i].is_default) {
          idx = static_cast<int>(i);
          break;
        }
      }
    }
    if (idx >= static_cast<int>(devices.list.size())) {
      return fail("device index " + std::to_string(idx) + " out of range (" +
                  std::to_string(devices.list.size()) + " devices)");
    }
    device_ = devices.list[static_cast<size_t>(idx)];

    IMMDeviceEnumerator *enumerator = nullptr;
    if (FAILED(CoCreateInstance(__uuidof(MMDeviceEnumerator), nullptr, CLSCTX_ALL,
                                __uuidof(IMMDeviceEnumerator),
                                reinterpret_cast<void **>(&enumerator)))) {
      return fail("CoCreateInstance(MMDeviceEnumerator) failed");
    }
    IMMDevice *dev = nullptr;
    const HRESULT hr_get =
        enumerator->GetDevice(devices.ids[static_cast<size_t>(idx)].c_str(), &dev);
    SafeRelease(&enumerator);
    if (FAILED(hr_get) || dev == nullptr) return fail("GetDevice failed");

    // Held until Initialize succeeds: the fallback path has to re-activate the
    // client, and that needs the device.
    IMMDevice *dev_for_retry = dev;
    HRESULT hr = dev->Activate(__uuidof(IAudioClient), CLSCTX_ALL, nullptr,
                               reinterpret_cast<void **>(&client_));
    if (FAILED(hr)) {
      SafeRelease(&dev);
      return fail("IAudioClient activation failed");
    }

    const REFERENCE_TIME duration = static_cast<REFERENCE_TIME>(kRefTimesPerSec / 5);

    // Path 1: ask the audio engine for 16 kHz / 16-bit / mono outright.
    WAVEFORMATEX want;
    std::memset(&want, 0, sizeof(want));
    want.wFormatTag = WAVE_FORMAT_PCM;
    want.nChannels = 1;
    want.nSamplesPerSec = static_cast<DWORD>(target_rate_);
    want.wBitsPerSample = 16;
    want.nBlockAlign = static_cast<WORD>(want.nChannels * want.wBitsPerSample / 8);
    want.nAvgBytesPerSec = want.nSamplesPerSec * want.nBlockAlign;
    want.cbSize = 0;

    // AUTOCONVERTPCM lets a shared-mode client name its own PCM format; without
    // it, Initialize only accepts the device's mix format.
    const DWORD convert_flags = AUDCLNT_STREAMFLAGS_EVENTCALLBACK |
                                AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM |
                                AUDCLNT_STREAMFLAGS_SRC_DEFAULT_QUALITY;
    hr = client_->Initialize(AUDCLNT_SHAREMODE_SHARED, convert_flags, duration, 0,
                             &want, nullptr);
    if (SUCCEEDED(hr)) {
      native_format_ = true;
      src_channels_ = 1;
      src_rate_ = target_rate_;
      src_bits_ = 16;
      src_is_float_ = false;
    } else {
      // Path 2: the driver would not take it. Take the mix format and convert.
      VCC_DEBUG << "wasapi: device refused " << target_rate_
                << " Hz/16-bit/mono (hr=0x" << ToHex(static_cast<uint32_t>(hr))
                << "), falling back to the mix format";
      SafeRelease(&client_);
      if (FAILED(dev_for_retry->Activate(__uuidof(IAudioClient), CLSCTX_ALL, nullptr,
                                         reinterpret_cast<void **>(&client_)))) {
        return fail("IAudioClient re-activation failed");
      }
      if (FAILED(client_->GetMixFormat(&mix_format_)) || mix_format_ == nullptr) {
        return fail("GetMixFormat failed");
      }
      src_channels_ = mix_format_->nChannels;
      src_rate_ = static_cast<int>(mix_format_->nSamplesPerSec);
      src_bits_ = mix_format_->wBitsPerSample;
      src_is_float_ = IsFloatFormat(mix_format_);
      if (!src_is_float_ && src_bits_ != 16 && src_bits_ != 32) {
        return fail("unsupported capture bit depth " + std::to_string(src_bits_));
      }
      hr = client_->Initialize(AUDCLNT_SHAREMODE_SHARED,
                               AUDCLNT_STREAMFLAGS_EVENTCALLBACK, duration, 0,
                               mix_format_, nullptr);
      if (FAILED(hr)) {
        return fail("IAudioClient::Initialize failed (hr=0x" +
                    ToHex(static_cast<uint32_t>(hr)) + ")");
      }
    }

    SafeRelease(&dev_for_retry);
    dev = nullptr;

    event_ = CreateEventW(nullptr, FALSE, FALSE, nullptr);
    if (event_ == nullptr) return fail("CreateEvent failed");
    if (FAILED(client_->SetEventHandle(event_))) return fail("SetEventHandle failed");
    if (FAILED(client_->GetService(__uuidof(IAudioCaptureClient),
                                   reinterpret_cast<void **>(&capture_)))) {
      return fail("GetService(IAudioCaptureClient) failed");
    }

    if (src_rate_ != target_rate_) {
      resampler_ = SherpaOnnxCreateLinearResampler(src_rate_, target_rate_, 0.0f, 0);
      if (resampler_ == nullptr) return fail("could not create resampler");
    }

    ring_capacity_ = static_cast<size_t>(
        static_cast<double>(target_rate_) * std::max(1.0f, opts.buffer_seconds));
    ring_.assign(ring_capacity_, 0.0f);
    ring_read_ = ring_write_ = ring_size_ = 0;
    overruns_ = 0;

    if (FAILED(client_->Start())) return fail("IAudioClient::Start failed");

    running_ = true;
    stop_flag_ = false;
    thread_ = std::thread(&WasapiCapture::Run, this);

    VCC_INFO << "capturing from '" << device_.name << "': "
             << (native_format_
                     ? std::to_string(target_rate_) + " Hz 16-bit mono (device native)"
                     : std::to_string(src_rate_) + " Hz " +
                           (src_is_float_ ? "float" : "int") +
                           std::to_string(src_bits_) + " " +
                           std::to_string(src_channels_) + "ch -> " +
                           std::to_string(target_rate_) + " Hz 16-bit mono");
    return true;
  }

  void Stop() override {
    if (thread_.joinable()) {
      stop_flag_ = true;
      if (event_) SetEvent(event_);
      thread_.join();
    }
    Teardown();
    running_ = false;
  }

  bool running() const override { return running_; }

  size_t Read(float *dst, size_t max_samples) override {
    std::lock_guard<std::mutex> lock(ring_mu_);
    const size_t n = std::min(max_samples, ring_size_);
    for (size_t i = 0; i < n; ++i) {
      dst[i] = ring_[ring_read_];
      ring_read_ = (ring_read_ + 1) % ring_capacity_;
    }
    ring_size_ -= n;
    return n;
  }

  uint64_t overruns() const override { return overruns_; }
  const AudioDevice &device() const override { return device_; }
  int sample_rate() const override { return target_rate_; }

 private:
  static bool IsFloatFormat(const WAVEFORMATEX *fmt) {
    if (fmt->wFormatTag == WAVE_FORMAT_IEEE_FLOAT) return true;
    if (fmt->wFormatTag == WAVE_FORMAT_EXTENSIBLE) {
      const WAVEFORMATEXTENSIBLE *ext =
          reinterpret_cast<const WAVEFORMATEXTENSIBLE *>(fmt);
      return IsEqualGUID(ext->SubFormat, KSDATAFORMAT_SUBTYPE_IEEE_FLOAT) != 0;
    }
    return false;
  }

  static std::string ToHex(uint32_t v) {
    static const char *digits = "0123456789abcdef";
    std::string s(8, '0');
    for (int i = 7; i >= 0; --i) {
      s[static_cast<size_t>(i)] = digits[v & 0xf];
      v >>= 4;
    }
    return s;
  }

  void Teardown() {
    if (client_) client_->Stop();
    SafeRelease(&capture_);
    SafeRelease(&client_);
    if (mix_format_) {
      CoTaskMemFree(mix_format_);
      mix_format_ = nullptr;
    }
    if (event_) {
      CloseHandle(event_);
      event_ = nullptr;
    }
    if (resampler_) {
      SherpaOnnxDestroyLinearResampler(resampler_);
      resampler_ = nullptr;
    }
    com_.reset();
  }

  // Quantise to 16-bit, then back to float for the model (sherpa-onnx wants
  // normalised float). The round trip is the point: it makes this path
  // bit-identical to a 16-bit ALSA capture on the target and to a clip saved as
  // 16-bit PCM, so live decoding and corpus decoding see the same samples.
  static float Quantize16(float v) {
    const float clamped = v < -1.0f ? -1.0f : (v > 1.0f ? 1.0f : v);
    const int16_t q = static_cast<int16_t>(std::lround(clamped * 32767.0f));
    return static_cast<float>(q) / 32768.0f;
  }

  void PushRing(const float *samples, size_t n) {
    std::lock_guard<std::mutex> lock(ring_mu_);
    for (size_t i = 0; i < n; ++i) {
      if (ring_size_ == ring_capacity_) {
        // Buffer full: drop the oldest sample. Losing the start of an old
        // utterance is better than stalling the audio thread.
        ring_read_ = (ring_read_ + 1) % ring_capacity_;
        --ring_size_;
        ++overruns_;
      }
      ring_[ring_write_] = Quantize16(samples[i]);
      ring_write_ = (ring_write_ + 1) % ring_capacity_;
      ++ring_size_;
    }
  }

  void Run() {
    ComScope com;  // the capture thread needs its own COM apartment
    std::vector<float> mono;
    while (!stop_flag_) {
      if (WaitForSingleObject(event_, 200) != WAIT_OBJECT_0) continue;

      UINT32 packet = 0;
      while (SUCCEEDED(capture_->GetNextPacketSize(&packet)) && packet > 0) {
        BYTE *data = nullptr;
        UINT32 frames = 0;
        DWORD flags = 0;
        if (FAILED(capture_->GetBuffer(&data, &frames, &flags, nullptr, nullptr))) {
          break;
        }
        mono.clear();
        mono.reserve(frames);
        if (flags & AUDCLNT_BUFFERFLAGS_SILENT) {
          mono.assign(frames, 0.0f);
        } else {
          Downmix(data, frames, &mono);
        }
        capture_->ReleaseBuffer(frames);

        if (resampler_ != nullptr && !mono.empty()) {
          const SherpaOnnxResampleOut *o = SherpaOnnxLinearResamplerResample(
              resampler_, mono.data(), static_cast<int32_t>(mono.size()), 0);
          if (o != nullptr) {
            PushRing(o->samples, static_cast<size_t>(o->n));
            SherpaOnnxLinearResamplerResampleFree(o);
          }
        } else if (!mono.empty()) {
          PushRing(mono.data(), mono.size());
        }
      }
    }
  }

  void Downmix(const BYTE *data, UINT32 frames, std::vector<float> *out) const {
    const size_t ch = src_channels_;
    for (UINT32 f = 0; f < frames; ++f) {
      double acc = 0.0;
      for (size_t c = 0; c < ch; ++c) {
        const BYTE *s = data + (static_cast<size_t>(f) * ch + c) * (src_bits_ / 8);
        if (src_is_float_) {
          float v = 0.0f;
          std::memcpy(&v, s, 4);
          acc += v;
        } else if (src_bits_ == 16) {
          int16_t v = 0;
          std::memcpy(&v, s, 2);
          acc += v / 32768.0;
        } else {
          int32_t v = 0;
          std::memcpy(&v, s, 4);
          acc += v / 2147483648.0;
        }
      }
      out->push_back(static_cast<float>(acc / static_cast<double>(ch)));
    }
  }

  std::unique_ptr<ComScope> com_;
  IAudioClient *client_ = nullptr;
  IAudioCaptureClient *capture_ = nullptr;
  WAVEFORMATEX *mix_format_ = nullptr;
  HANDLE event_ = nullptr;
  const SherpaOnnxLinearResampler *resampler_ = nullptr;

  CaptureOptions opts_;
  AudioDevice device_;
  int target_rate_ = 16000;
  bool native_format_ = false;  // device gave us 16 kHz/16-bit/mono directly
  int src_rate_ = 0;
  size_t src_channels_ = 1;
  int src_bits_ = 16;
  bool src_is_float_ = false;

  std::thread thread_;
  std::atomic<bool> stop_flag_ {false};
  std::atomic<bool> running_ {false};

  mutable std::mutex ring_mu_;
  std::vector<float> ring_;
  size_t ring_capacity_ = 0;
  size_t ring_read_ = 0;
  size_t ring_write_ = 0;
  size_t ring_size_ = 0;
  std::atomic<uint64_t> overruns_ {0};
};

}  // namespace

const char *AudioBackendName() { return "wasapi"; }

std::vector<AudioDevice> ListCaptureDevices(std::string *error) {
  ComScope com;
  EnumeratedDevices out;
  if (!EnumerateDevices(&out, error)) return {};
  return out.list;
}

std::unique_ptr<AudioCapture> AudioCapture::Create() {
  return std::unique_ptr<AudioCapture>(new WasapiCapture());
}

}  // namespace vcc

#endif  // _WIN32
