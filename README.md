# Contextual-biasing STT for non-native English

A speech-to-text component that stops mis-hearing Vietnamese- and
Indian-accented English on a fixed router vocabulary, by pushing that vocabulary
into the decoder as contextual bias (forced hotwords).

**Scope.** This project produces *text*. What happens to that text — intent
matching, slot filling, acting on the command — is somebody else's layer. The
one job here is: the speaker said "turn on guest network", so the output must say
"turn on guest network" and not "turn on gas network".

```
                     ┌─► decode, no hotwords ─────────────────────────► raw
  audio ─────────────┤
                     └─► decode, hotwords ───► rewrite rules ────────► filtered
                            stage 1               stage 2
```

Both decodes run on **the same loaded model**, so the comparison isolates exactly
one variable: the bias. That is what the dashboard shows you, side by side, on
every utterance.

---

## Quick start (Windows)

```bat
:: 1. libraries and models  (Git Bash)
bash scripts/fetch_sherpa_onnx.sh
bash scripts/download_models.sh

:: 2. build  (Visual Studio 2022 Build Tools, C++ workload)
scripts\build.bat Release test

:: 3. the dashboard
scripts\dashboard.bat
```

Prerequisites: Git Bash, CMake ≥ 3.16, VS 2022 Build Tools, Python 3 with
PyQt5 (`pip install -r dashboard/requirements.txt`) and `sentencepiece`
(needed once, to build the hotword vocabulary).

Driving the dashboard: **[dashboard/HUONG-DAN.md](dashboard/HUONG-DAN.md)**
(hướng dẫn tiếng Việt) — panel by panel, plus how to tune the boost and how to
turn what you see into a WER number.

---

## How the biasing actually works

sherpa-onnx tokenises each hotword phrase into BPE units and builds an
**Aho-Corasick automaton** over them — a prefix tree with goto, failure and
output arcs. Each phrase's score is spread evenly across its arcs, so a partial
match earns a partial bonus and that bonus is cancelled again if the match never
completes. The bias applies **during beam search**, so it changes which
hypothesis wins rather than patching up the loser afterwards. That is why it can
recover a word whose final consonant was never clearly pronounced, which is
exactly the Vietnamese-accent failure mode.

### The tree is the decoder's, not the model's

Worth being precise about, because the name invites the opposite guess: this has
nothing to do with Zipformer. Zipformer is a neural encoder — its "zip" is a
downsampling stack, there is no tree in it. The tree is built at decode time from
*your hotword list*, and it lives in the beam search.

What the model has to supply is only two things:

1. a **transducer (RNN-T) decoder**, so tokens are emitted one at a time under a
   beam — that is what gives the automaton somewhere to add its score;
2. the **BPE inventory** the hotwords are tokenised with, so the tree's arcs are
   labelled with units the decoder can actually emit.

The catalogue contains the pair that settles the argument: `zipformer-ctc` has
the *same Zipformer encoder* and cannot be biased, while the NeMo Parakeet
transducer is not a Zipformer at all and can. Swap the encoder, biasing survives;
swap the decoder, it disappears.

The practical consequence is that a streaming Zipformer is biasable too — same
decoder, different chunking — which is why `ModelFamily` has two transducer
entries rather than one.

Two implementation choices matter more than anything else here.

### Hotwords are passed per decode, not baked into the model

The recogniser is created with **no** hotwords file. Biasing is handed to an
individual decode instead. Three consequences, all of them load-bearing:

* the same audio can be decoded unbiased *and* biased from one model in memory,
  so the before/after is honest and the memory budget survives;
* editing the hotword list costs **nothing** — no model reload, no two-second
  pause. Tuning becomes interactive;
* the dashboard can re-decode audio you already recorded under a new list, so
  you do not have to keep repeating yourself.

The trap, if you ever change this: a configured hotwords file becomes a
permanent floor that per-stream hotwords are *added* to, and then there is no way
to get an unbiased baseline without loading a second model.

### The wire format has a separator you would not guess

The per-stream hotwords argument splits on `/`, not on newline. A
newline-joined list arrives as one giant bogus hotword and biases nothing.
`HotwordList::Serialize()` joins with `/`, uppercases (the English BPE
inventories these models ship with are uppercase), and drops any phrase
containing `/` with a warning.

### Three ways it silently does nothing

Biasing needs **all three** of the following, and sherpa-onnx reports no error
when one is missing:

1. a **transducer** model, offline or streaming — Whisper, Moonshine and the CTC
   families have no biasing hook at all;
2. `decoding_method = modified_beam_search` — greedy search ignores hotwords;
3. a **`bpe.vocab`** beside the model, so a phrase can be tokenised into the
   same subword units the decoder emits. Without it the only available
   `modeling_unit` is `cjkchar`, which splits English words into single letters
   that never line up with anything.

