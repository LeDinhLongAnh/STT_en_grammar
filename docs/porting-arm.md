# Porting to the Cortex-A55 router

The Windows build is the development environment. This is what changes for the
target: quad-core Cortex-A55, Embedded Linux, 200 MB RAM for this feature.

Only one file is platform-specific. Everything else already compiles for
`aarch64`.

---

## 1. sherpa-onnx for aarch64

The official releases include a shared `linux-aarch64` build:

```sh
./scripts/fetch_sherpa_onnx.sh --platform linux-aarch64
```

That is enough to get going. For the shipped image you almost certainly want to
build it yourself, for two reasons: to link statically (no `libonnxruntime.so`
to install), and to cut ONNX Runtime down to the operators these models
actually use.

```sh
git clone --depth 1 -b v1.13.6 https://github.com/k2-fsa/sherpa-onnx
cd sherpa-onnx
cmake -B build-aarch64 \
  -DCMAKE_TOOLCHAIN_FILE=/path/to/aarch64-toolchain.cmake \
  -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_SHARED_LIBS=OFF \
  -DSHERPA_ONNX_ENABLE_TTS=OFF \
  -DSHERPA_ONNX_ENABLE_PYTHON=OFF \
  -DSHERPA_ONNX_ENABLE_PORTAUDIO=OFF \
  -DSHERPA_ONNX_ENABLE_WEBSOCKET=OFF \
  -DSHERPA_ONNX_ENABLE_BINARY=OFF \
  -DSHERPA_ONNX_ENABLE_C_API=ON
cmake --build build-aarch64 --target sherpa-onnx-c-api -j4
```

Then arrange the result the way `CMakeLists.txt` expects — `include/` and
`lib/` under one root — and point at it:

```sh
cmake -S . -B build-arm \
  -DCMAKE_TOOLCHAIN_FILE=/path/to/aarch64-toolchain.cmake \
  -DSHERPA_ONNX_DIR=/path/to/sherpa-aarch64 \
  -DVCC_BUILD_ENGINE=OFF \
  -DVCC_BUILD_TESTS=ON \
  -DCMAKE_BUILD_TYPE=Release
cmake --build build-arm -j4
```

`VCC_BUILD_ENGINE=OFF` is not optional for a shipped image: the engine binds
localhost with no authentication (see the security note in the README). Keep
`VCC_BUILD_TESTS` on — the unit tests need no model and no microphone, so running
them on the device is a cheap sanity check that the cross-build is sound.

The reason this port is boring is the C API choice: `sherpa-onnx-c-api` is
`extern "C"`, so nothing in `src/` depends on which compiler or C++ runtime
built the library.

---

## 2. The one file you have to write: ALSA capture

`src/audio_null.cpp` compiles on non-Windows and honestly reports that there is
no microphone. Replace it with `src/audio_alsa.cpp` implementing the interface in
[`include/vcc/audio.h`](../include/vcc/audio.h):

```cpp
const char *AudioBackendName();                          // "alsa"
std::vector<AudioDevice> ListCaptureDevices(std::string *error);
std::unique_ptr<AudioCapture> AudioCapture::Create();
```

and, on the returned object:

```cpp
bool Start(const CaptureOptions &opts, std::string *error);
void Stop();
bool running() const;
size_t Read(float *dst, size_t max_samples);   // non-blocking, mono, at opts.sample_rate
uint64_t overruns() const;
```

Four properties the WASAPI backend has that the ALSA one needs too:

* **`Read()` never blocks.** A capture thread fills a ring buffer; `Read()`
  drains it. The decode loop must never be able to stall the audio thread.
* **On overrun, drop the oldest samples and count it.** Losing the start of a
  stale recording beats blocking. `overruns()` is surfaced in the UI and in
  `vcc_listen`'s exit summary, because a non-zero value means the consumer cannot
  keep up with the configured buffer — which is exactly the thing you want to
  find out on the target, not in the field.
* **Resample inside the backend.** The device runs at whatever rate it runs at;
  callers only ever see `opts.sample_rate`. Use
  `SherpaOnnxCreateLinearResampler` — the same call the Windows backend uses, so
  there is no second resampler implementation to keep honest.
* **Downmix to mono in the backend** as well, for the same reason.

Then swap the file in `CMakeLists.txt`:

