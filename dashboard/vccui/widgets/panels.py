"""The side panels: recording, model, filter, and the two editable lists.

Every control here follows one rule: changing it must not require repeating
yourself. Editing the hotword list re-decodes the audio already captured, and
because hotwords are passed per decode that costs no model reload. That is the
difference between a tool you tune with and a tool you demo with.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QPainter
from PyQt5.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QPlainTextEdit, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from ..theme import Theme

_MONO = ["Cascadia Mono", "Consolas", "DejaVu Sans Mono", "monospace"]


def mono_font(size: int = 10) -> QFont:
    font = QFont()
    font.setFamilies(_MONO)
    font.setStyleHint(QFont.Monospace)
    font.setPointSize(size)
    return font


class LevelMeter(QWidget):
    """Peak/RMS bar in dBFS.

    -60..0 dBFS across the width. Below -60 reads as silence, which is the
    range that matters for telling "too quiet" from "not speaking".
    """

    def __init__(self, theme: Theme, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.theme = theme
        self.peak = -120.0
        self.rms = -120.0
        self.clipped = False
        self.setMinimumHeight(14)
        self.setMaximumHeight(14)

    def update_level(self, peak: float, rms: float, clipped: bool) -> None:
        self.peak, self.rms, self.clipped = peak, rms, clipped
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        painter = QPainter(self)
        painter.setPen(Qt.NoPen)
        painter.setBrush(self.palette().base())
        painter.drawRoundedRect(self.rect(), 3, 3)

        def fraction(db: float) -> float:
            return max(0.0, min(1.0, (db + 60.0) / 60.0))

        width = self.rect().width()
        rms_w = int(width * fraction(self.rms))
        peak_x = int(width * fraction(self.peak))

        painter.setBrush(self.theme.meter_colour(self.peak, self.clipped))
        rect = self.rect()
        rect.setWidth(rms_w)
        painter.drawRoundedRect(rect, 3, 3)

        if peak_x > 1:
            painter.setBrush(QColor(self.theme.meter_colour(self.peak, self.clipped)))
            painter.drawRect(peak_x - 2, 0, 2, self.rect().height())


class RecordPanel(QGroupBox):
    """Device selection, push-to-talk, and the level meter.

    Push-to-talk rather than voice-activity detection: the boundaries of the
    clip are the speaker's choice, which is what you want both for a fair
    comparison and for a clip that is going into an evaluation corpus.
    """

    start_requested = pyqtSignal(int)
    stop_requested = pyqtSignal()
    cancel_requested = pyqtSignal()

    def __init__(self, theme: Theme, parent: Optional[QWidget] = None) -> None:
        super().__init__("Microphone", parent)
        self.theme = theme

        layout = QVBoxLayout(self)
        self.device = QComboBox()
        layout.addWidget(self.device)

        row = QHBoxLayout()
        self.button = QPushButton("Record")
        self.button.setMinimumHeight(34)
        self.button.clicked.connect(self._toggle)
        self.cancel = QPushButton("Discard")
        self.cancel.setToolTip("Stop without decoding")
        self.cancel.clicked.connect(self.cancel_requested.emit)
        self.cancel.setEnabled(False)
        row.addWidget(self.button, 1)
        row.addWidget(self.cancel)
        layout.addLayout(row)

        self.state = QLabel("idle")
        self.state.setFont(mono_font(9))
        layout.addWidget(self.state)

        self.meter = LevelMeter(theme)
        layout.addWidget(self.meter)
        self.level_text = QLabel("peak -  /  rms -")
        self.level_text.setFont(mono_font(9))
        self.level_text.setStyleSheet(f"color: {theme.hex(theme.muted)};")
        layout.addWidget(self.level_text)

        self.advice = QLabel()
        self.advice.setFont(mono_font(9))
        self.advice.setWordWrap(True)
        layout.addWidget(self.advice)

        hint = QLabel("Press Record, say one phrase, press Stop. "
                      "Space also toggles it.")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {theme.hex(theme.muted)};")
        layout.addWidget(hint)

        self._recording = False

    def _toggle(self) -> None:
        if self._recording:
            self.stop_requested.emit()
        else:
            index = self.device.currentData()
            self.start_requested.emit(-1 if index is None else int(index))

    def toggle(self) -> None:
        """Public entry point for the keyboard shortcut."""
        if self.button.isEnabled():
            self._toggle()

    def set_busy(self, busy: bool) -> None:
        self.button.setEnabled(not busy)
        if busy:
            self.button.setText("Decoding...")

    def apply_state(self, state: Dict[str, Any]) -> None:
        mics: List[Dict[str, Any]] = state.get("mics") or []
        rec = state.get("recording") or {}
        recording = bool(rec.get("active"))

        wanted = self.device.currentData()
        self.device.blockSignals(True)
        self.device.clear()
        if not mics:
            self.device.addItem(state.get("mic_error") or "no capture devices", -1)
        for mic in mics:
            bits = []
            if mic.get("sample_rate"):
                bits.append(f'{mic["sample_rate"]} Hz')
            if mic.get("channels"):
                bits.append(f'{mic["channels"]}ch')
            label = mic.get("name", "?")
            if mic.get("is_default"):
                label += "  (default)"
            if bits:
                label += "  - " + ", ".join(bits)
            self.device.addItem(label, mic.get("index", -1))
        if recording:
            idx = self.device.findData(rec.get("mic_index", -1))
            if idx >= 0:
                self.device.setCurrentIndex(idx)
        elif wanted is not None:
            idx = self.device.findData(wanted)
            if idx >= 0:
                self.device.setCurrentIndex(idx)
        self.device.blockSignals(False)

        self._recording = recording
        self.device.setEnabled(not recording)
        self.cancel.setEnabled(recording)
        self.button.setEnabled(True)
        self.button.setText("Stop and decode" if recording else "Record")
        self.button.setStyleSheet(
            f"font-weight: bold; color: {self.theme.hex(self.theme.bad)};"
            if recording else "")
        if not recording:
            self.state.setText("idle")
            self.state.setStyleSheet(f"color: {self.theme.hex(self.theme.muted)};")

    def on_level(self, payload: Dict[str, Any]) -> None:
        peak = float(payload.get("peak_dbfs", -120.0))
        rms = float(payload.get("rms_dbfs", -120.0))
        clipped = bool(payload.get("clipped"))
        self.meter.update_level(peak, rms, clipped)
        text = f"peak {peak:6.1f}  /  rms {rms:6.1f} dBFS"
        overruns = int(payload.get("overruns", 0))
        if overruns:
            text += f"   {overruns} samples dropped"
        self.level_text.setText(text)

        if "recorded_s" in payload:
            self.state.setText(f'recording {float(payload["recorded_s"]):.1f}s')
            self.state.setStyleSheet(f"color: {self.theme.hex(self.theme.bad)};")

        advice = self.theme.level_advice(peak, clipped)
        self.advice.setText(advice)
        self.advice.setStyleSheet(f"color: {self.theme.hex(self.theme.warn)};")

    def on_recording(self, payload: Dict[str, Any]) -> None:
        active = bool(payload.get("active"))
        self._recording = active
        self.button.setText("Stop and decode" if active else "Record")
        self.cancel.setEnabled(active)
        reason = payload.get("reason")
        if not active:
            self.state.setText(f"stopped ({reason})" if reason else "idle")
            self.state.setStyleSheet(f"color: {self.theme.hex(self.theme.muted)};")


class FilterPanel(QGroupBox):
    """The two filter stages and the boost, the knobs that matter."""

    changed = pyqtSignal(dict)

    def __init__(self, theme: Theme, parent: Optional[QWidget] = None) -> None:
        super().__init__("Filter", parent)
        self.theme = theme
        self._loading = False

        layout = QVBoxLayout(self)

        self.biasing = QCheckBox("Stage 1: contextual biasing (hotwords in the decoder)")
        self.rewrites = QCheckBox("Stage 2: rewrite rules over the text")
        self.biasing.toggled.connect(self._emit)
        self.rewrites.toggled.connect(self._emit)
        layout.addWidget(self.biasing)
        layout.addWidget(self.rewrites)

        form = QFormLayout()
        self.boost = QDoubleSpinBox()
        self.boost.setRange(0.0, 10.0)
        self.boost.setSingleStep(0.5)
        self.boost.setDecimals(1)
        self.boost.setToolTip(
            "Hotword boost. ONE value for the whole list -- there is no\n"
            "per-phrase score, on purpose: thirty knobs cannot be tuned well.\n\n"
            "THERE IS NO UNIVERSAL GOOD VALUE. It does not transfer between\n"
            "models, and resistance differs per word: zipformer-small-en flips a\n"
            "near-homophone between 2.0 and 3.0, while the medium zipformer never\n"
            "flips that word at any boost yet yields others at 4.0. Re-sweep\n"
            "after switching model.\n\n"
            "Too low and nothing bends. Too high and the decoder starts emitting\n"
            "your vocabulary out of noise, which is worse than not biasing:\n"
            "it fails silently and confidently.")
        self.boost.editingFinished.connect(self._emit)
        form.addRow("Hotword boost", self.boost)
        layout.addLayout(form)

        self.status = QLabel()
        self.status.setFont(mono_font(9))
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

    def _emit(self) -> None:
        if self._loading:
            return
        self.changed.emit({
            "biasing": self.biasing.isChecked(),
            "rewrites": self.rewrites.isChecked(),
            "hotwords_score": self.boost.value(),
            "redecode": True,
        })

    def apply_state(self, state: Dict[str, Any]) -> None:
        self._loading = True
        filt = state.get("filter") or {}
        loaded = state.get("loaded") or {}
        self.biasing.setChecked(bool(filt.get("biasing", True)))
        self.rewrites.setChecked(bool(filt.get("rewrites", True)))
        self.boost.setValue(float(loaded.get("hotwords_score", 2.0)))

        available = bool(loaded.get("biasing_available", False))
        self.biasing.setEnabled(available)
        if not available:
            blocker = loaded.get("biasing_blocker") or "no model loaded"
            self.status.setText(f"biasing unavailable: {blocker}")
            self.status.setStyleSheet(f"color: {self.theme.hex(self.theme.bad)};")
        else:
            active = filt.get("active", False)
            self.status.setText(
                f'{filt.get("hotword_count", 0)} hotword phrase(s) at boost '
                f'{self.boost.value():.1f}, '
                f'{filt.get("rewrite_count", 0)} rewrite rule(s)'
                + ("" if active else "   [not reaching the decoder]"))
            self.status.setStyleSheet(
                f"color: {self.theme.hex(self.theme.muted if active else self.theme.warn)};")
        self._loading = False


class ModelPanel(QGroupBox):
    """Model selection and the decoder settings that need a reload."""

    apply_requested = pyqtSignal(dict)

    def __init__(self, theme: Theme, parent: Optional[QWidget] = None) -> None:
        super().__init__("Model", parent)
        self.theme = theme

        layout = QVBoxLayout(self)
        self.model = QComboBox()
        layout.addWidget(self.model)

        form = QFormLayout()
        self.threads = QSpinBox()
        self.threads.setRange(1, 16)
        self.method = QComboBox()
        self.method.addItems(["modified_beam_search", "greedy_search"])
        self.method.setToolTip(
            "Only modified_beam_search honours hotwords. greedy_search silently\n"
            "ignores them, which makes the whole filter a no-op -- useful for\n"
            "seeing the unbiased baseline in isolation, useless otherwise.")
        self.blank = QDoubleSpinBox()
        self.blank.setRange(0.0, 5.0)
        self.blank.setSingleStep(0.1)
        self.blank.setDecimals(1)
        self.blank.setToolTip(
            "Negative pressure on the blank symbol. Helps recover the swallowed\n"
            "final consonants typical of Vietnamese-accented English.")
        form.addRow("Threads", self.threads)
        form.addRow("Decoding", self.method)
        form.addRow("Blank penalty", self.blank)
        layout.addLayout(form)

        self.button = QPushButton("Apply and reload model")
        self.button.clicked.connect(self._emit)
        layout.addWidget(self.button)

        self.info = QLabel()
        self.info.setFont(mono_font(9))
        self.info.setWordWrap(True)
        self.info.setStyleSheet(f"color: {theme.hex(theme.muted)};")
        layout.addWidget(self.info)

    def _emit(self) -> None:
        self.apply_requested.emit({
            "model": self.model.currentData() or "",
            "num_threads": self.threads.value(),
            "decoding_method": self.method.currentText(),
            "blank_penalty": self.blank.value(),
        })

    def set_busy(self, busy: bool) -> None:
        self.button.setEnabled(not busy)
        self.button.setText("Loading..." if busy else "Apply and reload model")

    def apply_state(self, state: Dict[str, Any]) -> None:
        models: List[Dict[str, Any]] = state.get("models") or []
        loaded = state.get("loaded") or {}

        wanted = loaded.get("id") or self.model.currentData()
        self.model.blockSignals(True)
        self.model.clear()
        if not models:
            self.model.addItem("no models installed", "")
        for model in models:
            label = f'{model.get("id")}  -  {model.get("describe")}'
            if not model.get("biasing_capable"):
                label += "  [no biasing]"
            self.model.addItem(label, model.get("id"))
        if wanted:
            idx = self.model.findData(wanted)
            if idx >= 0:
                self.model.setCurrentIndex(idx)
        self.model.blockSignals(False)

        if loaded:
            self.threads.setValue(int(loaded.get("num_threads", 4)))
            method = loaded.get("decoding_method", "modified_beam_search")
            idx = self.method.findText(method)
            if idx >= 0:
                self.method.setCurrentIndex(idx)
            self.blank.setValue(float(loaded.get("blank_penalty", 0.0)))
            self.info.setText(
                f'loaded in {loaded.get("load_ms", 0):.0f} ms   '
                f'sherpa-onnx {state.get("sherpa_version", "?")}')
        else:
            self.info.setText(
                "no model loaded - run scripts/download_models.sh, then Apply")


class ListEditor(QGroupBox):
    """A plain-text editor for one of the two data files.

    Plain text on purpose: the hotword file's format is one phrase per line with
    an optional score, and a table widget would make bulk edits (paste twenty
    phrases, comment five out) harder than the thing it replaced.
    """

    applied = pyqtSignal(str, bool)  # text, save_to_disk

    def __init__(self, title: str, hint: str, theme: Theme,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(title, parent)
        self.theme = theme

        layout = QVBoxLayout(self)
        label = QLabel(hint)
        label.setWordWrap(True)
        label.setStyleSheet(f"color: {theme.hex(theme.muted)};")
        layout.addWidget(label)

        self.editor = QPlainTextEdit()
        self.editor.setFont(mono_font(10))
        self.editor.setLineWrapMode(QPlainTextEdit.NoWrap)
        layout.addWidget(self.editor, 1)

        row = QHBoxLayout()
        self.apply_button = QPushButton("Apply")
        self.apply_button.setToolTip("Use it now, without writing to disk")
        self.save_button = QPushButton("Apply and save")
        self.save_button.setToolTip("Use it now and write the file")
        self.apply_button.clicked.connect(lambda: self._emit(False))
        self.save_button.clicked.connect(lambda: self._emit(True))
        row.addWidget(self.apply_button)
        row.addWidget(self.save_button)
        row.addStretch(1)
        self.status = QLabel()
        self.status.setFont(mono_font(9))
        row.addWidget(self.status)
        layout.addLayout(row)

    def _emit(self, save: bool) -> None:
        self.applied.emit(self.editor.toPlainText(), save)

    def set_text(self, text: str) -> None:
        # Do not stomp on an edit in progress.
        if self.editor.document().isModified():
            return
        self.editor.setPlainText(text)
        self.editor.document().setModified(False)

    def set_busy(self, busy: bool, message: str = "") -> None:
        self.apply_button.setEnabled(not busy)
        self.save_button.setEnabled(not busy)
        self.status.setText(message)
        self.status.setStyleSheet(f"color: {self.theme.hex(self.theme.muted)};")

    def mark_clean(self) -> None:
        self.editor.document().setModified(False)


class WirePanel(QGroupBox):
    """Exactly what the decoder was handed.

    Worth its screen space: the hotword pipeline has three ways to silently do
    nothing, and this pane is where "I edited the file but nothing changed"
    gets answered.
    """

    def __init__(self, theme: Theme, parent: Optional[QWidget] = None) -> None:
        super().__init__("Handed to the decoder", parent)
        layout = QVBoxLayout(self)
        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setFont(mono_font(9))
        self.view.setLineWrapMode(QPlainTextEdit.NoWrap)
        layout.addWidget(self.view)

    def set_text(self, text: str) -> None:
        self.view.setPlainText(text or "(nothing - biasing is not reaching the decoder)")


class LogPanel(QGroupBox):
    """The engine's stderr.

    When a model fails to load, sherpa-onnx's own diagnostics are the only
    explanation available. Hiding them in a terminal the user never sees would
    make every load failure a mystery.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__("Engine log", parent)
        layout = QVBoxLayout(self)
        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setFont(mono_font(9))
        self.view.setMaximumBlockCount(2000)
        self.view.setLineWrapMode(QPlainTextEdit.NoWrap)
        layout.addWidget(self.view)

    def append(self, lines: List[str]) -> None:
        for line in lines:
            self.view.appendPlainText(line)