The engine checks all three at load time and says which one failed;
`ModelRegistry` marks affected models `hotwords blocked` with the reason. The
`bpe.vocab` case is the sneaky one — the published tarball for the primary model
does not contain `bpe.model`, so `scripts/download_models.sh` fetches a matching
one keyed by the SHA-1 of `tokens.txt` and generates the vocabulary from it.

### One boost for the whole list

`config/hotwords.txt` is one phrase per line and nothing else — no per-phrase
score. sherpa-onnx supports one; this project deliberately does not use it,
because a per-phrase knob is a per-phrase decision and thirty of those cannot be
tuned well. One number can be swept against a corpus in an afternoon. A leftover
`:2.5` on a line is accepted and ignored, with a warning.

That one number matters a lot, and **it does not transfer between models.**
Measured here with `YELLOW LAMBS` biased against audio that says "yellow lamps":

| model | boost 0.5–2.0 | 3.0 | 4.0 | 12.0 |
|---|---|---|---|---|
| `zipformer-small-en` | LAMPS | **LAMBS** | LAMBS | LAMBS |
| `zipformer-en` (medium) | LAMPS | LAMPS | LAMPS | LAMPS |

The medium model never yields on that word. It is not that biasing fails there —
`SQUALID QUARTERS`, `THE BROTHERS` and `EARLY NIGHTFALLS` all bend it at boost
4.0. It is that a more accurate acoustic model is *more confident*, so the same
boost buys less. Resistance is per-word too: the same model gives up one word and
not another.

Three practical consequences:

* **Re-sweep the boost whenever you change model.** A value tuned on the small
  zipformer is not a value for the medium one.
* Resistance is a feature, not only a nuisance: a model that ignores your bias on
  a word it heard clearly is a model that will not hallucinate your vocabulary
  out of noise. That failure mode is worse than under-biasing, because it is
  silent and confident.
* **Over-biasing can delete words, not just replace them.** With four probes at
  boost 4.0 the offline models substituted in place — same word count, same
  positions — while the streaming model collapsed "nightfall the yellow lamps"
  into "nightfalls", losing three words. A chunked encoder has no right context to
  contradict a strongly boosted path, so it commits and drops what followed. Watch
  the **length** of the filtered line, not only its words.
* Since a single boost covers the whole list, **every phrase you add makes the
  ones you need weaker**. Delete anything that never fires.

Sweep it against a recorded corpus rather than guessing —
`vcc_cli --eval` with `--set asr.hotwords_score=...` in a loop.

### Stage 2, and when to use it

`config/rewrites.txt` repairs substitutions that survive biasing —
`gues`/`gas`/`gust` → `guest`, `band width` → `bandwidth`. Order of preference:

1. **add the phrase to `config/hotwords.txt`** (and, if it is still not enough,
   nudge the global boost). Fixing it in the decoder generalises to nearby
   phrasings.
2. only if it still comes out wrong the same way twice, add a rewrite rule.

A rule is surgical by design. The tempting alternative — a fuzzy
nearest-neighbour pass over the whole transcript — fixes the case you were
looking at and quietly corrupts words you were not.

---

## What you get

| binary | purpose |
|---|---|
| `vcc_engine` | the STT service: model, microphone, filter, HTTP + SSE API. No UI. |
| `vcc_listen` | push-to-talk in a terminal; `--save-dir` builds the corpus |
| `vcc_cli` | decode WAV files, and **measure WER** raw vs filtered |
| `vcc_tests` | unit tests, no model or microphone needed |
| `dashboard/` | PyQt5 dashboard — launches the engine and shows raw vs filtered |

```bat
build\bin\vcc_cli.exe --list-models
build\bin\vcc_cli.exe --show-hotwords
build\bin\vcc_cli.exe clip.wav
build\bin\vcc_cli.exe --eval tests\data\manifest.tsv
build\bin\vcc_cli.exe --no-biasing clip.wav     :: baseline in isolation
build\bin\vcc_listen.exe --list-mics
build\bin\vcc_listen.exe --save-dir tests\data\clips
```

`vcc_cli` on one clip:

```
clip.wav  (2.10s, peak -14 dBFS)
  raw      : "TURN ON GAS NETWORK"
  filtered : "TURN ON GUEST NETWORK"
  diff     : turn on [gas -> guest] network
  rules    : gas => guest
  timing   : raw 61 ms, biased 68 ms (rtf 0.03)
```

### Audio path: 16 kHz, 16-bit, mono

That is what the acoustic models were trained on and what the router's ALSA
capture will hand over, so the dev box matches it exactly. The WASAPI backend
asks the device for that format directly (shared mode with
`AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM`, so Windows' own resampler does the work
before the data reaches us) and falls back to the mix format plus our own
resample only if the driver refuses. On this machine the direct path works:

