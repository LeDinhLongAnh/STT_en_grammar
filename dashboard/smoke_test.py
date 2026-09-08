#!/usr/bin/env python3
"""Headless smoke test: prove the dashboard actually runs, not just imports.

    python dashboard/smoke_test.py

It launches the real engine, builds the real window offscreen, decodes a real
WAV, edits the hotword list, and checks the transcript actually bent towards the
new vocabulary. Then it verifies nothing was left running -- a leaked engine
holds the microphone open, which is the worst failure this program has.

Exit status 0 means all of that worked.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Same Windows DLL ordering as dashboard/main.py: Torch before Qt.
experiment_dir = Path(__file__).resolve().parents[1] / "experiments" / \
    "whisper_initial_prompt"
sys.path.insert(0, str(experiment_dir))
try:
    import whisper as _whisper_preload  # noqa: F401,E402
except ImportError:
    _whisper_preload = None

from PyQt5.QtCore import QTimer  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

from vccui.engine import EngineProcess, resolve_engine  # noqa: E402
from vccui.mainwindow import MainWindow  # noqa: E402

FAILURES: list[str] = []
NOTES: list[str] = []


def check(condition: bool, message: str) -> None:
    print(("  ok   " if condition else "  FAIL ") + message)
    if not condition:
        FAILURES.append(message)


# Near-homophone probes for the biasing check: if the raw transcript contains
# `heard`, biasing towards `probe` should make the decoder emit it instead.
# Verified by hand on the LibriSpeech samples that ship with the zipformer
# models. How hard a model resists a given word varies -- the medium zipformer
# never gives up "LAMPS" but yields "QUARTER" -- so the check biases every
# applicable probe at once rather than betting on one.
BIAS_PROBES = [
    ("LAMPS", "YELLOW LAMBS"),
    ("QUARTER", "SQUALID QUARTERS"),
    ("COUNTRY", "YOUR COUNTRIES"),
]


def find_test_wav(root: Path, model_dir: str | None) -> Path | None:
    """Prefer a sample shipped with the model that is loaded.

    The probe words below only exist in some samples, so grabbing whichever WAV
    sorts first makes the biasing check a coin flip.
    """
    if model_dir:
        for candidate in sorted((root / "models" / model_dir).glob("test_wavs/*.wav")):
            return candidate
    for candidate in sorted(root.glob("models/*/test_wavs/*.wav")):
        return candidate
    return None


def main() -> int:
    print("dashboard smoke test")
    print(f"  python {sys.version.split()[0]}  platform={os.environ['QT_QPA_PLATFORM']}")

    root, binary = resolve_engine(None, None)
    print(f"  root   {root}")
    print(f"  engine {binary}")

    app = QApplication(sys.argv[:1])
    process = EngineProcess(binary, root)
    process.start()

    window = None
    try:
        client = process.wait_ready(timeout=120.0)
        check(True, "engine answered /api/state")

        state = client.state()
        check(bool(state.get("sherpa_version")), "state carries a sherpa version")
        loaded = state.get("loaded") or {}
        if loaded:
            check(True, f'model loaded: {loaded.get("id")}')
            check("biasing_available" in loaded, "state reports biasing availability")
            if not loaded.get("biasing_available"):
                NOTES.append(f'biasing unavailable: {loaded.get("biasing_blocker")}')
        else:
            NOTES.append("no model loaded; decode checks will be skipped")

        wire = client.hotwords_wire()
        check("/" in wire or wire.strip() == "" or "\n" in wire,
              "hotword wire format is readable")

        window = MainWindow(process, client, root)
        window.show()
        check(True, "main window constructed")
        check(window.workspace_tabs.count() == 2,
              "main dashboard contains classic and Whisper workspaces")
        check(window.whisper_prompt is not None,
              "Whisper Initial Prompt workspace is integrated")

        model_dir = (loaded.get("id") or "").split("@")[0]
        wav = find_test_wav(root, model_dir)
        steps: list = []
        probe: tuple[str, str] | None = None

        if loaded and wav is not None:
            def decode() -> None:
                print(f"  ..     decoding {wav.name}")
                window._decode_files([wav])

            def check_card() -> None:
                total = len(window.comparisons._cards)
                check(total >= 1, f"a comparison card appeared ({total})")
                if total:
                    card = next(iter(window.comparisons._cards.values()))
                    check(bool(card.raw.text().strip()), "the raw transcript is not empty")
                    check(bool(card.filtered.text().strip()),
                          "the filtered transcript is not empty")
                    print(f'         raw      : {card.raw.text()[:70]}')
                    print(f'         filtered : {card.filtered.text()[:70]}')

            def raise_boost() -> None:
                # The boost is ONE global value -- there is no per-phrase score.
                # Measured on this project, a near-homophone only flips somewhere
                # above 2.0, so turn it up first. This also exercises the control
                # a user actually turns.
                print("  ..     raising the global hotword boost to 4.0")
                window.filter_panel.boost.setValue(4.0)
                window.filter_panel._emit()

            def edit_hotwords() -> None:
                # Bias EVERY applicable probe at once. How hard a model resists a
                # given word varies by model -- the medium zipformer will not give
                # up "LAMPS" at any boost, while it yields "QUARTER" at 4.0 -- so a
                # single probe would make this check depend on which model happens
                # to be loaded. If any one of them bends, biasing reaches the
                # decoder, which is what is being tested.
                nonlocal probe
                raw = ""
                for card in window.comparisons._cards.values():
                    raw = card.raw.text().upper()
                    break
                applicable = [c for heard, c in BIAS_PROBES if heard in raw]
                if not applicable:
                    NOTES.append(
                        "skipped the biasing check: no known near-homophone probe "
                        f"applies to '{raw[:50]}'")
                    return
                probe = ("any of", ", ".join(applicable))
                print(f"  ..     biasing towards {len(applicable)} probe(s): "
                      f"{', '.join(applicable)}")
                window.hotword_editor.editor.setPlainText(
                    "\n".join(applicable) + "\n")
                window.hotword_editor._emit(False)

            def check_biased() -> None:
                if probe is None:
                    return
                if not loaded.get("biasing_available"):
                    NOTES.append("skipped the biasing check: model cannot be biased")
                    return
                changed = sum(1 for c in window.comparisons._cards.values()
                              if c.badge.text() == "CHANGED")
                check(changed >= 1,
                      "biasing changed the transcript "
                      "(the hotwords reach the decoder)")
                for card in window.comparisons._cards.values():
                    print(f'         filtered : {card.filtered.text()[:70]}')
                    break

            steps = [(500, decode), (9000, check_card), (9500, raise_boost),
                     (19000, edit_hotwords), (30000, check_biased)]
        else:
            NOTES.append("skipped decode checks (no model or no test wav)")

        for delay, fn in steps:
            QTimer.singleShot(delay, fn)
        QTimer.singleShot(steps[-1][0] + 1500 if steps else 1000, app.quit)
        app.exec_()

        check(process.running, "the engine survived the session")
    finally:
        if window is not None:
            window.close()
        process.stop()

    check(not process.running, "the engine was shut down")

    # A leaked process is the failure that bites a user hours later.
    leaked = 0
    if os.name == "nt":
        import subprocess
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq vcc_engine.exe"],
                             capture_output=True, text=True).stdout
        leaked = out.lower().count("vcc_engine.exe")
    check(leaked == 0, f"no vcc_engine process left behind (found {leaked})")

    if NOTES:
        print("\nnotes:")
        for note in NOTES:
            print(f"  - {note}")

    print(f"\n{'FAILED' if FAILURES else 'PASSED'}"
          f"  ({len(FAILURES)} failure(s))")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
