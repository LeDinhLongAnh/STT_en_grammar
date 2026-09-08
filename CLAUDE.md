# CLAUDE.md

Working notes for AI agents on this repository. Read this before changing code.

## What this project is, and is not

**Is:** a speech-to-text component that stops mis-hearing Vietnamese- and
Indian-accented English on a fixed router vocabulary, by pushing that vocabulary
into the decoder as contextual bias (forced hotwords). Output is *text*.

**Is not:** intent matching, slot filling, or command execution. That is a
different team's layer. If you find yourself writing an intent matcher, a
command catalogue, or an action enum, stop — that work was deliberately removed
from this repository.

Development on Windows; deployment target is a quad-core Cortex-A55 with a
200 MB RAM budget.

## The two things that must not be broken

**1. The recogniser is created with no hotwords file.** Biasing is passed
per-decode, via `SherpaOnnxCreateOfflineStreamWithHotwords`. This is not a
stylistic choice:

* a configured hotwords file becomes a permanent floor that per-stream hotwords
  are *added* to (see `offline-recognizer-transducer-impl.h`), so there would be
  no way to produce an unbiased baseline without loading a second model;
* per-decode hotwords make an edit free — no model reload — which is what makes
  the dashboard's tuning loop interactive.

**2. The wire format splits on `/`, not newline.** sherpa-onnx regex-replaces
`/` with `\n` before parsing the per-stream hotword string. Join with `/`,
uppercase everything, and drop phrases containing `/`. `HotwordList::Serialize()`
does this and `tests/test_hotwords.cpp` pins it.

## Build and test

```bat
bash scripts/fetch_sherpa_onnx.sh      :: once
bash scripts/download_models.sh        :: once
scripts\build.bat Release test
```

MSVC is not on PATH; the batch file finds `vcvars64.bat` via `vswhere`. From
elsewhere:

```
powershell -NoProfile -Command "$vs='C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat'; cmd /c \"call `\"$vs`\" >nul 2>nul && cmake --build build --parallel\""
```

Three layers, run all three after a non-trivial change:

```bat
build\bin\vcc_tests.exe                 :: 99 cases, sub-second, no model
build\bin\vcc_cli.exe clip.wav          :: end-to-end decode
python dashboard\smoke_test.py          :: engine + UI + a real biasing check
```

The tree builds `/W4 /WX` clean. Keep it that way.

## Architecture

```
audio ──┬─► asr, no hotwords ──────────────────────────► raw
        └─► asr, hotwords ─────► rewrite table ────────► filtered
              stage 1               stage 2
