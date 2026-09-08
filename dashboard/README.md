# Dashboard

A PyQt5 client for `vcc_engine`. It shows, for every utterance, what the
recogniser said **without** the hotword bias and what the filter made of it —
side by side, with the changed words highlighted.

```bat
scripts\dashboard.bat
:: or
python dashboard\main.py
```

The engine is launched as a child process on a free port and killed when the
window closes. Nothing here decodes audio: what you see is exactly what the
device would produce.

**A user-facing walkthrough lives in [HUONG-DAN.md](HUONG-DAN.md)** (Vietnamese):
every panel, how to read a comparison card, how to tune the boost without
producing hallucinations, and how to get from "it looks better" to a WER number.
This file is the developer view — structure, options, and why it is built this
way.

## Requirements

```
pip install -r dashboard/requirements.txt
```

PyQt5 and the standard library, nothing else. `urllib` is enough for the API,
and one dependency is one thing that can break on a machine you do not control.

## The loop it is built for

1. **Record** — push-to-talk. Say one phrase, press Stop. Space toggles it.
2. **Read** — the card shows `raw`, `filtered`, and the word-level diff.
3. **Edit** — change `config/hotwords.txt` in the Hotwords tab, press Apply.
4. **Look again** — everything already recorded is re-decoded under the new
   list, with no model reload. You do not repeat yourself.

Step 4 is the reason the engine keeps the audio of the last 40 utterances in
memory, and the reason hotwords are passed per decode rather than baked into
the model.

## Panels

| panel | what it is for |
|---|---|
| **Microphone** | device pick, push-to-talk, level meter. The meter tells "the model is wrong" from "the mic did not hear me" — the most common confusion when testing STT. |
| **Filter** | the two stages, independently switchable, and the boost. Changing any of them re-decodes the history. |
| **Model** | model pick, threads, decoding method, blank penalty. Needs a reload, so it is a separate button. |
| **Hotwords** | the list, plus *Handed to the decoder* showing the exact serialised string. That pane is where "I edited the file but nothing changed" gets answered. |
| **Rewrites** | stage 2 rules. Applying these does not re-decode, only re-runs the text stage, so it is instant. |
| **Log** | the engine's stderr. When a model fails to load, sherpa-onnx's own diagnostics are the only explanation available. |

Apply uses the edited text without touching disk; **Apply and save** writes the
file. That split exists so you can try something ugly without dirtying the repo.

## Options

```
--attach URL     use an engine already running instead of launching one
--engine PATH    a specific vcc_engine binary
--root DIR       project root (default: autodetected)
--port N         port for the launched engine (default: a free one)
--model ID       model to load at startup
--no-copy        run the engine from build/bin instead of a temp copy
```

By default the engine is copied to a temp directory before launching. On Windows
a running executable is locked, so launching straight from `build/bin` makes a
concurrent `cmake --build` fail. `--no-copy` opts out.

## Structure

```
main.py              argument parsing, engine startup, error dialogs
smoke_test.py        headless end-to-end check (see below)
vccui/
  client.py          HTTP + SSE, all of it off the GUI thread
  engine.py          child-process supervision and readiness polling
  theme.py           colours derived from the Qt palette, so dark mode works
  mainwindow.py      wiring
  widgets/
    compare.py       the raw-vs-filtered card list
    panels.py        microphone, filter, model, list editors, log
```

Every network call runs in a `QThread`. A blocking read on the Qt event loop
freezes the window during exactly the operation you are trying to observe.

## Smoke test

```bat
python dashboard\smoke_test.py
```

Runs offscreen and proves the thing works rather than merely imports: launches
the real engine, builds the real window, decodes a real WAV, raises the global
boost, then biases towards every near-homophone probe that applies to that
transcript and checks the output actually bent.

It biases *all* the applicable probes rather than one because how hard a model
resists a given word varies by model — the medium zipformer never gives up
"LAMPS" at any boost while yielding "QUARTER" at 4.0 — so a single probe would
turn the check into a lottery over whichever model happens to be loaded.

Finally it verifies no engine process was left behind — a leaked engine holds the
microphone open, which is the worst failure this program has.
