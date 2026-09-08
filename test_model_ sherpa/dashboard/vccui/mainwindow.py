"""The dashboard window: wiring the panels to the engine.

The whole window exists to serve one loop:

    speak  ->  see raw vs filtered  ->  change the hotword list  ->  see it again

The last arrow is the one that had to be cheap, and it is: hotwords are handed to
the decoder per decode, so applying an edited list re-runs the audio already
captured with no model reload.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from PyQt5.QtCore import Qt, QTimer, pyqtSlot
from PyQt5.QtGui import QDragEnterEvent, QDropEvent, QKeySequence
from PyQt5.QtWidgets import (
    QCheckBox, QFileDialog, QHBoxLayout, QLabel, QMainWindow, QMessageBox,
    QPushButton, QShortcut, QSplitter, QStatusBar, QTabWidget, QVBoxLayout,
    QWidget,
)

from .client import ApiWorker, EngineClient, EventStream
from .engine import EngineProcess
from .theme import Theme
from .widgets.compare import ComparisonList
from .widgets.panels import (
    FilterPanel, ListEditor, LogPanel, ModelPanel, RecordPanel, WirePanel, mono_font,
)
from .whisper_prompt import create_whisper_prompt_dashboard
from .sherpa_vi_prompt import create_sherpa_vi_dashboard

HOTWORD_HINT = (
    "One phrase per line, no score - the boost on the Control tab covers the "
    "whole list (a legacy ':2.5' is ignored with a warning). Phrases beat single "
    "words. Applying re-decodes everything below - no model reload, because "
    "hotwords are passed per decode."
)

REWRITE_HINT = (
    "pattern => replacement, over the text after decoding. Use this only for a "
    "substitution that survives biasing: fixing it in the decoder generalises, "
    "fixing it here does not."
)


class MainWindow(QMainWindow):
    def __init__(self, process: Optional[EngineProcess], client: EngineClient,
                 root: Path) -> None:
        super().__init__()
        self.process = process
        self.client = client
        self.root = root
        self.theme = Theme()
        self._workers: List[ApiWorker] = []
        self._log_cursor = 0

        self.setWindowTitle("Contextual-biasing STT - raw vs filtered")
        self.resize(1420, 900)
        self.setAcceptDrops(True)

        self._build_ui()
        self._connect_events()

        # First paint, then load: the window should appear immediately even if
        # the engine is still bringing a model up.
        QTimer.singleShot(0, self.refresh_state)
        QTimer.singleShot(0, self.refresh_history)
        QTimer.singleShot(0, self.refresh_lists)

        # Space is the natural push-to-talk key, and the transcript panes are
        # read-only so nothing else wants it.
        record_shortcut = QShortcut(QKeySequence(Qt.Key_Space), self)
        record_shortcut.activated.connect(
            lambda: self.record_panel.toggle()
            if self.workspace_tabs.currentIndex() == 0 else None)

        self._log_timer = QTimer(self)
        self._log_timer.timeout.connect(self._poll_log)
        self._log_timer.start(500)

    # -- construction ------------------------------------------------------

    def _build_ui(self) -> None:
        self.workspace_tabs = QTabWidget()
        classic = QWidget()
        outer = QHBoxLayout(classic)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(8)

        # Left: the comparison stream, which is what the user actually reads.
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)

        header = QHBoxLayout()
        self.summary = QLabel("no results yet")
        self.summary.setFont(mono_font(10))
        self.text_button = QPushButton("Decode a WAV file...")
        self.text_button.clicked.connect(self._choose_files)
        self.norm_check = QCheckBox("normalise level")
        self.clear_button = QPushButton("Clear")
        self.clear_button.clicked.connect(self._clear_history)
        header.addWidget(self.summary)
        header.addStretch(1)
        header.addWidget(self.norm_check)
        header.addWidget(self.text_button)
        header.addWidget(self.clear_button)
        left_layout.addLayout(header)

        self.comparisons = ComparisonList(self.theme)
        self.comparisons.count_changed.connect(self._on_counts)
        left_layout.addWidget(self.comparisons, 1)

        # Right: the controls, tabbed so the window fits on a laptop.
        right = QTabWidget()
        right.setMinimumWidth(430)
        right.setMaximumWidth(560)

        control_tab = QWidget()
        control_layout = QVBoxLayout(control_tab)
        self.record_panel = RecordPanel(self.theme)
        self.filter_panel = FilterPanel(self.theme)
        self.model_panel = ModelPanel(self.theme)
        control_layout.addWidget(self.record_panel)
        control_layout.addWidget(self.filter_panel)
        control_layout.addWidget(self.model_panel)
        control_layout.addStretch(1)
        right.addTab(control_tab, "Control")

        self.hotword_editor = ListEditor("Hotwords", HOTWORD_HINT, self.theme)
        self.wire_panel = WirePanel(self.theme)
        hotword_tab = QWidget()
        hotword_layout = QVBoxLayout(hotword_tab)
        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(self.hotword_editor)
        splitter.addWidget(self.wire_panel)
        splitter.setSizes([500, 200])
        hotword_layout.addWidget(splitter)
        right.addTab(hotword_tab, "Hotwords")

        self.rewrite_editor = ListEditor("Rewrites", REWRITE_HINT, self.theme)
        right.addTab(self.rewrite_editor, "Rewrites")

        self.log_panel = LogPanel()
        right.addTab(self.log_panel, "Log")

        outer.addWidget(left, 1)
        outer.addWidget(right)
        self.workspace_tabs.addTab(classic, "Contextual Hotwords (sherpa-onnx)")

        self.whisper_prompt = None
        try:
            self.whisper_prompt = create_whisper_prompt_dashboard(
                self.root, self.workspace_tabs)
            self.workspace_tabs.addTab(
                self.whisper_prompt, "Whisper base.en — Initial Prompt")
        except Exception as exc:
            unavailable = QWidget()
            unavailable_layout = QVBoxLayout(unavailable)
            message = QLabel(
                "Whisper Initial Prompt chưa sẵn sàng.\n\n"
                f"{exc}\n\n"
                "Chạy experiments\\whisper_initial_prompt\\setup.ps1 -DownloadModel, "
                "sau đó mở lại scripts\\dashboard.bat.")
            message.setWordWrap(True)
            unavailable_layout.addWidget(message)
            unavailable_layout.addStretch(1)
            self.workspace_tabs.addTab(unavailable, "Whisper Initial Prompt (unavailable)")

        self.sherpa_vi = None
        try:
            self.sherpa_vi = create_sherpa_vi_dashboard(
                self.root, self.workspace_tabs)
            self.workspace_tabs.addTab(
                self.sherpa_vi, "Sherpa-ONNX Zipformer VI")
        except Exception as exc:
            unavailable2 = QWidget()
            unavailable2_layout = QVBoxLayout(unavailable2)
            message2 = QLabel(
                "Sherpa-ONNX Zipformer VI chưa sẵn sàng.\n\n"
                f"{exc}\n\n"
                "Kiểm tra lại model tại models\\sherpa-onnx-zipformer-vi "
                "và đảm bảo sherpa-onnx đã được cài (pip install sherpa-onnx).")
            message2.setWordWrap(True)
            unavailable2_layout.addWidget(message2)
            unavailable2_layout.addStretch(1)
            self.workspace_tabs.addTab(
                unavailable2, "Sherpa-ONNX Zipformer VI (unavailable)")

        self.setCentralWidget(self.workspace_tabs)

        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage(f"engine: {self.client.base_url}")

        self.record_panel.start_requested.connect(self._start_record)
        self.record_panel.stop_requested.connect(self._stop_record)
        self.record_panel.cancel_requested.connect(self._cancel_record)
        self.filter_panel.changed.connect(self._apply_filter)
        self.model_panel.apply_requested.connect(self._apply_model)
        self.hotword_editor.applied.connect(self._apply_hotwords)
        self.rewrite_editor.applied.connect(self._apply_rewrites)

    def _connect_events(self) -> None:
        self.events = EventStream(self.client.base_url, self)
        self.events.level.connect(self.record_panel.on_level)
        self.events.recording.connect(self.record_panel.on_recording)
        self.events.utterance.connect(self._on_utterance)
        self.events.connected.connect(self._on_connected)
        self.events.start()

    # -- worker plumbing ---------------------------------------------------

    def _run(self, fn: Callable[[], Any], on_done: Callable[[Any], None],
             on_error: Optional[Callable[[str], None]] = None) -> None:
        """Run an engine call off the GUI thread.

        The worker is kept in a list so it is not garbage-collected mid-flight,
        which is the classic PyQt bug that shows up as a silent no-op.
        """
        worker = ApiWorker(fn, self)
        self._workers.append(worker)

        def cleanup() -> None:
            if worker in self._workers:
                self._workers.remove(worker)

        worker.done.connect(on_done)
        worker.done.connect(lambda _: cleanup())
        worker.failed.connect(on_error or self._show_error)
        worker.failed.connect(lambda _: cleanup())
        worker.start()

    def _show_error(self, message: str) -> None:
        self.statusBar().showMessage(message, 12000)

    # -- refreshes ---------------------------------------------------------

    def refresh_state(self) -> None:
        self._run(self.client.state, self._apply_state)

    def refresh_history(self) -> None:
        self._run(self.client.history, self.comparisons.set_items)

    def refresh_lists(self) -> None:
        self._run(self.client.hotwords, self.hotword_editor.set_text)
        self._run(self.client.rewrites, self.rewrite_editor.set_text)
        self._run(self.client.hotwords_wire, self.wire_panel.set_text)

    @pyqtSlot(object)
    def _apply_state(self, state: Any) -> None:
        if not isinstance(state, dict):
            return
        self.record_panel.apply_state(state)
        self.filter_panel.apply_state(state)
        self.model_panel.apply_state(state)

        loaded = state.get("loaded") or {}
        model = loaded.get("id", "no model")
        filt = state.get("filter") or {}
        bits = [f"engine {self.client.base_url}", f"model {model}"]
        if loaded:
            bits.append("biasing "
                        + ("on" if filt.get("active") else "off"))
        self.statusBar().showMessage("   |   ".join(bits))

        for warning in state.get("warnings") or []:
            self.log_panel.append([f"[warning] {warning}"])

    # -- actions -----------------------------------------------------------

    def _start_record(self, index: int) -> None:
        self._run(lambda: self.client.record_start(index), self._apply_state)

    def _stop_record(self) -> None:
        # The engine decodes the take twice before answering, so the button has
        # to say something other than "Record" in the meantime.
        self.record_panel.set_busy(True)

        def done(state: Any) -> None:
            self.record_panel.set_busy(False)
            self._apply_state(state)

        def failed(message: str) -> None:
            self.record_panel.set_busy(False)
            self._show_error(message)
            self.refresh_state()

        self._run(self.client.record_stop, done, failed)

    def _cancel_record(self) -> None:
        self._run(self.client.record_cancel, self._apply_state)

    def _apply_filter(self, payload: Dict[str, Any]) -> None:
        self.statusBar().showMessage("re-decoding with the new filter settings...")

        def done(state: Any) -> None:
            self._apply_state(state)
            self.refresh_history()
            self.refresh_lists()

        self._run(lambda: self.client.set_filter(**payload), done)

    def _apply_model(self, payload: Dict[str, Any]) -> None:
        self.model_panel.set_busy(True)

        def done(state: Any) -> None:
            self.model_panel.set_busy(False)
            self._apply_state(state)
            self.refresh_history()

        def failed(message: str) -> None:
            self.model_panel.set_busy(False)
            self._show_error(message)

        self._run(lambda: self.client.load_model(**payload), done, failed)

    def _apply_hotwords(self, text: str, save: bool) -> None:
        self.hotword_editor.set_busy(True, "re-decoding...")

        def done(state: Any) -> None:
            self.hotword_editor.set_busy(False, "applied" + (" and saved" if save else ""))
            self.hotword_editor.mark_clean()
            self._apply_state(state)
            self.refresh_history()
            self._run(self.client.hotwords_wire, self.wire_panel.set_text)

        def failed(message: str) -> None:
            self.hotword_editor.set_busy(False, "")
            self._show_error(message)

        self._run(lambda: self.client.set_hotwords(text, save), done, failed)

    def _apply_rewrites(self, text: str, save: bool) -> None:
        self.rewrite_editor.set_busy(True, "applying...")

        def done(state: Any) -> None:
            self.rewrite_editor.set_busy(False, "applied" + (" and saved" if save else ""))
            self.rewrite_editor.mark_clean()
            self._apply_state(state)
            self.refresh_history()

        def failed(message: str) -> None:
            self.rewrite_editor.set_busy(False, "")
            self._show_error(message)

        self._run(lambda: self.client.set_rewrites(text, save), done, failed)

    def _clear_history(self) -> None:
        def done(state: Any) -> None:
            self.comparisons.clear_all()
            self._apply_state(state)

        self._run(self.client.clear_history, done)

    def _choose_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Decode WAV files", str(self.root), "WAV audio (*.wav)")
        if paths:
            self._decode_files([Path(p) for p in paths])

    def _decode_files(self, paths: List[Path]) -> None:
        normalize = self.norm_check.isChecked()
        for path in paths:
            try:
                data = path.read_bytes()
            except OSError as exc:
                self._show_error(f"{path.name}: {exc}")
                continue
            name = path.name
            self.statusBar().showMessage(f"decoding {name}...")
            self._run(
                lambda d=data, n=name: self.client.recognize_wav(d, n, normalize),
                self._on_decoded)

    @pyqtSlot(object)
    def _on_decoded(self, items: Any) -> None:
        if not isinstance(items, list):
            return
        if not items:
            self._show_error("no speech found in that file")
            return
        for item in items:
            self.comparisons.upsert(item)
        self.statusBar().clearMessage()

    # -- events ------------------------------------------------------------

    @pyqtSlot(dict)
    def _on_utterance(self, payload: Dict[str, Any]) -> None:
        self.comparisons.upsert(payload)

    @pyqtSlot(bool)
    def _on_connected(self, connected: bool) -> None:
        if not connected:
            self.statusBar().showMessage("event stream disconnected, retrying...", 4000)

    def _on_counts(self, total: int, changed: int) -> None:
        if total == 0:
            self.summary.setText("no results yet")
        else:
            self.summary.setText(
                f"{total} utterance(s)   |   the filter changed {changed}")

    def _poll_log(self) -> None:
        if self.process is None:
            return
        lines, self._log_cursor = self.process.log_lines(self._log_cursor)
        if lines:
            self.log_panel.append(lines)
        if not self.process.running:
            self._log_timer.stop()
            QMessageBox.critical(
                self, "Engine stopped",
                "The engine process exited.\n\n"
                + "\n".join(self.process.log_text().splitlines()[-20:]))

    # -- drag and drop -----------------------------------------------------

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls()]
        wavs = [p for p in paths if p.suffix.lower() == ".wav"]
        if wavs:
            self._decode_files(wavs)
            event.acceptProposedAction()

    # -- shutdown ----------------------------------------------------------

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        """Tear down in dependency order.

        The engine holds the microphone, so it must not outlive the window: on
        Windows a leaked engine keeps the mic busy until somebody finds it in
        Task Manager.
        """
        self._log_timer.stop()
        if self.whisper_prompt is not None:
            self.whisper_prompt.shutdown()
        if self.sherpa_vi is not None:
            self.sherpa_vi.shutdown()
        self.events.stop()
        self.events.wait(1500)
        for worker in list(self._workers):
            worker.wait(1500)
        if self.process is not None:
            self.process.stop()
        super().closeEvent(event)