```

`src/pipeline.cpp` is the only place that wires modules together; the three apps
in `src/apps/` are thin front-ends over it.

| you want to… | change |
|---|---|
| add vocabulary to bias towards | `config/hotwords.txt` — data only, no rebuild |
| change the capture format | `src/audio_wasapi.cpp` — but 16 kHz is what the models want |
| fix a substitution biasing cannot | `config/rewrites.txt` |
| change how hotwords reach the decoder | `src/asr.cpp` + `tests/test_hotwords.cpp` |
| change WER accounting | `src/diff.cpp` + `tests/test_diff.cpp` |
| support a new model layout | `src/models.cpp` `BuildProfile()` + `tests/test_models.cpp` |
| port to a new platform | implement `AudioCapture` from `include/vcc/audio.h` |
| explain the dashboard to a user | `dashboard/HUONG-DAN.md` (Vietnamese) |

## Conventions

* C++17. Google-ish style: `PascalCase` functions and types, `snake_case`
  locals, `trailing_underscore_` members, 2-space indent, 90-ish columns.
* Headers in `include/vcc/`, one per module. Public headers carry the *why*;
  implementations carry the *how*.
* Errors: return `bool` and fill a `std::string *error`. No exceptions across
  module boundaries. `VCC_WARN` / `VCC_ERROR` for things a user should see.
* **Bind the sherpa-onnx C API, not the C++ API.** `extern "C"` means the same
  source links against a prebuilt MSVC DLL here and a cross-compiled `.so` on
  the target.
* No new third-party dependencies. The HTTP server, JSON codec, WAV codec and
  test harness are local and small on purpose — this has to cross-compile onto a
  router. The dashboard depends on PyQt5 and the standard library, nothing else.

## Traps that have already bitten

* **Biasing has three prerequisites** and sherpa-onnx reports no error when one
  is missing: a transducer (offline *or* streaming), `modified_beam_search`, and a
  `bpe.vocab` beside the model. `AsrEngine::Load()` checks all three and names the
  failure.
* **Streaming models truncate their last word without tail padding.** A chunk-wise
  encoder cannot emit the tail until it has been handed enough future frames, and
  the result looks exactly like a recognition error rather than a plumbing bug.
  `kOnlineTailPaddingS` in `src/asr.cpp` feeds the silence.
* **Two tells for a streaming export, and neither is universal.**
  `pruned_transducer_stateless7_streaming` puts the chunk geometry in the
  filenames; the 2023-02-21 export does not, and only its directory name says
  "streaming". `BuildProfile()` checks both, and `tests/test_models.cpp` pins each
  case separately.
* **Whisper cannot be biased, and `initial_prompt` is not a workaround.**
  `SherpaOnnxOfflineWhisperModelConfig` (v1.13.6) has `encoder`, `decoder`,
  `language`, `task`, `tail_paddings` and nothing else — no `initial_prompt`, no
  `prompt`. Established by compiling a probe against the header (`hotwords_file`
  and `tail_paddings` compiled in the same harness, so the harness was sound).
  Reaching it would mean patching sherpa-onnx, which the cross-compile rule
  forbids. Conceptually it is also the wrong mechanism: a prompt shifts a prior,
  it cannot guarantee a score for a token sequence, and there is no scalar to
  sweep.
* **Whisper's decode cost is NOT flat.** An earlier note here claimed the 30 s mel
  window made it constant; measured, it scales with length (0.70 s → 194 ms,
  6.62 s → 1217 ms, 16.71 s → 3165 ms). Short clips pay a fixed overhead — RTF
  0.24–0.38 below 1.5 s vs 0.18 at 6.6 s — but there is no 30-second floor. The
  real reasons it is baseline-only: 153 MB of weights (int8 decoder alone is
  124.6 MB, from the 51 864-token vocabulary), 2–4× a zipformer's decode time,
  and no biasing hook.
* **Whisper emits cased, punctuated text**; the zipformers emit upper case. Any
  code comparing transcripts across families has to normalise first.
* **The primary model's tarball has no `bpe.model`.** `scripts/download_models.sh`
  fetches a matching one keyed by the SHA-1 of `tokens.txt`
  (`scripts/bpe_sources.txt`) and generates `bpe.vocab` from it. A `bpe.model`
  from the wrong vocabulary would tokenise silently wrong.
* **`functiondiscoverykeys_devpkey.h` include order.** It uses
  `DEFINE_PROPERTYKEY` without including what defines it, so `mmdeviceapi.h`
  must come first. `src/audio_wasapi.cpp` has a `clang-format off` guard. Do not
  alphabetise those includes.
* **sherpa-onnx `exit()`s** when ONNX Runtime cannot open a model file. `Load()`
  stats every path first so the failure is a message, not a dead process.
* **The C structs hold borrowed `const char *`.** Every path handed to
  `SherpaOnnxCreateOfflineRecognizer` lives in `AsrEngine::Impl`, not a local.
* **`%.3f` of an exact binary tie** rounds to even. Do not assert on `0.8125`.
* **Heredocs with `\n` inside C++ string literals** get mangled by this
  environment's shell. Use the Write/Edit tools for such edits, not `cat <<EOF`.

## The biasing tree belongs to the decoder, not to Zipformer

A recurring wrong guess, so it is written down. sherpa-onnx tokenises the
hotwords into BPE units and builds an **Aho-Corasick automaton** (goto / failure /
output arcs) over them, spreading each phrase's score across its arcs so a
partial match earns a partial bonus that is withdrawn if the match never
completes. That tree is built **at decode time from the hotword list** and lives
in the beam search. Zipformer is a neural encoder — its "zip" is a downsampling
stack, and there is nothing tree-shaped in it.

The model only has to supply two things: a **transducer decoder** (tokens emitted
one at a time under a beam, which is where the score attaches) and the **BPE
inventory** the arcs are labelled with.

The pair in `scripts/models.catalog` that proves it: `zipformer-ctc` has the same
Zipformer encoder and cannot be biased, while the NeMo Parakeet transducer is not
a Zipformer and can. Swap the encoder and biasing survives; swap the decoder and
it is gone.

Consequences for this code:

* `ModelFamily` has **two** transducer entries. Streaming Zipformers are biasable
  and load under the *online* recogniser — a separate config struct and a
  ready/decode pump, plus `kOnlineTailPaddingS` of silence to flush the last
  chunk. `AsrEngine::Recognize()` hides the difference.
* Do not look for a "Zipformer tree" to optimise. There isn't one. The cost knobs
  are `max_active_paths` and the size of the hotword list.

## Empirical facts worth not re-deriving

* **The boost does not transfer between models.** With `YELLOW LAMBS` biased
  against a clip saying "yellow lamps": `zipformer-small-en` flips between 2.0
  and 3.0; `zipformer-en` (medium) never flips, even at 12.0 — while
  `SQUALID QUARTERS`, `THE BROTHERS` and `EARLY NIGHTFALLS` all bend it at 4.0.
  A more accurate model is more confident, so the same boost buys less, and
  resistance is per-word as well as per-model. Re-sweep after changing model.
  Do not restate a single "usable band" as if it were universal — that was an
  earlier claim measured on one model and one word.
* **The streaming model fails structurally, not just wrongly.** Same clip, same
  four probes (`EARLY NIGHTFALLS`, `YELLOW LAMBS`, `SQUALID QUARTERS`,
  `THE BROTHERS`) against "after early nightfall the yellow lamps ... the squalid
  quarter of the brothels":

  | model | boost 2.0 | boost 4.0 |
  |---|---|---|
  | `streaming-zipformer-en-2023-02-21` | LAMBS, QUARTERS | **"after early nightfalls would light up"** — three words deleted |
  | `zipformer-small-en` | NIGHTFALLS, QUARTERS, BROTHERS | all four, structure intact |
  | `zipformer-en` (medium) | NIGHTFALLS, QUARTERS, BROTHERS | unchanged; LAMPS never yields |

  The offline models substitute *in place*: word count and positions survive, so a
  bad boost costs you one wrong word. The streaming model collapsed
  "nightfall the yellow lamps" into "nightfalls" — a chunked encoder with no right
  context can commit to a hotword path and lose the words that followed. Deleting
  words is a worse failure than substituting them, and it is another reason
  streaming is not the shipped path.
* **One boost for the whole list.** `config/hotwords.txt` has no per-phrase
  score by design; a legacy `:2.5` is parsed and ignored with a warning. Do not
  reintroduce per-phrase scores.
* WASAPI accepts a direct request for 16 kHz / 16-bit / mono in shared mode when
  `AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM` is set — verified on this machine
  ("device native" in the capture log). The mix-format fallback exists for
  drivers that refuse.
* Capture quantises to 16-bit before the ring buffer. That is deliberate: it
  makes live decoding and corpus decoding see identical samples, and matches the
  target's ALSA path.
* Peak working set 139 MB, 2 s utterance, 3 threads, one decode. RTF 0.03.
* The dual decode is a dashboard feature. The device runs the biased decode
  only.

## Do not

* Reintroduce intent matching, command catalogues or slot filling.
* Reintroduce a VAD. Input is one phrase per clip by design.
* Commit model weights or recorded audio; `scripts/download_models.sh`
  reproduces the models.
* Ship `vcc_engine` on the device — localhost bind, no authentication.
  `-DVCC_BUILD_ENGINE=OFF` for the target image.
* Make a streaming model the default, or ship one. The online recogniser exists
  so the streaming-vs-offline question can be *measured*; the only English export
  is 128 MB int8 against a 200 MB whole-system budget, and a chunked encoder
  throws away the right context that accented speech needs most. The sort in
  `ModelRegistry::Scan` encodes this and a test pins it.
