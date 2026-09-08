---
description: Measure whether the biasing filter actually improves WER
argument-hint: [extra vcc_cli flags, e.g. --set asr.hotwords_score=3]
---

Run the recorded-corpus evaluation and interpret it.

```
./build/bin/vcc_cli.exe --eval tests/data/manifest.tsv $ARGUMENTS
```

Report, in this order:

1. **clips worsened** — must be 0. A filter that raises the average WER while
   breaking individual utterances is not ready. If non-zero, name the
   substitutions from the "introduced" list and propose removing the hotword or
   rewrite rule responsible.
2. **relative gain** — the headline number. If it is near zero, run
   `./build/bin/vcc_cli.exe --show-hotwords` and check biasing is actually
   reaching the decoder: it needs an offline transducer, modified_beam_search,
   and a bpe.vocab beside the model, and fails silently when one is missing.
3. WER raw vs filtered, and the mean RTF.

If most clips are reported as missing files, say so plainly: the corpus has not
been recorded yet (`vcc_listen --save-dir tests/data/clips`) and the numbers mean
nothing until it is. Do not invent a conclusion from placeholder rows.

Useful comparisons to offer: `--no-biasing` and `--no-rewrites` isolate the two
stages, and a sweep over `asr.hotwords_score` finds the sweet spot (expect
2.0-3.0, and expect it to get worse above that, not better).
