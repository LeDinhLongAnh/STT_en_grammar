# Tests

Three layers, deliberately separate.

## 1. Unit tests — logic, no model, no audio hardware

```bat
build\bin\vcc_tests.exe            :: everything
build\bin\vcc_tests.exe hotwords   :: substring filter on "suite.name"
build\bin\vcc_tests.exe wer
```

`ctest --test-dir build` runs the same binary.

| file | what it pins down |
|---|---|
| [test_hotwords.cpp](test_hotwords.cpp) | the hotword list and **its wire format** — read this one first |
| [test_diff.cpp](test_diff.cpp) | word diff, WER and CER, against hand-worked examples |
| [test_text.cpp](test_text.cpp) | tokenisation and the rewrite table, including case preservation |
| [test_wav.cpp](test_wav.cpp) | WAV codec, level metering, resampling |
| [test_config.cpp](test_config.cpp) | `config/app.ini` parsing and `--set` overrides |
| [test_json.cpp](test_json.cpp) | the engine's wire format |
| [test_models.cpp](test_models.cpp) | model auto-detection per sherpa-onnx directory layout |

`test_hotwords.cpp` matters most. The per-stream hotword string splits on `/`,
not newline, and getting that subtly wrong makes biasing silently do nothing
while everything still looks fine. `serialises_slash_separated_for_the_per_stream_api`
is the case that would catch it.

Sub-second, no external dependency beyond the sherpa-onnx DLL that `wav.cpp`
links for its resampler. Run them on every change.

## 2. Accuracy evaluation — your voice, a real model

Unit tests cannot tell you whether the filter helps *you*. That needs recorded
audio and a reference transcript, which is what
[data/manifest.tsv](data/manifest.tsv) is for.

```bat
:: 1. record: push-to-talk, one phrase per take
build\bin\vcc_listen.exe --save-dir tests\data\clips

:: 2. label: write what you MEANT to say, tab-separated, in manifest.tsv

:: 3. measure
build\bin\vcc_cli.exe --eval tests\data\manifest.tsv
```

Output:

```
clip                           raw     filt    transcript
----------------------------------------------------------------------------
take-0009.wav                   33.3%    0.0% <- TURN ON GUEST WIFI
                                 raw: TURN ON GAS WIFI
                                 ref: turn on guest wifi
take-0014.wav                   25.0%   25.0%    SET BANDWIDTH LIMIT FIFTY
============================================================================
WER raw         :  31.4%   (11 sub, 2 del, 0 ins)
WER filtered    :  17.1%   (6 sub, 1 del, 0 ins)
relative gain   : +45.5%   <-- the number this project exists for

clips improved  : 7
clips unchanged : 11
clips worsened  : 0   <-- drive this to zero before chasing gain
```

Read it in this order:

1. **clips worsened** — must be 0. A filter that raises the average while
   breaking three utterances is not ready to ship. The `substitutions the filter
   introduced` list at the bottom names the culprits.
2. **relative gain** — the headline. If it is near zero, check
   `vcc_cli --show-hotwords` first: biasing has three prerequisites and fails
   silently when one is missing.
3. **WER raw** on its own tells you how bad the problem is, which is worth
   knowing before claiming a fix.

### Sweeping a parameter

Everything in `config/app.ini` is overridable per run:

```bat
for %s in (0 1.0 2.0 2.5 3.0 4.0) do ^
  build\bin\vcc_cli.exe --quiet --set asr.hotwords_score=%s --eval tests\data\manifest.tsv

build\bin\vcc_cli.exe --no-biasing  --eval tests\data\manifest.tsv   :: stage 1 off
build\bin\vcc_cli.exe --no-rewrites --eval tests\data\manifest.tsv   :: stage 2 off
```

Those last two are how you find out which stage is actually earning its keep.
Expect the boost sweep to have a sweet spot around 2.0–3.0 and to get *worse*
above it, not better — an overconfident bias hallucinates your vocabulary out of
noise.

`--min-gain 20` exits 2 when the gain falls below 20%, which makes this a CI
gate once the corpus is real.

### Why the clips are not in the repo

Audio is large, and a corpus recorded by one speaker only proves the filter works
for that speaker. `tests/data/clips/` is gitignored: record your own, and record
a colleague with a different accent too — the whole premise of this project is
that accent is the variable.

## 3. Dashboard smoke test — the whole stack

```bat
python dashboard\smoke_test.py
```

Launches the real engine, builds the real Qt window offscreen, decodes a real
WAV, then edits the hotword list to a near-homophone of a word in that
transcript and asserts the output bent towards it. That last check is the only
automated proof that contextual biasing is reaching the decoder at all.

It also verifies no engine process was left running afterwards.
