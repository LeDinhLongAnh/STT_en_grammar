#!/usr/bin/env python3
"""Prove the Whisper prompt workspace works inside the existing dashboard."""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = ROOT / "experiments" / "whisper_initial_prompt"
sys.path.insert(0, str(EXPERIMENT))
sys.path.insert(0, str(ROOT / "dashboard"))

# Windows DLL order: Torch before PyQt.
import whisper as _whisper_preload  # noqa: F401,E402

from PyQt5.QtCore import QTimer  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

from vccui.engine import EngineProcess, resolve_engine  # noqa: E402
from vccui.mainwindow import MainWindow  # noqa: E402


def main() -> int:
    root, binary = resolve_engine(str(ROOT), None)
    process = EngineProcess(binary, root)
    # Managed test environments may expose %TEMP% read-only. Running directly
    # from build/bin is safe here because the smoke does not rebuild binaries.
    process.start(copy_binaries=False)
    window = None
    try:
        client = process.wait_ready(timeout=120.0)
        app = QApplication(sys.argv[:1])
        window = MainWindow(process, client, root)
        window.show()
        assert window.workspace_tabs.count() == 2
        prompt = window.whisper_prompt
        assert prompt is not None
        assert prompt.example_combo.count() >= 8
        assert prompt.strength_combo.currentData() == 2
        prompt._use_sample()
        assert prompt.wav_path is not None

        finished = {"value": False}
        prompt._run_decode()
        assert prompt.worker is not None

        def done(_result) -> None:
            finished["value"] = True
            app.quit()

        prompt.worker.completed.connect(done)
        QTimer.singleShot(30000, app.quit)
        app.exec_()
        assert finished["value"], "integrated Whisper decode timed out"
        assert all(card.transcript.toPlainText().strip()
                   for card in prompt.cards.values())
        print("integrated dashboard smoke: classic engine + Whisper tab + 3 decodes OK")
        return 0
    finally:
        if window is not None:
            window.close()
        process.stop()


if __name__ == "__main__":
    sys.exit(main())
