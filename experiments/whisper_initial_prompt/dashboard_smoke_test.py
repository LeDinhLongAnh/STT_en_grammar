#!/usr/bin/env python3
"""Construct the prompt dashboard offscreen without touching the microphone."""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Import the dashboard first so its Windows-safe Torch-before-Qt ordering is
# exercised. Importing QApplication here first would recreate WinError 1114.
from dashboard import QApplication, WhisperPromptDashboard  # noqa: E402
from PyQt5.QtCore import QTimer  # noqa: E402


def main() -> int:
    app = QApplication(sys.argv[:1])
    window = WhisperPromptDashboard()
    assert window.scenario_combo.count() == 12
    assert window.example_combo.count() >= 8
    assert window.strength_combo.currentData() == 2
    assert "V3-LEAN" in window.global_prompt_label.text()
    assert "124/223" in window.global_prompt_label.text()
    assert len(window.cards) == 3
    window._use_sample()
    assert window.wav_path is not None and window.wav_path.is_file()
    # Deliberately select the wrong expected label after choosing network audio.
    # It must not control the automatically selected scenario prompt.
    window.scenario_combo.setCurrentIndex(8)
    assert window.scenario_combo.currentData() == "block_internet"
    finished = {"value": False}
    decoded = {"result": None}
    window._run_decode()
    assert window.worker is not None

    def done(result) -> None:
        finished["value"] = True
        decoded["result"] = result
        app.quit()

    window.worker.completed.connect(done)
    QTimer.singleShot(30000, app.quit)
    app.exec_()
    assert finished["value"], "dashboard decode did not finish within 30 seconds"
    assert decoded["result"]["auto_scenario_id"] == "network_status"
    assert all(card.transcript.toPlainText().strip() for card in window.cards.values())
    window.close()
    app.processEvents()
    print("prompt dashboard smoke: wrong selected label ignored, auto-routed network_status")
    return 0


if __name__ == "__main__":
    sys.exit(main())