```
capturing from 'Headset Microphone': 16000 Hz 16-bit mono (device native)
```

Either way the samples are **quantised to 16-bit before leaving the capture
layer**. That is not cosmetic: it makes a clip saved as 16-bit PCM decode to
exactly what was decoded live, so a recorded corpus measures the same audio you
heard the result for.

### There is no VAD

Input is one phrase per clip: push-to-talk in the dashboard and in
`vcc_listen`, one file per utterance for `vcc_cli`. An endpointer in the middle
would add a variable that has nothing to do with the accent problem, and
push-to-talk means every clip has exactly the boundaries you chose — which is
what you want when the clip is going into an evaluation corpus.

---

## Measuring it

An impression is not a result. `--eval` takes a TSV of
`<wav>` TAB `<what you actually said>` and reports word error rate before and
after the filter:

```
WER raw         :  31.4%   (11 sub, 2 del, 0 ins)
WER filtered    :  17.1%   (6 sub, 1 del, 0 ins)
relative gain   : +45.5%   <-- the number this project exists for

clips improved  : 7
clips unchanged : 11
clips worsened  : 0   <-- drive this to zero before chasing gain

substitutions the filter fixed:
    4x  gas -> guest
    2x  band width -> bandwidth
substitutions the filter introduced (look here first):
    (none)
```

Read **clips worsened** before anything else: a filter that raises the average
while breaking three utterances is not ready. `--min-gain 20` makes it a CI
gate. Full loop in [tests/README.md](tests/README.md).

---

## Configuration

| file | contents |
|---|---|
| `config/app.ini` | model, threads, boost, the two filter switches |
| `config/hotwords.txt` | **the vocabulary to force into the decoder** |
| `config/rewrites.txt` | text repairs for what biasing could not fix |

Any key is overridable per run, which is what makes a sweep a loop rather than
an edit:

```bat
for %s in (1.0 2.0 2.5 3.0) do ^
  build\bin\vcc_cli.exe --set asr.hotwords_score=%s --eval tests\data\manifest.tsv
```

The hotword list ships with the router vocabulary for the target scenarios —
network and router status, device info, online devices, gaming sessions, guest
Wi-Fi, QoS, bandwidth limit, block/unblock internet and applications.

---

## Models

Pick one in the dashboard's Model panel, or with `--model` on the command line.
`vcc_cli --list-models` shows what is installed and whether each can be biased.

| model | size | biasing | notes |
|---|---|---|---|
| `sherpa-onnx-zipformer-small-en-2023-06-26` | 27 MB | **yes** | the primary. RTF ≈ 0.04, most responsive to bias |
| `sherpa-onnx-zipformer-en-2023-06-26` | 67 MB | **yes** | medium zipformer: better WER, resists bias harder |
| `sherpa-onnx-streaming-zipformer-en-2023-02-21` | 128 MB | **yes** | streaming. Over budget — comparison only, see below |
| `sherpa-onnx-whisper-base.en` | see below | no | encoder-decoder baseline |
| `sherpa-onnx-moonshine-tiny-en-quantized` | 42 MB | no | baseline only — cannot be biased |

All three zipformers share the LibriSpeech BPE-500 inventory, so
`download_models.sh` derives `bpe.vocab` for all of them from the same verified
`bpe.model` (matched by the SHA-1 of `tokens.txt`).

`scripts/download_models.sh --all` adds the large zipformer, NeMo Parakeet 110M,
Whisper tiny.en and the streaming zipformer; `--list` shows the catalogue.
Everything is defined in `scripts/models.catalog` — add a row to add a model.

**Only the two transducer families can be biased.** Whisper, Moonshine and the
CTC families have no biasing hook in sherpa-onnx, so selecting one turns the
feature off entirely. They are worth keeping around to answer "is the problem in
the acoustic model or in the language prior?", and the dashboard marks them
`[no biasing]` rather than pretending.

### Whisper: no biasing, and no way to fake it

Whisper is an encoder-decoder attention model, so there is nowhere to attach a
context graph — it is a baseline, not a candidate.

**Initial prompt is not an escape hatch.** Whisper the model can be conditioned
on a prompt, but `SherpaOnnxOfflineWhisperModelConfig` in v1.13.6 exposes only
`encoder`, `decoder`, `language`, `task` and `tail_paddings` — no
`initial_prompt`, no `prompt`. Verified by compiling against the header rather
than by reading docs; the same probe accepted `hotwords_file` and
`tail_paddings`, so it was the field that was missing, not the test. Reaching it
would mean patching sherpa-onnx, which breaks the one rule that makes this code
cross-compile onto the router.