```cmake
if(WIN32)
  target_sources(vcc_core PRIVATE src/audio_wasapi.cpp)
elseif(UNIX AND NOT APPLE)
  target_sources(vcc_core PRIVATE src/audio_alsa.cpp)
  target_link_libraries(vcc_core PUBLIC asound)
else()
  target_sources(vcc_core PRIVATE src/audio_null.cpp)
endif()
```

(The current list compiles both `audio_wasapi.cpp` and `audio_null.cpp`
unconditionally and lets `#ifdef _WIN32` pick one. That is fine while there are
two backends; with three, the CMake conditional above is clearer.)

A useful intermediate step: run the whole pipeline on the target with
`vcc_cli <clip>.wav` before the capture backend exists. That validates the
model, the threading, and the memory footprint with zero audio code.

---

## 3. Configuration for the target

```ini
[filter]
biasing  = true        ; the whole point of the component
rewrites = true

[asr]
num_threads = 3        ; leave one A55 for the rest of the router
precision   = int8
decoding_method = modified_beam_search   ; required for biasing
max_active_paths = 4   ; drop to 2 if CPU is tight; costs a little accuracy
hotwords_score = 2.0   ; tune against the corpus, not by feel

[audio]
mic_index    = 0
sample_rate  = 16000
max_record_s = 30

[log]
level = warn           ; info logs every utterance
```

`max_active_paths` is the first knob to turn if CPU is short: beam width 4 → 2
roughly halves decode cost. Measure the accuracy delta on the evaluation corpus
before accepting it.

---

## 4. Budget

Measured on the Windows dev box, primary model, 2-second utterance,
`num_threads = 3`, **one** decode — which is what the device runs. The dual
decode is a dashboard feature for showing the before/after; production biases
once and is done.

| | |
|---|---|
| peak working set | 139 MB |
| decode | 60 ms (RTF 0.03) |
| model on disk | 27 MB |

139 MB fits in 200 MB, but not with much room, and the number does not transfer
directly — a Windows working set accounts for the mapped `onnxruntime.dll` and
CRT pages differently from an `aarch64` ELF. **Re-measure on the target first**
(`/proc/<pid>/status`, `VmHWM`) before treating the budget as settled.

If it is tight, in the order worth trying:

1. **Minimal ONNX Runtime build.** The stock library carries kernels for every
   model family; a `--minimal_build` with a reduced operator set is the largest
   single saving available.
2. **`num_threads = 2`.** Each intra-op thread brings its own arena. RTF has the
   headroom: 0.03 on a desktop core survives an A55's several-fold slowdown with
   room left over, so trading threads for memory is the right direction.
3. **Shrink or disable the ONNX Runtime arena.** Arena reuse is tuned for
   sustained throughput; a 2-second utterance every few seconds does not benefit
   much from it.
4. **`sherpa-onnx-moonshine-tiny-en`** is smaller on disk — but it gives up
   contextual biasing, which is the main accuracy mechanism for accented speech.
   Treat this as a last resort and measure the accuracy cost on the corpus.

---

## 5. Handing the text on

This component's output is a string, and the next layer — intent matching, slot
filling, acting on the command — belongs to somebody else. The integration point
is one call:

```cpp
const Comparison c = pipeline.Process(audio);
if (c.ok) {
  HandOffToIntentLayer(c.final_text());   // == c.filtered
}
```

Three things worth agreeing with whoever owns that layer:

* **Which string.** `filtered` is the product. `raw` exists so a human can see
  what the filter did; nothing downstream should consume it. `Comparison::final_text()`
  names the answer so the question stops coming up.
* **Casing.** The zipformer models emit uppercase; Moonshine emits sentence case.
  The rewrite stage preserves whichever it was given (see the note in
  `RewriteTable::Apply`), so the intent layer must not assume one or the other —
  it should lowercase before matching.
* **The device only needs the biased decode.** Run with `filter.biasing = true`
  and do not call the unbiased path: it doubles CPU for a comparison nobody on
  the device is looking at. `Pipeline::Process` currently always does both; on
  the target, add a flag or call `AsrEngine::Recognize` directly with the
  serialised hotwords. That is a ~10-line change and halves the decode cost.

`src/apps/vcc_cli.cpp` is the reference for a file-in, text-out flow, and
`src/apps/vcc_listen.cpp` for capture-to-text.

---

## 6. What does not come along

* **No VAD.** Input is one phrase per clip. If the device needs to decide *when*
  someone is talking, that is a wake-word or a button, and it belongs upstream of
  this component.
* **No intent layer.** Deliberately not in this repository.
* **No dashboard.** `dashboard/` and `vcc_engine` are development tools; neither
  ships.