And prompt conditioning would be the wrong tool anyway: it shifts a *prior* over
the whole utterance. It cannot guarantee a score for a specific token sequence,
gives no single scalar to sweep, and Whisper is known for echoing prompts into
the transcript. Contextual biasing is a *forced* mechanism; a prompt is a
suggestion.

Measured here, base.en int8 against the primary zipformer, 4 threads:

| clip | whisper base.en | zipformer-small-en |
|---|---|---|
| 0.70 s | 194 ms (RTF 0.28) | 44 ms (RTF 0.06) |
| 1.50 s | 574 ms (RTF 0.38) | — |
| 3.00 s | 723 ms (RTF 0.24) | 165 ms (RTF 0.06) |
| 6.62 s | 1217 ms (RTF 0.18) | 501 ms (RTF 0.08) |
| 16.71 s | 3165 ms (RTF 0.19) | — |

Short clips do pay a visible fixed overhead — RTF climbs to 0.24–0.38 below
1.5 s — but cost still scales with length, so there is no flat 30-second floor to
budget around. The reasons it is not a router candidate are simpler and
independent: **153 MB of weights** (the int8 *decoder alone* is 124.6 MB, 4.6× the
entire primary model, because of Whisper's 51 864-token vocabulary), 2–4× the
decode time, and no biasing at all.

One integration note: Whisper emits **cased, punctuated** text where the
zipformers emit upper case. Stage-2 rewrite rules still fire (both sides are
lowercased on load), but that is the documented weak path for case restoration —
see `RewriteTable::Apply`.

### Streaming: supported, measurable, and over budget

`ModelFamily` has two transducer entries because the biasing hook belongs to the
decoder, so a streaming Zipformer has it too. Streaming exports load under
sherpa-onnx's *online* recogniser, which needs the audio pumped through a
ready/decode loop plus a tail of silence to flush the encoder's last chunk —
`AsrEngine` hides that, so `Recognize()` behaves the same either way.

Offline is still what ships, for three measured reasons:

* the only English streaming export is **128 MB int8** — its encoder alone is
  127 MB, against a 200 MB whole-system budget;
* a chunked encoder commits to the start of a word before hearing the end, and
  for accented speech the end of the word is exactly where the information is;
* the utterances are one to three seconds, so streaming buys a latency nobody
  perceives.

`ModelRegistry` therefore never picks a streaming model as the default, even if
it were the smallest one installed — the ordering encodes that. It stays
selectable so the question can be settled with a measurement instead of this
paragraph.

### Memory

Measured on this dev box, 2-second utterance, `asr.num_threads=3`, one decode:

```
peak working set: 139 MB     (27 MB weights + ONNX Runtime arenas + CRT + DLLs)
decode: 60 ms, RTF 0.03
```

Inside a 200 MB budget but not comfortably, and a Windows working set is not
directly comparable to an `aarch64` one. Re-measure on the target. The dual
decode is a *dashboard* feature — the device runs the biased decode only, so it
pays the memory once and the CPU once. Mitigations, in order:
[docs/porting-arm.md](docs/porting-arm.md).

---

## Layout

```
include/vcc/     public headers, one per module
src/             implementations
  apps/          vcc_cli, vcc_listen, vcc_engine
config/          app.ini, hotwords.txt, rewrites.txt
dashboard/       PyQt5 client (main.py, vccui/, smoke_test.py)
models/          downloaded weights (gitignored)
scripts/         fetch_sherpa_onnx.sh, download_models.sh, build.bat, dashboard.bat
tests/           unit tests + the evaluation corpus
third_party/     prebuilt sherpa-onnx (gitignored)
```

| module | responsibility |
|---|---|
| `core` | strings, paths, timing |
| `config` | ini-ish key/value with `section.key` addressing |
| `hotwords` | the hotword list and its wire format |
| `text` | tokenisation and the rewrite table |
| `diff` | word-level diff, WER and CER |
| `wav` | RIFF codec, level metering, resampling |
| `models` | model auto-detection by filename layout |
| `asr` | sherpa-onnx wrapper, biased and unbiased decode |
| `audio` | WASAPI capture (Windows) / null fallback |
| `pipeline` | the two-stage filter |
| `json`, `http` | engine plumbing |

The project binds the sherpa-onnx **C** API deliberately: it is `extern "C"`, so
the same source links against a prebuilt MSVC DLL here and a cross-compiled
`.so` on the Cortex-A55 target regardless of compiler or C++ runtime.

---

## Security note

`vcc_engine` binds `127.0.0.1` and has **no authentication**. It is a
development service and should not ship on the device; build the target image
with `-DVCC_BUILD_ENGINE=OFF`. The library and `vcc_cli` are what the device
needs.
