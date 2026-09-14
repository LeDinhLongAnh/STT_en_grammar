#!/usr/bin/env python3
"""Visual A/B/C dashboard for Whisper base.en initial-prompt experiments."""

from __future__ import annotations

import json
import sys
import threading
import traceback
from pathlib import Path
from typing import Any

import numpy as np
import datetime
import os
# On Windows, load PyTorch's DLLs before Qt's DLL search path is activated.
# Importing Whisper lazily from a QThread after PyQt5 can fail at c10.dll with
# WinError 1114 even though the same environment works from the CLI.
import whisper
import sounddevice as sd
from PyQt5.QtCore import QThread, QTimer, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QDragEnterEvent, QDropEvent, QFont, QPainter, QPen
from PyQt5.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

import run as experiment

# Add experiments root to import tts_helpers and result_logger
_EXP_ROOT = Path(__file__).resolve().parents[1]
if str(_EXP_ROOT) not in sys.path:
    sys.path.insert(0, str(_EXP_ROOT))
from tts_helpers import KokoroTTSWorker
from result_logger import log_test_result, generate_markdown_report
import logit_bias

# Import ESP32MicRecorder tu thu muc scripts cua sherpa app
_SHERPA_SCRIPTS = Path(__file__).resolve().parents[2] / "test_model_ sherpa" / "scripts"
if str(_SHERPA_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHERPA_SCRIPTS))
try:
    from esp32_mic_recorder import ESP32MicRecorder
    _ESP32_AVAILABLE = True
except ImportError:
    _ESP32_AVAILABLE = False
    print("[CANH BAO] Khong tim thay esp32_mic_recorder.py, chuc nang ESP32 bi tat.")


MODE_TITLES = {
    "none": "1. Không prompt",
    "global": "2. Global prompt",
    "global_bias": "3. Global + Logit Bias",
}


class ModelCache:
    model: Any = None
    model_name: str = ""


class LoadModelWorker(QThread):
    """Load a Whisper model in the background without blocking the GUI."""
    progress = pyqtSignal(str)
    loaded = pyqtSignal(str)   # emits model_name on success
    failed = pyqtSignal(str)

    def __init__(self, cache: ModelCache, model_name: str, parent=None) -> None:
        super().__init__(parent)
        self.cache = cache
        self.model_name = model_name

    def run(self) -> None:
        try:
            self.progress.emit(f"Đang load {self.model_name}...")
            self.cache.model = whisper.load_model(
                self.model_name, device="cpu",
                download_root=str(experiment.ROOT / ".models"))
            self.cache.model_name = self.model_name
            self.loaded.emit(self.model_name)
        except Exception as exc:
            traceback.print_exc()
            self.failed.emit(str(exc))


class DecodeWorker(QThread):
    progress = pyqtSignal(str)
    completed = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, cache: ModelCache, wav_path: Path | None,
                 audio_samples: np.ndarray | None, reference: str,
                 global_prompt: str, prompt_strength: int,
                 model_name: str,
                 config: dict[str, Any],
                 parent=None) -> None:
        super().__init__(parent)
        self.cache = cache
        self.wav_path = wav_path
        self.audio_samples = None if audio_samples is None else audio_samples.copy()
        self.reference = reference
        self.config = config
        self.prompt_strength = prompt_strength
        self.model_name = model_name
        self.prompts = {
            "none": None,
            "global": global_prompt,
        }

    def run(self) -> None:
        try:
            if self.cache.model is None or getattr(self.cache, 'model_name', None) != self.model_name:
                self.progress.emit(f"Đang load Whisper {self.model_name}...")
                self.cache.model = whisper.load_model(
                    self.model_name, device="cpu", download_root=str(experiment.ROOT / ".models"))
                self.cache.model_name = self.model_name

            if self.audio_samples is not None:
                audio = self.audio_samples
                duration = len(audio) / 16000.0
            elif self.wav_path is not None:
                audio, duration = experiment.read_pcm16_mono_16k(self.wav_path)
            else:
                raise RuntimeError("no microphone buffer or WAV selected")
            results: dict[str, Any] = {"duration": duration}
            for mode in ("none", "global"):
                self.progress.emit(f"Đang decode: {MODE_TITLES[mode]}")
                text, elapsed = experiment.transcribe(
                    self.cache.model, audio, self.prompts[mode])
                resolution = experiment.resolve_scenario(text, self.config)
                errors, words = experiment.edit_counts(self.reference, text) \
                    if self.reference.strip() else (0, 0)
                results[mode] = {
                    "text": text,
                    "seconds": elapsed,
                    "rtf": elapsed / duration if duration else 0.0,
                    "errors": errors,
                    "words": words,
                    "wer": errors / words if words else None,
                    "prompt": self.prompts[mode],
                    "resolution": resolution,
                }

            # === MODE 3: Global + Logit Bias (Single-pass) ===
            import logit_bias
            import ctypes
            from ctypes import wintypes
            class PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
                _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD), ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t), ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t), ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t), ("PrivateUsage", ctypes.c_size_t)]
            
            def get_mem_mb() -> float:
                process = ctypes.windll.kernel32.GetCurrentProcess()
                counters = PROCESS_MEMORY_COUNTERS_EX()
                counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS_EX)
                ctypes.windll.psapi.GetProcessMemoryInfo(process, ctypes.byref(counters), counters.cb)
                return counters.PrivateUsage / (1024 * 1024)

            self.progress.emit(f"Đang decode: {MODE_TITLES['global_bias']}...")
            
            # Đo RAM của Global prompt trước để làm mốc cho Bias
            results["global"]["ram_cost_mb"] = 0.0 # Baseline cho global là 0 vì lúc nãy đã chạy
            
            tokenizer = whisper.tokenizer.get_tokenizer(
                multilingual=False, language="en", task="transcribe")
            bias_cfg = logit_bias.load_logit_bias_config()
            bias_filter = logit_bias.build_bias_filter(bias_cfg, tokenizer)
            
            mem_before = get_mem_mb()
            text, elapsed = logit_bias.transcribe_with_bias(
                self.cache.model, audio, self.prompts["global"], bias_filter)
            mem_after = get_mem_mb()
            ram_cost_mb = mem_after - mem_before
            
            resolution = experiment.resolve_scenario(text, self.config)
            errors, words = experiment.edit_counts(self.reference, text) \
                if self.reference.strip() else (0, 0)
            
            results["global_bias"] = {
                "text": text,
                "seconds": elapsed,
                "rtf": elapsed / duration if duration else 0.0,
                "errors": errors,
                "words": words,
                "wer": errors / words if words else None,
                "prompt": self.prompts["global"],
                "resolution": resolution,
                "ram_cost_mb": ram_cost_mb
            }
            results["auto_scenario_id"] = None
            results["routing_source"] = "global_bias"
            results["applied_strength"] = 1
            self.completed.emit(results)
        except Exception as exc:  # GUI boundary: show the complete cause to the user.
            traceback.print_exc()
            self.failed.emit(str(exc))


class BatchBenchmarkWorker(QThread):
    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal(int)
    failed = pyqtSignal(str)

    def __init__(self, cache: ModelCache, items: list[dict], model_name: str, config: dict, parent=None):
        super().__init__(parent)
        self.cache = cache
        self.items = items
        self.model_name = model_name
        self.config = config

    def run(self):
        try:
            if self.cache.model is None or getattr(self.cache, 'model_name', None) != self.model_name:
                self.progress.emit(0, len(self.items), f"Đang nạp Whisper {self.model_name}...")
                self.cache.model = whisper.load_model(
                    self.model_name, device="cpu", download_root=str(experiment.ROOT / ".models"))
                self.cache.model_name = self.model_name

            global_prompt = str(self.config.get("global_prompt", ""))
            tokenizer = whisper.tokenizer.get_tokenizer(multilingual=False, language="en", task="transcribe")
            bias_cfg = logit_bias.load_logit_bias_config()
            bias_filter = logit_bias.build_bias_filter(bias_cfg, tokenizer)

            workspace_root = Path(__file__).resolve().parents[2]
            csv_path = experiment.ROOT / "test_history.csv"

            total = len(self.items)
            for idx, item in enumerate(self.items, 1):
                sample_id = item.get("id", f"sample_{idx:03d}")
                rel_audio = item.get("audio_file", f"audio/{sample_id}.wav")
                audio_path = Path(rel_audio) if Path(rel_audio).is_absolute() else (workspace_root / "datatest" / rel_audio)
                gt = str(item.get("ground_truth", "")).strip()

                if not audio_path.is_file():
                    continue

                self.progress.emit(idx, total, f"[{idx}/{total}] {sample_id} ({gt[:25]}...)")
                audio, duration = experiment.read_pcm16_mono_16k(audio_path)

                # 1. Baseline
                text_none, sec_none = experiment.transcribe(self.cache.model, audio, None)
                err_none, words_none = experiment.edit_counts(gt, text_none) if gt else (0, 0)
                wer_none = err_none / words_none if words_none else 0.0

                # 2. Global Prompt
                text_glob, sec_glob = experiment.transcribe(self.cache.model, audio, global_prompt)
                err_glob, words_glob = experiment.edit_counts(gt, text_glob) if gt else (0, 0)
                wer_glob = err_glob / words_glob if words_glob else 0.0

                # 3. Global Prompt + Logit Bias
                text_bias, sec_bias = logit_bias.transcribe_with_bias(self.cache.model, audio, global_prompt, bias_filter)
                err_bias, words_bias = experiment.edit_counts(gt, text_bias) if gt else (0, 0)
                wer_bias = err_bias / words_bias if words_bias else 0.0

                verdict = "TỐT HƠN" if err_bias < err_none else "XẤU HƠN" if err_bias > err_none else "KHÔNG ĐỔI"

                row = {
                    "Timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "Model": f"whisper-{self.model_name}",
                    "Source_Type": "DATASET_BATCH",
                    "Scenario": item.get("accent", "vietnamese"),
                    "Reference": gt,
                    "Baseline_Text": text_none,
                    "Baseline_WER": f"{wer_none * 100:.1f}%",
                    "Global_Text": text_glob,
                    "Global_WER": f"{wer_glob * 100:.1f}%",
                    "Global_RAM_MB": "0.0",
                    "GlobalBias_Text": text_bias,
                    "GlobalBias_WER": f"{wer_bias * 100:.1f}%",
                    "GlobalBias_RAM_MB": "0.0",
                    "Scenario_Text": text_bias,
                    "Scenario_WER": f"{wer_bias * 100:.1f}%",
                    "Prompt_Verdict": verdict,
                    "Audio_Duration_s": f"{duration:.2f}",
                    "Saved_Audio_Path": str(audio_path),
                }
                log_test_result(csv_path, row)

            self.finished.emit(total)
        except Exception as e:
            traceback.print_exc()
            self.failed.emit(str(e))


class AudioRecorder:
    def __init__(self) -> None:
        self.stream: Any = None
        self.rate = 0.0
        self.chunks: list[np.ndarray] = []
        self.lock = threading.Lock()

    @property
    def active(self) -> bool:
        return self.stream is not None

    @property
    def recorded_seconds(self) -> float:
        with self.lock:
            count = sum(len(chunk) for chunk in self.chunks)
        return count / self.rate if self.rate else 0.0

    def start(self, device: int | None) -> None:
        if self.active:
            return
        info = sd.query_devices(device, "input")
        self.rate = float(info["default_samplerate"])
        self.chunks = []

        def callback(indata, frames, time_info, status) -> None:  # noqa: ANN001
            del frames, time_info
            if status:
                print(f"audio: {status}", file=sys.stderr)
            with self.lock:
                self.chunks.append(indata[:, 0].copy())

        self.stream = sd.InputStream(
            device=device, samplerate=self.rate, channels=1,
            dtype="float32", callback=callback)
        self.stream.start()

    def stop(self) -> tuple[np.ndarray, float]:
        if not self.active:
            raise RuntimeError("microphone is not recording")
        stream = self.stream
        self.stream = None
        stream.stop()
        stream.close()
        with self.lock:
            samples = np.concatenate(self.chunks) if self.chunks else np.zeros(0, np.float32)
            self.chunks = []
        if len(samples) == 0:
            raise RuntimeError("microphone returned no samples")
        audio = experiment.prepare_float32_16k(samples, self.rate)
        return audio, len(audio) / 16000.0

    def snapshot(self, seconds: float = 2.0, max_points: int = 1800) -> np.ndarray:
        """Return a bounded copy for the live waveform; never touches disk."""
        wanted = max(1, int(self.rate * seconds)) if self.rate else max_points
        with self.lock:
            chunks: list[np.ndarray] = []
            count = 0
            for chunk in reversed(self.chunks):
                chunks.append(chunk)
                count += len(chunk)
                if count >= wanted:
                    break
        if not chunks:
            return np.zeros(0, dtype=np.float32)
        samples = np.concatenate(list(reversed(chunks)))[-wanted:]
        if len(samples) > max_points:
            samples = samples[::max(1, len(samples) // max_points)]
        return samples.astype(np.float32, copy=False)

    def cancel(self) -> None:
        if self.active:
            stream = self.stream
            self.stream = None
            stream.stop()
            stream.close()
            self.chunks = []


class ResultCard(QGroupBox):
    def __init__(self, mode: str) -> None:
        super().__init__(MODE_TITLES[mode])
        layout = QVBoxLayout(self)
        self.transcript = QPlainTextEdit()
        self.transcript.setReadOnly(True)
        self.transcript.setPlaceholderText("Chưa decode")
        self.transcript.setMinimumHeight(125)
        font = QFont("Segoe UI", 12)
        self.transcript.setFont(font)
        self.metrics = QLabel("WER —   |   RTF —   |   time —")
        self.metrics.setStyleSheet("color: #64748b;")
        self.route = QLabel("Kịch bản: —")
        self.route.setWordWrap(True)
        self.route.setStyleSheet("color:#334155; font-weight:600;")
        layout.addWidget(self.transcript)
        layout.addWidget(self.route)
        layout.addWidget(self.metrics)

    def set_result(self, result: dict[str, Any]) -> None:
        self.transcript.setPlainText(result["text"])
        wer = "—" if result["wer"] is None else f"{result['wer'] * 100:.1f}%"
        self.metrics.setText(
            f"WER {wer}   |   RTF {result['rtf']:.3f}   |   {result['seconds']:.2f} s")
        resolution = result["resolution"]
        if resolution.status == "matched":
            slots = ", ".join(f"{key}={value}" for key, value in resolution.slots.items())
            suffix = f" | {slots}" if slots else ""
            self.route.setText(
                f"→ {resolution.scenario_name} [{resolution.canonical_action}] "
                f"{resolution.confidence * 100:.0f}%{suffix}")
            self.route.setStyleSheet("color:#15803d; font-weight:700;")
        else:
            candidates = ", ".join(name for name, _score in resolution.alternatives[:2])
            label = "Mơ hồ" if resolution.status == "ambiguous" else "Chưa đủ ý"
            self.route.setText(f"→ {label}; ứng viên: {candidates}")
            self.route.setStyleSheet("color:#b45309; font-weight:700;")


class WaveformWidget(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.samples = np.zeros(0, dtype=np.float32)
        self.setMinimumHeight(92)

    def set_samples(self, samples: np.ndarray) -> None:
        self.samples = np.asarray(samples, dtype=np.float32).copy()
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802,ANN001
        del event
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#0f172a"))
        middle = self.height() / 2.0
        painter.setPen(QPen(QColor("#334155"), 1))
        painter.drawLine(0, int(middle), self.width(), int(middle))
        if len(self.samples) < 2:
            painter.end()
            return
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(QPen(QColor("#38bdf8"), 2))
        amplitude = max(1.0, self.height() * 0.44)
        previous_x = 0
        previous_y = int(middle - float(self.samples[0]) * amplitude)
        denominator = max(1, len(self.samples) - 1)
        for index, sample in enumerate(self.samples[1:], 1):
            x = int(index * (self.width() - 1) / denominator)
            y = int(middle - float(np.clip(sample, -1.0, 1.0)) * amplitude)
            painter.drawLine(previous_x, previous_y, x, y)
            previous_x, previous_y = x, y
        painter.end()


class WhisperPromptDashboard(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.config = experiment.load_config(experiment.DEFAULT_CONFIG)
        self.scenarios = experiment.scenario_map(self.config)
        self.samples = self._load_samples()
        self.cache = ModelCache()
        self.recorder = AudioRecorder()
        self.worker: DecodeWorker | None = None
        self.load_worker: LoadModelWorker | None = None
        self.wav_path: Path | None = None
        self.audio_samples: np.ndarray | None = None
        self.audio_duration: float = 0.0
        self._is_playing: bool = False
        # ESP32 mic
        self._esp32_mic: "ESP32MicRecorder | None" = (
            ESP32MicRecorder(port="COM16", baudrate=2000000) if _ESP32_AVAILABLE else None
        )
        self._esp32_recording: bool = False
        self.dataset_items: list[dict[str, Any]] = []
        self.batch_worker: BatchBenchmarkWorker | None = None
        self._last_dataset_mtime: float = 0.0

        self.setWindowTitle("Whisper — Initial Prompt Lab")
        self.resize(1320, 860)
        self.setAcceptDrops(True)
        self._build_ui()
        self._load_devices()
        self._scenario_changed()
        self._update_model_status()  # reflect any cached model on startup
        self.meter_timer = QTimer(self)
        self.meter_timer.timeout.connect(self._update_meter)
        self.meter_timer.start(50)

        self.ds_watcher_timer = QTimer(self)
        self.ds_watcher_timer.timeout.connect(self._check_dataset_updates)
        self.ds_watcher_timer.start(2000)

    def _load_samples(self) -> dict[str, tuple[Path, str]]:
        rows = experiment.read_manifest(
            experiment.ROOT / "manifest-synthetic.tsv", set(self.scenarios))
        samples: dict[str, tuple[Path, str]] = {}
        for row in rows:
            samples.setdefault(row.scenario_id, (row.wav, row.reference))
        return samples

    def _build_ui(self) -> None:
        central = QWidget()
        outer = QVBoxLayout(central)

        title = QLabel("Whisper + Initial Prompt")
        title.setStyleSheet("font-size: 23px; font-weight: 700; color: #0f172a;")
        note = QLabel(
            "Tự động 2 lượt: Global Prompt → nhận diện intent → nạp đúng Scenario Prompt "
            "→ decode lại. Ô Kịch bản bên dưới chỉ là expected label để test, không lái model.")
        note.setWordWrap(True)
        note.setStyleSheet("color: #475569; margin-bottom: 6px;")
        outer.addWidget(title)
        outer.addWidget(note)

        controls = QGroupBox("Input và kịch bản")
        grid = QGridLayout(controls)

        # --- Model selector row ---
        self.model_combo = QComboBox()
        self.model_combo.addItems(["tiny.en", "base.en", "small.en", "medium.en"])
        self.model_combo.setCurrentText("base.en")
        self.model_combo.currentTextChanged.connect(self._update_model_status)
        self.load_model_button = QPushButton("↧ Load Model")
        self.load_model_button.setFixedWidth(110)
        self.load_model_button.setStyleSheet(
            "QPushButton { background:#0f766e; color:white; font-weight:600; "
            "border-radius:4px; padding:4px 8px; } "
            "QPushButton:disabled { background:#94a3b8; }")
        self.load_model_button.clicked.connect(self._load_model_clicked)
        self.model_status_label = QLabel()
        self.model_status_label.setStyleSheet("font-family:Consolas; font-size:11px;")

        self.scenario_combo = QComboBox()
        for item in sorted(self.config["scenarios"], key=lambda value: value["number"]):
            self.scenario_combo.addItem(
                f"{item['number']}. {item['name']}", item["id"])
        self.scenario_combo.currentIndexChanged.connect(self._scenario_changed)
        self.example_combo = QComboBox()
        self.example_combo.currentTextChanged.connect(self._example_changed)
        self.device_combo = QComboBox()
        self.strength_combo = QComboBox()
        self.strength_combo.addItem("1× — nhẹ, ít nguy cơ hallucination", 1)
        self.strength_combo.addItem("2× — mạnh hơn (khuyên dùng để test)", 2)
        self.strength_combo.addItem("3× — rất mạnh, phải kiểm tra worsened", 3)
        self.strength_combo.setCurrentIndex(1)
        self.reference_edit = QLineEdit()
        self.reference_edit.setPlaceholderText("Reference: câu bạn định nói (để tính WER)")
        self.input_label = QLabel("Chưa có audio — thu mic hoặc chọn WAV")
        self.input_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.waveform = WaveformWidget()
        self.meter_label = QLabel("0.0 s   |   −∞ dBFS   |   mic buffer: RAM only")
        self.meter_label.setStyleSheet("color:#64748b; font-family:Consolas;")
        self.open_button = QPushButton("Chọn WAV…")
        self.tts_button = QPushButton("🔊 Sinh TTS (Kokoro)")
        self.tts_button.setStyleSheet("QPushButton { font-weight:600; color:#0369a1; }")
        self.record_button = QPushButton("● Thu âm")
        self.play_button = QPushButton("▶ Nghe lại")
        self.play_button.setStyleSheet("QPushButton { font-weight:600; color:#0f766e; }")
        self.run_button = QPushButton("Chạy so sánh 3 mode")
        self.run_button.setStyleSheet(
            "QPushButton { background:#2563eb; color:white; padding:9px 16px; "
            "font-weight:600; border-radius:5px; } QPushButton:disabled { background:#94a3b8; }")
        self.export_button = QPushButton("📊 Xuất báo cáo (CSV/MD)")
        self.export_button.setStyleSheet("QPushButton { font-weight:600; color:#7c3aed; }")
        self.open_button.clicked.connect(self._choose_wav)
        self.tts_button.clicked.connect(self._generate_tts_kokoro)
        self.record_button.clicked.connect(self._toggle_record)
        self.play_button.clicked.connect(self._play_audio)
        self.run_button.clicked.connect(self._run_decode)
        self.export_button.clicked.connect(self._export_report)

        # Row 0: model combo + load button + status
        grid.addWidget(QLabel("Whisper Model"), 0, 0)
        model_row = QHBoxLayout()
        model_row.addWidget(self.model_combo)
        model_row.addWidget(self.load_model_button)
        model_row.addWidget(self.model_status_label, 1)
        grid.addLayout(model_row, 0, 1, 1, 3)

        grid.addWidget(QLabel("Kịch bản"), 1, 0)
        grid.addWidget(self.scenario_combo, 1, 1, 1, 3)
        grid.addWidget(QLabel("Câu mẫu"), 2, 0)
        grid.addWidget(self.example_combo, 2, 1, 1, 3)
        grid.addWidget(QLabel("Prompt strength"), 3, 0)
        grid.addWidget(self.strength_combo, 3, 1, 1, 3)
        grid.addWidget(QLabel("Microphone"), 4, 0)
        grid.addWidget(self.device_combo, 4, 1, 1, 3)

        # --- ESP32 INMP441 row ---
        esp32_row = QHBoxLayout()
        self.esp32_port_edit = QLineEdit("COM16")
        self.esp32_port_edit.setFixedWidth(80)
        self.esp32_port_edit.setPlaceholderText("COM16")
        esp32_row.addWidget(QLabel("Port:"))
        esp32_row.addWidget(self.esp32_port_edit)
        self.esp32_baud_edit = QLineEdit("2000000")
        self.esp32_baud_edit.setFixedWidth(90)
        esp32_row.addWidget(QLabel("Baud:"))
        esp32_row.addWidget(self.esp32_baud_edit)
        self.esp32_connect_btn = QPushButton("🔌 Ket noi ESP32")
        self.esp32_connect_btn.setStyleSheet(
            "QPushButton { background:#0f766e; color:white; font-weight:600; "
            "border-radius:4px; padding:4px 10px; } "
            "QPushButton:hover { background:#0d5c55; }")
        self.esp32_connect_btn.setEnabled(_ESP32_AVAILABLE)
        self.esp32_connect_btn.clicked.connect(self._toggle_esp32_connect)
        esp32_row.addWidget(self.esp32_connect_btn)
        self.esp32_status_label = QLabel(
            "Chua ket noi" if _ESP32_AVAILABLE else "Khong kha dung (thieu esp32_mic_recorder.py)")
        self.esp32_status_label.setStyleSheet("color:#b45309; font-weight:600; font-family:Consolas;")
        esp32_row.addWidget(self.esp32_status_label, 1)
        grid.addLayout(esp32_row, 5, 0, 1, 4)

        # --- Dataset quick selector row ---
        grid.addWidget(QLabel("Dataset"), 6, 0)
        ds_row = QHBoxLayout()
        self.prev_ds_btn = QPushButton("◀ Trước")
        self.prev_ds_btn.setFixedWidth(75)
        self.prev_ds_btn.setStyleSheet("font-weight:600;")
        self.prev_ds_btn.clicked.connect(self._prev_dataset_sample)
        ds_row.addWidget(self.prev_ds_btn)

        self.dataset_combo = QComboBox()
        self.dataset_combo.currentIndexChanged.connect(self._dataset_sample_selected)
        ds_row.addWidget(self.dataset_combo, 1)

        self.next_ds_btn = QPushButton("Tiếp ▶")
        self.next_ds_btn.setFixedWidth(75)
        self.next_ds_btn.setStyleSheet("font-weight:600;")
        self.next_ds_btn.clicked.connect(self._next_dataset_sample)
        ds_row.addWidget(self.next_ds_btn)

        self.refresh_ds_btn = QPushButton("🔄")
        self.refresh_ds_btn.setFixedWidth(36)
        self.refresh_ds_btn.setToolTip("Làm mới danh sách Dataset (nếu vừa ghi âm thêm câu mới)")
        self.refresh_ds_btn.clicked.connect(lambda: self._load_dataset_catalog(preserve_selection=False))
        ds_row.addWidget(self.refresh_ds_btn)

        self.batch_ds_btn = QPushButton("⚡ Chạy toàn bộ Dataset")
        self.batch_ds_btn.setStyleSheet(
            "QPushButton { background:#7c3aed; color:white; font-weight:700; "
            "border-radius:4px; padding:4px 10px; } "
            "QPushButton:hover { background:#6d28d9; } "
            "QPushButton:disabled { background:#94a3b8; }")
        self.batch_ds_btn.clicked.connect(self._run_batch_benchmark)
        ds_row.addWidget(self.batch_ds_btn)
        grid.addLayout(ds_row, 6, 1, 1, 3)

        grid.addWidget(QLabel("Reference"), 7, 0)
        grid.addWidget(self.reference_edit, 7, 1, 1, 3)
        grid.addWidget(QLabel("Audio"), 8, 0)
        grid.addWidget(self.input_label, 8, 1, 1, 3)
        meter = QVBoxLayout()
        meter.addWidget(self.waveform)
        meter.addWidget(self.meter_label)
        grid.addLayout(meter, 9, 0, 1, 4)

        # Them nut Thu ESP32 vao hang button
        self.esp32_record_btn = QPushButton("🎙 Thu ESP32")
        self.esp32_record_btn.setEnabled(False)
        self.esp32_record_btn.setStyleSheet(
            "QPushButton { font-weight:600; color:#0369a1; } "
            "QPushButton:disabled { color:#94a3b8; }")
        self.esp32_record_btn.clicked.connect(self._toggle_esp32_record)

        buttons = QHBoxLayout()
        for button in (self.open_button, self.tts_button, self.record_button,
                       self.esp32_record_btn,
                       self.play_button, self.run_button, self.export_button):
            buttons.addWidget(button)
        grid.addLayout(buttons, 10, 0, 1, 4)
        outer.addWidget(controls)

        splitter = QSplitter(Qt.Vertical)
        results_widget = QWidget()
        results_layout = QHBoxLayout(results_widget)
        self.cards = {mode: ResultCard(mode) for mode in ("none", "global", "global_bias")}
        for card in self.cards.values():
            results_layout.addWidget(card)
        splitter.addWidget(results_widget)

        prompts = QWidget()
        prompt_grid = QGridLayout(prompts)
        self.global_prompt = QPlainTextEdit(str(self.config["global_prompt"]))
        self.scenario_prompt = QPlainTextEdit()
        self.global_prompt_label = QLabel("Global prompt")

        self.save_prompt_button = QPushButton("💾 Lưu Global Prompt")
        self.save_prompt_button.setStyleSheet(
            "QPushButton { background:#7c3aed; color:white; font-weight:600; "
            "border-radius:4px; padding:4px 10px; } "
            "QPushButton:hover { background:#6d28d9; } "
            "QPushButton:disabled { background:#94a3b8; }")
        self.save_prompt_button.clicked.connect(self._save_global_prompt)

        label_row = QHBoxLayout()
        label_row.addWidget(self.global_prompt_label, 1)
        label_row.addWidget(self.save_prompt_button)

        prompt_grid.addLayout(label_row, 0, 0)
        prompt_grid.addWidget(QLabel("Scenario prompt của expected label (auto-router tự chọn khi chạy)"), 0, 1)
        prompt_grid.addWidget(self.global_prompt, 1, 0)
        prompt_grid.addWidget(self.scenario_prompt, 1, 1)
        self.global_prompt.textChanged.connect(self._update_global_prompt_budget)
        self._update_global_prompt_budget()
        splitter.addWidget(prompts)
        splitter.setSizes([360, 250])
        outer.addWidget(splitter, 1)

        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Chọn kịch bản và dùng TTS mẫu hoặc thu WAV mới")
        self._load_dataset_catalog()

    def _load_dataset_catalog(self, preserve_selection: bool = True) -> None:
        """Load danh sach cac mau tu datatest/dataset.json vao combobox."""
        workspace_root = Path(__file__).resolve().parents[2]
        ds_path = workspace_root / "datatest" / "dataset.json"
        if not ds_path.is_file():
            return

        try:
            self._last_dataset_mtime = ds_path.stat().st_mtime
        except Exception:
            pass

        current_idx = self.dataset_combo.currentIndex() if preserve_selection else -1

        self.dataset_items = []
        try:
            with open(ds_path, "r", encoding="utf-8") as f:
                self.dataset_items = json.load(f)
        except Exception:
            return

        self.dataset_combo.blockSignals(True)
        self.dataset_combo.clear()
        for idx, item in enumerate(self.dataset_items):
            sid = item.get("id", f"sample_{idx+1:03d}")
            gt = item.get("ground_truth", "")
            gt_display = (gt[:38] + "..") if len(gt) > 40 else gt
            dur = item.get("duration_s", 0)
            self.dataset_combo.addItem(f"[{idx+1:02d}/{len(self.dataset_items)}] {sid} ({dur}s): {gt_display}", idx)

        if preserve_selection and 0 <= current_idx < self.dataset_combo.count():
            self.dataset_combo.setCurrentIndex(current_idx)
        elif self.dataset_combo.count() > 0:
            self.dataset_combo.setCurrentIndex(0)
        self.dataset_combo.blockSignals(False)

    def _check_dataset_updates(self) -> None:
        """Tu dong kiem tra va nap them mau moi neu vua thu am xong o recording_studio.py."""
        workspace_root = Path(__file__).resolve().parents[2]
        ds_path = workspace_root / "datatest" / "dataset.json"
        if ds_path.is_file():
            try:
                mtime = ds_path.stat().st_mtime
                if mtime != getattr(self, "_last_dataset_mtime", 0.0):
                    old_count = len(self.dataset_items)
                    self._load_dataset_catalog(preserve_selection=True)
                    new_count = len(self.dataset_items)
                    if new_count > old_count:
                        self.statusBar().showMessage(
                            f"🔄 Đã phát hiện {new_count - old_count} file ghi âm mới! Tổng cộng: {new_count} câu trong Dataset.", 6000)
            except Exception:
                pass

    def _dataset_sample_selected(self, index: int) -> None:
        if index < 0 or index >= len(self.dataset_items):
            return
        item = self.dataset_items[index]
        rel_audio = item.get("audio_file", f"audio/{item.get('id', '')}.wav")
        workspace_root = Path(__file__).resolve().parents[2]
        wav_path = Path(rel_audio) if Path(rel_audio).is_absolute() else (workspace_root / "datatest" / rel_audio)
        if wav_path.is_file():
            self._set_wav(wav_path)
            gt = item.get("ground_truth", "")
            if gt:
                self.reference_edit.setText(gt)

    def _prev_dataset_sample(self) -> None:
        idx = self.dataset_combo.currentIndex()
        if idx > 0:
            self.dataset_combo.setCurrentIndex(idx - 1)

    def _next_dataset_sample(self) -> None:
        idx = self.dataset_combo.currentIndex()
        if idx < self.dataset_combo.count() - 1:
            self.dataset_combo.setCurrentIndex(idx + 1)

    def _run_batch_benchmark(self) -> None:
        if not self.dataset_items:
            QMessageBox.warning(self, "Không có dataset", "Không tìm thấy mẫu nào trong datatest/dataset.json")
            return
        
        reply = QMessageBox.question(
            self, "Chạy Batch Benchmark",
            f"Bạn có muốn tự động chạy benchmark tất cả {len(self.dataset_items)} câu trong dataset qua 3 chế độ không?\n\n"
            "Quá trình chạy sẽ tự động cập nhật kết quả và xuất báo cáo sau khi xong.",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        self._set_busy(True)
        self.batch_ds_btn.setEnabled(False)
        self.batch_ds_btn.setText("⏳ Đang chạy...")

        self.batch_worker = BatchBenchmarkWorker(
            self.cache, self.dataset_items, self.model_combo.currentText(), self.config, self)
        self.batch_worker.progress.connect(self._on_batch_progress)
        self.batch_worker.finished.connect(self._on_batch_finished)
        self.batch_worker.failed.connect(self._on_batch_failed)
        self.batch_worker.start()

    def _on_batch_progress(self, current: int, total: int, msg: str) -> None:
        self.statusBar().showMessage(f"⚡ Batch Benchmark: {msg}")

    def _on_batch_finished(self, total: int) -> None:
        self._set_busy(False)
        self.batch_ds_btn.setEnabled(True)
        self.batch_ds_btn.setText("⚡ Chạy toàn bộ Dataset")
        self.statusBar().showMessage(f"✅ Đã hoàn thành benchmark {total} câu!", 8000)
        self.batch_worker = None
        self._export_report()

    def _on_batch_failed(self, err: str) -> None:
        self._set_busy(False)
        self.batch_ds_btn.setEnabled(True)
        self.batch_ds_btn.setText("⚡ Chạy toàn bộ Dataset")
        QMessageBox.critical(self, "Lỗi Batch Benchmark", err)
        self.statusBar().showMessage(f"Lỗi: {err}")
        self.batch_worker = None

    def _update_global_prompt_budget(self) -> None:
        tokenizer = whisper.tokenizer.get_tokenizer(
            multilingual=False, language="en", task="transcribe")
        prompt = self.global_prompt.toPlainText().strip()
        count = len(tokenizer.encode(" " + prompt)) if prompt else 0
        version = str(self.config.get("global_prompt_version", "custom")).upper()
        self.global_prompt_label.setText(
            f"Global prompt {version} — {count}/223 Whisper tokens")
        color = "#dc2626" if count > 223 else "#15803d" if count >= 180 else "#475569"
        self.global_prompt_label.setStyleSheet(f"color:{color}; font-weight:700;")

    def _save_global_prompt(self) -> None:
        """Ghi global_prompt hiện tại trên UI xuống scenarios.json."""
        new_prompt = self.global_prompt.toPlainText().strip()
        if not new_prompt:
            QMessageBox.warning(self, "Không lưu", "Prompt đang trống, không lưu.")
            return

        config_path = experiment.DEFAULT_CONFIG
        try:
            raw = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception as exc:
            QMessageBox.critical(self, "Lỗi đọc file", str(exc))
            return

        raw["global_prompt"] = new_prompt
        # Đánh dấu là đã chỉnh sửa thủ công
        raw["global_prompt_version"] = raw.get("global_prompt_version", "V3-LEAN") + "-EDITED"
        # Chỉ giữ tag gốc, không để "-EDITED-EDITED"
        raw["global_prompt_version"] = raw["global_prompt_version"].replace("-EDITED-EDITED", "-EDITED")

        try:
            config_path.write_text(
                json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            QMessageBox.critical(self, "Lỗi ghi file", str(exc))
            return

        # Cập nhật config trong RAM luôn để kết quả được nhất quán
        self.config["global_prompt"] = new_prompt
        self.config["global_prompt_version"] = raw["global_prompt_version"]
        self._update_global_prompt_budget()
        self.statusBar().showMessage(
            f"💾 Đã lưu Global Prompt vào {config_path.name} — sẽ dùng ngay và giữ sau khi khởi động lại", 7000)

    def _load_devices(self) -> None:
        self.device_combo.clear()
        try:
            default_input = sd.default.device[0]
            for index, info in enumerate(sd.query_devices()):
                if int(info.get("max_input_channels", 0)) > 0:
                    self.device_combo.addItem(str(info["name"]), index)
                    if index == default_input:
                        self.device_combo.setCurrentIndex(self.device_combo.count() - 1)
        except Exception as exc:
            self.device_combo.addItem(f"Không đọc được microphone: {exc}", None)

    def _scenario_changed(self) -> None:
        scenario_id = self.scenario_combo.currentData()
        if not scenario_id:
            return
        scenario = self.scenarios[scenario_id]
        self.scenario_prompt.setPlainText(str(scenario["prompt"]))
        examples = [str(value) for value in scenario.get("examples", [])]
        self.example_combo.blockSignals(True)
        self.example_combo.clear()
        self.example_combo.addItems(examples)
        self.example_combo.blockSignals(False)
        if examples:
            self.reference_edit.setText(examples[0])
        else:
            sample = self.samples.get(scenario_id)
            if sample:
                self.reference_edit.setText(sample[1])

    def _example_changed(self, text: str) -> None:
        if text.strip():
            self.reference_edit.setText(text.strip())

    def _lookup_ground_truth(self, path: Path) -> str | None:
        """Lookup ground truth / reference text for a given WAV file from datatest/dataset.json or sidecars."""
        try:
            workspace_root = Path(__file__).resolve().parents[2]
            dataset_path = workspace_root / "datatest" / "dataset.json"
            if dataset_path.is_file():
                with open(dataset_path, "r", encoding="utf-8") as f:
                    items = json.load(f)
                stem = path.stem.lower()
                fname = path.name.lower()
                for item in items:
                    item_id = str(item.get("id", "")).lower()
                    item_audio = Path(str(item.get("audio_file", ""))).name.lower()
                    if item_id == stem or item_audio == fname:
                        gt = item.get("ground_truth") or item.get("reference") or item.get("text")
                        if gt and str(gt).strip():
                            return str(gt).strip()
        except Exception:
            pass

        # Check sidecar .json
        try:
            sidecar_json = path.with_suffix(".json")
            if sidecar_json.is_file():
                with open(sidecar_json, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                gt = meta.get("ground_truth") or meta.get("reference") or meta.get("text")
                if gt and str(gt).strip():
                    return str(gt).strip()
        except Exception:
            pass

        # Check sidecar .txt
        try:
            sidecar_txt = path.with_suffix(".txt")
            if sidecar_txt.is_file():
                txt = sidecar_txt.read_text(encoding="utf-8").strip()
                if txt:
                    return txt
        except Exception:
            pass

        # Check manifest files in experiments/whisper_initial_prompt
        for manifest_name in ("manifest.tsv", "manifest-synthetic.tsv"):
            manifest_path = Path(__file__).resolve().parent / manifest_name
            if manifest_path.is_file():
                try:
                    with open(manifest_path, "r", encoding="utf-8") as f:
                        for line in f:
                            parts = line.strip().split("\t")
                            if len(parts) >= 2:
                                wav_str = parts[1] if len(parts) > 2 else parts[0]
                                ref_str = parts[2] if len(parts) > 2 else parts[1]
                                if Path(wav_str).name.lower() == path.name.lower():
                                    return ref_str.strip()
                except Exception:
                    pass
        return None

    def _set_wav(self, path: Path) -> None:
        self._stop_audio()
        self.audio_samples = None
        self.audio_duration = 0.0
        self.wav_path = path.resolve()
        self.source_type = "FILE_WAV"
        self.saved_audio_path = str(self.wav_path)
        
        # Tu dong dien Ground Truth tu dataset.json hoac metadata neu tim thay
        ref_text = self._lookup_ground_truth(self.wav_path)
        if ref_text:
            self.reference_edit.setText(ref_text)

        try:
            samples, duration = experiment.read_pcm16_mono_16k(self.wav_path)
            self.audio_samples = samples
            self.audio_duration = duration
            self.waveform.set_samples(samples[-32000:] if len(samples) > 32000 else samples)
            self.input_label.setText(f"{self.wav_path.name} ({duration:.2f} s)")
            if ref_text:
                self.statusBar().showMessage(
                    f"Đã chọn {self.wav_path.name} ({duration:.2f} s) | Reference: \"{ref_text}\"", 6000)
            else:
                self.statusBar().showMessage(
                    f"Đã chọn {self.wav_path.name} ({duration:.2f} s) — bấm '▶ Nghe lại' để nghe", 6000)
        except Exception:
            self.input_label.setText(str(self.wav_path))
            if ref_text:
                self.statusBar().showMessage(
                    f"Đã chọn {self.wav_path.name} | Reference: \"{ref_text}\"", 6000)
            else:
                self.statusBar().showMessage(f"Đã chọn {self.wav_path.name}")

    def _handle_multiple_wavs(self, paths: list[Path]) -> None:
        """Xu ly khi nguoi dung chon hoac keo tha mot hoac nhieu file WAV."""
        if not paths:
            return

        # Sap xep theo ten file tu nhien (sample_001, sample_002...)
        try:
            import re
            def natural_key(p: Path):
                return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', p.name)]
            paths = sorted(paths, key=natural_key)
        except Exception:
            paths = sorted(paths)

        self._last_wav_dir = paths[0].parent

        if len(paths) == 1:
            self._set_wav(paths[0])
            return

        # Neu chon nhieu file: nap vao dataset_items va combo
        selected_items = []
        for p in paths:
            gt = self._lookup_ground_truth(p) or ""
            selected_items.append({
                "id": p.stem,
                "audio_file": str(p),
                "ground_truth": gt,
                "duration_s": 0.0,
                "accent": "vietnamese",
            })

        self.dataset_items = selected_items
        self.dataset_combo.blockSignals(True)
        self.dataset_combo.clear()
        for idx, item in enumerate(self.dataset_items):
            sid = item["id"]
            gt = item["ground_truth"]
            gt_disp = (gt[:35] + "..") if len(gt) > 37 else gt
            label = f"[{idx+1:02d}/{len(paths)}] {sid}: {gt_disp}" if gt_disp else f"[{idx+1:02d}/{len(paths)}] {sid}"
            self.dataset_combo.addItem(label, idx)
        self.dataset_combo.blockSignals(False)

        # Chon ngay file dau tien
        self._set_wav(paths[0])
        if selected_items[0]["ground_truth"]:
            self.reference_edit.setText(selected_items[0]["ground_truth"])

        self.statusBar().showMessage(
            f"✅ Đã nạp {len(paths)} file WAV vào danh sách. Bấm 'Tiếp ▶' để duyệt hoặc '⚡ Chạy toàn bộ Dataset' để benchmark.", 8000)

        # Hoi nguoi dung co muon chay tu dong luon khong
        reply = QMessageBox.question(
            self, "Đã chọn nhiều file WAV",
            f"Bạn đã chọn {len(paths)} file WAV.\n\n"
            f"Bạn có muốn TỰ ĐỘNG CHẠY SO SÁNH 3 MODE cho toàn bộ {len(paths)} file này ngay bây giờ không?\n\n"
            "• Chọn YES: Hệ thống tự động chạy hết từ đầu đến cuối và xuất báo cáo.\n"
            "• Chọn NO: Giữ danh sách, dùng nút '◀ Trước' / 'Tiếp ▶' để duyệt và test từng file.",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self._run_batch_benchmark()

    def _choose_wav(self) -> None:
        workspace_root = Path(__file__).resolve().parents[2]
        default_dir = workspace_root / "datatest" / "audio"
        if not default_dir.exists():
            default_dir = experiment.ROOT
        init_dir = str(getattr(self, "_last_wav_dir", default_dir))
        names, _ = QFileDialog.getOpenFileNames(
            self, "Chọn một hoặc nhiều file WAV (Ctrl+A để chọn tất cả)", 
            init_dir, "WAV audio (*.wav)")
        if names:
            self._handle_multiple_wavs([Path(n) for n in names])

    def _generate_tts_kokoro(self) -> None:
        text = self.reference_edit.text().strip()
        if not text:
            text = self.example_combo.currentText().strip()
            if text:
                self.reference_edit.setText(text)
        if not text:
            QMessageBox.warning(self, "Thiếu văn bản", "Nhập câu cần đọc vào Reference hoặc chọn câu mẫu.")
            return

        self.tts_button.setDisabled(True)
        self.tts_button.setText("⏳ Đang sinh...")
        self.statusBar().showMessage(f"Đang sinh âm thanh Kokoro TTS cho: '{text}'...")

        self.tts_worker = KokoroTTSWorker(text, voice="af_heart", parent=self)
        self.tts_worker.progress.connect(self.statusBar().showMessage)
        self.tts_worker.completed.connect(self._on_tts_completed)
        self.tts_worker.failed.connect(self._on_tts_failed)
        self.tts_worker.start()

    def _on_tts_completed(self, samples: np.ndarray, duration: float) -> None:
        self._stop_audio()
        self.tts_button.setEnabled(True)
        self.tts_button.setText("🔊 Sinh TTS (Kokoro)")
        self.audio_samples = samples
        self.audio_duration = duration
        self.wav_path = None
        self.source_type = "TTS_KOKORO"

        import soundfile as sf
        rec_dir = experiment.ROOT.parents[1] / "recordings"
        rec_dir.mkdir(parents=True, exist_ok=True)
        t_stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        out_wav = rec_dir / f"kokoro_{t_stamp}.wav"
        try:
            sf.write(str(out_wav), samples, 16000, subtype="PCM_16")
            self.saved_audio_path = str(out_wav)
            save_name = out_wav.name
        except Exception:
            self.saved_audio_path = ""
            save_name = "RAM"

        self.waveform.set_samples(samples[-32000:])
        self.input_label.setText(f"TTS Kokoro: {duration:.2f} s (Đã lưu: {save_name})")
        self.statusBar().showMessage(f"✅ Đã sinh âm Kokoro ({duration:.2f} s) — bấm '▶ Nghe lại' để nghe", 6000)

    def _on_tts_failed(self, err: str) -> None:
        self.tts_button.setEnabled(True)
        self.tts_button.setText("🔊 Sinh TTS (Kokoro)")
        QMessageBox.critical(self, "Lỗi Kokoro TTS", err)
        self.statusBar().showMessage(f"Lỗi Kokoro: {err}")

    def _export_report(self) -> None:
        csv_path = experiment.ROOT / "test_history.csv"
        md_text = generate_markdown_report(csv_path, "Báo cáo thử nghiệm: Whisper Prompt vs Không Prompt")
        md_file = experiment.ROOT / "TEST_REPORT.md"
        try:
            md_file.write_text(md_text, encoding="utf-8")
        except Exception:
            pass

        dlg = QDialog(self)
        dlg.setWindowTitle("Báo cáo kết quả thử nghiệm: Prompt vs Không Prompt")
        dlg.resize(850, 600)
        ly = QVBoxLayout(dlg)
        tb = QPlainTextEdit()
        tb.setPlainText(md_text)
        tb.setReadOnly(True)
        tb.setFont(QFont("Consolas", 10))
        ly.addWidget(tb)
        btn_box = QHBoxLayout()
        open_folder_btn = QPushButton("📁 Mở thư mục chứa file CSV / MD")
        open_folder_btn.setStyleSheet("font-weight:600; padding:6px 12px;")
        open_folder_btn.clicked.connect(lambda: os.startfile(str(experiment.ROOT)))
        btn_box.addWidget(open_folder_btn)
        
        clear_btn = QPushButton("🗑 Xóa lịch sử")
        clear_btn.setStyleSheet("font-weight:600; padding:6px 12px; color:#dc2626;")
        def _clear_history() -> None:
            ans = QMessageBox.question(dlg, "Xác nhận", "Xóa toàn bộ file test_history.csv và báo cáo MD?", QMessageBox.Yes | QMessageBox.No)
            if ans == QMessageBox.Yes:
                try:
                    if csv_path.exists():
                        csv_path.unlink()
                    if md_file.exists():
                        md_file.unlink()
                    tb.setPlainText("Lịch sử đã trống.")
                    QMessageBox.information(dlg, "Đã xóa", "Đã xóa lịch sử thành công.")
                except Exception as exc:
                    QMessageBox.critical(dlg, "Lỗi xóa file", str(exc))
        clear_btn.clicked.connect(_clear_history)
        btn_box.addWidget(clear_btn)

        btn_box.addStretch(1)
        close_btn = QPushButton("Đóng")
        close_btn.clicked.connect(dlg.accept)
        btn_box.addWidget(close_btn)
        ly.addLayout(btn_box)
        dlg.exec_()

    def _toggle_record(self) -> None:
        if not self.recorder.active:
            try:
                self._stop_audio()
                device = self.device_combo.currentData()
                self.wav_path = None
                self.audio_samples = None
                self.audio_duration = 0.0
                self.waveform.set_samples(np.zeros(0, dtype=np.float32))
                self.recorder.start(device)
                self.record_button.setText("■ Dừng thu")
                self.record_button.setStyleSheet("background:#dc2626; color:white; padding:7px;")
                self.statusBar().showMessage("Đang thu... hãy nói một câu rồi bấm Dừng thu")
            except Exception as exc:
                QMessageBox.critical(self, "Không mở được microphone", str(exc))
        else:
            try:
                audio, duration = self.recorder.stop()
                self.audio_samples = audio
                self.audio_duration = duration
                self.wav_path = None
                self.source_type = "MIC"

                # Auto save mic take to recordings
                import soundfile as sf
                rec_dir = experiment.ROOT.parents[1] / "recordings"
                rec_dir.mkdir(parents=True, exist_ok=True)
                t_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                saved_wav = rec_dir / f"mic_whisper_{t_str}.wav"
                try:
                    sf.write(str(saved_wav), audio, 16000, subtype="PCM_16")
                    self.saved_audio_path = str(saved_wav)
                    saved_name = saved_wav.name
                except Exception:
                    self.saved_audio_path = ""
                    saved_name = "RAM"

                self.waveform.set_samples(audio[-32000:])
                self.input_label.setText(
                    f"Microphone buffer: {duration:.2f} s, mono 16 kHz (Đã lưu: {saved_name})")
                self.statusBar().showMessage(
                    f"Đã thu {duration:.1f} giây và lưu {saved_name} — bấm '▶ Nghe lại' để nghe", 6000)
            except Exception as exc:
                QMessageBox.critical(self, "Thu âm thất bại", str(exc))
            finally:
                self.record_button.setText("● Thu âm")
                self.record_button.setStyleSheet("")

    # -----------------------------------------------------------------------
    # Handler: ESP32 INMP441
    # -----------------------------------------------------------------------
    def _toggle_esp32_connect(self) -> None:
        if self._esp32_mic is None:
            return
        if self._esp32_mic.is_connected():
            if self._esp32_recording:
                self._force_stop_esp32()
            self._esp32_mic.disconnect()
            self.esp32_connect_btn.setText("🔌 Ket noi ESP32")
            self.esp32_connect_btn.setStyleSheet(
                "QPushButton { background:#0f766e; color:white; font-weight:600; "
                "border-radius:4px; padding:4px 10px; } "
                "QPushButton:hover { background:#0d5c55; }")
            self.esp32_status_label.setText("Chua ket noi")
            self.esp32_status_label.setStyleSheet("color:#b45309; font-weight:600; font-family:Consolas;")
            self.esp32_record_btn.setEnabled(False)
        else:
            port = self.esp32_port_edit.text().strip() or "COM16"
            baud_str = self.esp32_baud_edit.text().strip()
            baud = int(baud_str) if baud_str.isdigit() else 2000000
            try:
                self._esp32_mic.connect(port=port, baudrate=baud)
                self.esp32_connect_btn.setText("🔌 Ngat ESP32")
                self.esp32_connect_btn.setStyleSheet(
                    "QPushButton { background:#dc2626; color:white; font-weight:600; "
                    "border-radius:4px; padding:4px 10px; } "
                    "QPushButton:hover { background:#b91c1c; }")
                self.esp32_status_label.setText(f"Da ket noi ({port})")
                self.esp32_status_label.setStyleSheet("color:#15803d; font-weight:600; font-family:Consolas;")
                self.esp32_record_btn.setEnabled(True)
            except Exception as exc:
                self.esp32_status_label.setText(f"Loi: {exc}")
                self.esp32_status_label.setStyleSheet("color:#dc2626; font-weight:600; font-family:Consolas;")

    def _toggle_esp32_record(self) -> None:
        if self._esp32_mic is None or not self._esp32_mic.is_connected():
            QMessageBox.warning(self, "Chua ket noi", "Ket noi ESP32 truoc khi ghi am.")
            return
        if not self._esp32_recording:
            # Dung mic laptop neu dang chay
            if self.recorder.active:
                self.recorder.cancel()
                self.record_button.setText("● Thu âm")
                self.record_button.setStyleSheet("")
            self._stop_audio()
            self.wav_path = None
            self.audio_samples = None
            self.audio_duration = 0.0
            self.waveform.set_samples(np.zeros(0, dtype=np.float32))
            try:
                self._esp32_mic.start()
                self._esp32_recording = True
                self.esp32_record_btn.setText("■ Dung ESP32")
                self.esp32_record_btn.setStyleSheet(
                    "QPushButton { background:#dc2626; color:white; font-weight:600; "
                    "border-radius:4px; padding:4px 8px; }")
                self.statusBar().showMessage("Dang ghi am tu ESP32 INMP441... noi vao mic roi bam Dung ESP32")
            except Exception as exc:
                QMessageBox.critical(self, "Loi ghi am ESP32", str(exc))
        else:
            self._force_stop_esp32()

    def _force_stop_esp32(self) -> None:
        """Dung ghi am ESP32 va luu audio vao self.audio_samples."""
        if self._esp32_mic is None:
            return
        try:
            samples = self._esp32_mic.stop()
        except Exception:
            samples = np.array([], dtype=np.float32)
        self._esp32_recording = False
        self.esp32_record_btn.setText("🎙 Thu ESP32")
        self.esp32_record_btn.setStyleSheet("QPushButton { font-weight:600; color:#0369a1; }")
        if samples is None or len(samples) == 0:
            self.statusBar().showMessage("ESP32: Khong nhan duoc du lieu. Kiem tra ket noi.")
            return
        duration = len(samples) / 16000.0
        self.audio_samples = samples
        self.audio_duration = duration
        self.wav_path = None
        self.source_type = "ESP32_INMP441"
        # Luu file wav
        import soundfile as sf
        rec_dir = experiment.ROOT.parents[1] / "recordings"
        rec_dir.mkdir(parents=True, exist_ok=True)
        t_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        saved_wav = rec_dir / f"esp32_whisper_{t_str}.wav"
        try:
            sf.write(str(saved_wav), samples, 16000, subtype="PCM_16")
            self.saved_audio_path = str(saved_wav)
            saved_name = saved_wav.name
        except Exception:
            self.saved_audio_path = ""
            saved_name = "RAM"
        self.waveform.set_samples(samples[-32000:])
        self.input_label.setText(
            f"ESP32 INMP441: {duration:.2f} s, mono 16 kHz (Da luu: {saved_name})")
        self.statusBar().showMessage(
            f"Da ghi am ESP32 {duration:.1f}s, luu {saved_name} — bam Nghe lai hoac Chay so sanh", 6000)

    def _update_meter(self) -> None:
        if not self.recorder.active:
            return
        samples = self.recorder.snapshot()
        self.waveform.set_samples(samples)
        rms = float(np.sqrt(np.mean(np.square(samples)))) if len(samples) else 0.0
        dbfs = 20.0 * np.log10(max(rms, 1e-8))
        duration = self.recorder.recorded_seconds
        self.meter_label.setText(
            f"{duration:5.1f} s   |   {dbfs:6.1f} dBFS   |   mic buffer: RAM only")

    def _run_decode(self) -> None:
        self._stop_audio()
        has_wav = self.wav_path is not None and self.wav_path.is_file()
        if self.audio_samples is None and not has_wav:
            QMessageBox.warning(self, "Thiếu audio", "Chọn WAV, dùng TTS mẫu hoặc thu âm trước.")
            return
        self._set_busy(True)
        strength = int(self.strength_combo.currentData())
        self.cards["global_bias"].setTitle(
            f"3. Global + Logit Bias")
        selected_id = self.scenario_combo.currentData()
        if selected_id:
            self.scenarios[selected_id]["prompt"] = self.scenario_prompt.toPlainText().strip()
        self.worker = DecodeWorker(
            self.cache, self.wav_path, self.audio_samples, self.reference_edit.text(),
            self.global_prompt.toPlainText().strip(), strength,
            self.model_combo.currentText(),
            self.config, self)
        self.worker.progress.connect(self.statusBar().showMessage)
        self.worker.completed.connect(self._decode_done)
        self.worker.failed.connect(self._decode_failed)
        self.worker.start()

    def _update_model_status(self) -> None:
        """Refresh the status label to show whether the selected model is loaded."""
        selected = self.model_combo.currentText()
        if self.cache.model_name == selected and self.cache.model is not None:
            self.model_status_label.setText(
                f"✅ Đã load — đang dùng: {selected}")
            self.model_status_label.setStyleSheet(
                "color:#15803d; font-family:Consolas; font-size:11px; font-weight:700;")
        else:
            cached = self.cache.model_name if self.cache.model else ""
            note = f" (RAM: {cached})" if cached and cached != selected else ""
            self.model_status_label.setText(
                f"⚠ Chưa load{note} — bấm '↧ Load Model' trước khi chạy")
            self.model_status_label.setStyleSheet(
                "color:#b45309; font-family:Consolas; font-size:11px; font-weight:700;")

    def _load_model_clicked(self) -> None:
        model_name = self.model_combo.currentText()
        if self.cache.model_name == model_name and self.cache.model is not None:
            QMessageBox.information(self, "Model sẵn sàng",
                                    f"{model_name} đã được load trong RAM rồi, không cần load lại.")
            return
        self.load_model_button.setDisabled(True)
        self.load_model_button.setText("⏳ Loading...")
        self.model_combo.setDisabled(True)
        self.model_status_label.setText(f"⏳ Đang load {model_name}...")
        self.model_status_label.setStyleSheet(
            "color:#1d4ed8; font-family:Consolas; font-size:11px; font-weight:700;")
        self.load_worker = LoadModelWorker(self.cache, model_name, self)
        self.load_worker.progress.connect(self.statusBar().showMessage)
        self.load_worker.loaded.connect(self._on_model_loaded)
        self.load_worker.failed.connect(self._on_model_load_failed)
        self.load_worker.start()

    def _on_model_loaded(self, model_name: str) -> None:
        self.load_model_button.setEnabled(True)
        self.load_model_button.setText("↧ Load Model")
        self.model_combo.setEnabled(True)
        self._update_model_status()
        self.statusBar().showMessage(f"✅ {model_name} đã load xong vào RAM — sẵn sàng decode", 8000)
        self.load_worker = None

    def _on_model_load_failed(self, message: str) -> None:
        self.load_model_button.setEnabled(True)
        self.load_model_button.setText("↧ Load Model")
        self.model_combo.setEnabled(True)
        self._update_model_status()
        QMessageBox.critical(self, "Load model thất bại", message)
        self.load_worker = None

    def _set_busy(self, busy: bool) -> None:
        self.run_button.setDisabled(busy)
        self.open_button.setDisabled(busy)
        self.tts_button.setDisabled(busy)
        self.record_button.setDisabled(busy)
        self.play_button.setDisabled(busy)
        self.scenario_combo.setDisabled(busy)
        self.strength_combo.setDisabled(busy)
        self.model_combo.setDisabled(busy)
        self.load_model_button.setDisabled(busy)
        self.run_button.setText("Đang decode..." if busy else "Chạy so sánh 3 mode")

    def _stop_audio(self) -> None:
        if getattr(self, "_is_playing", False):
            try:
                sd.stop()
            except Exception:
                pass
            self._on_playback_finished()

    def _play_audio(self) -> None:
        if getattr(self, "_is_playing", False):
            self._stop_audio()
            return

        # Fallback load WAV if only wav_path exists
        if self.audio_samples is None and self.wav_path is not None and self.wav_path.is_file():
            try:
                samples, duration = experiment.read_pcm16_mono_16k(self.wav_path)
                self.audio_samples = samples
                self.audio_duration = duration
            except Exception as exc:
                QMessageBox.critical(self, "Lỗi đọc file âm thanh", str(exc))
                return

        if self.audio_samples is None or len(self.audio_samples) == 0:
            QMessageBox.warning(self, "Chưa có âm thanh", "Chưa có audio để phát. Hãy sinh TTS (Kokoro), thu âm hoặc chọn file WAV trước.")
            return

        try:
            sd.stop()
            dur = getattr(self, "audio_duration", 0.0)
            if dur <= 0:
                dur = len(self.audio_samples) / 16000.0
            sd.play(self.audio_samples, 16000)
            self._is_playing = True
            self.play_button.setText("⏹ Dừng")
            self.play_button.setStyleSheet("QPushButton { font-weight:600; color:#dc2626; }")
            self.statusBar().showMessage(f"▶ Đang phát âm thanh ({dur:.2f} s)...", int(dur * 1000) + 500)

            if not hasattr(self, "_play_timer"):
                self._play_timer = QTimer(self)
                self._play_timer.setSingleShot(True)
                self._play_timer.timeout.connect(self._on_playback_finished)
            self._play_timer.stop()
            self._play_timer.start(int(dur * 1000) + 200)
        except Exception as exc:
            self._on_playback_finished()
            QMessageBox.critical(self, "Lỗi phát âm thanh", str(exc))

    def _on_playback_finished(self) -> None:
        self._is_playing = False
        if hasattr(self, "_play_timer"):
            self._play_timer.stop()
        self.play_button.setText("▶ Nghe lại")
        self.play_button.setStyleSheet("QPushButton { font-weight:600; color:#0f766e; }")

    def _decode_done(self, results: dict[str, Any]) -> None:
        self._set_busy(False)
        for mode, card in self.cards.items():
            card.set_result(results[mode])
        ram_cost = results["global_bias"].get("ram_cost_mb", 0.0)
        self.cards["global_bias"].setTitle(f"3. Global + Logit Bias (Peak RAM diff: {ram_cost:+.1f} MB)")
        
        base = results["none"]["errors"]
        scenario = results["global_bias"]["errors"]
        verdict = "TỐT HƠN" if scenario < base else "XẤU HƠN" if scenario > base else "KHÔNG ĐỔI"

        # Log test result automatically to CSV
        row = {
            "Timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Model": f"whisper-{self.model_combo.currentText()}",
            "Source_Type": getattr(self, "source_type", "UNKNOWN"),
            "Scenario": str(self.scenario_combo.currentData() or ""),
            "Reference": self.reference_edit.text().strip(),
            "Baseline_Text": results["none"]["text"],
            "Baseline_WER": f"{results['none']['wer']*100:.1f}%" if results['none']['wer'] is not None else "0.0%",
            "Global_Text": results["global"]["text"],
            "Global_WER": f"{results['global']['wer']*100:.1f}%" if results['global']['wer'] is not None else "0.0%",
            "Global_RAM_MB": "0.0",
            "GlobalBias_Text": results["global_bias"]["text"],
            "GlobalBias_WER": f"{results['global_bias']['wer']*100:.1f}%" if results['global_bias']['wer'] is not None else "0.0%",
            "GlobalBias_RAM_MB": f"{ram_cost:+.1f}",
            "Scenario_Text": results["global_bias"]["text"],
            "Scenario_WER": f"{results['global_bias']['wer']*100:.1f}%" if results['global_bias']['wer'] is not None else "0.0%",
            "Prompt_Verdict": verdict,
            "Audio_Duration_s": f"{results['duration']:.2f}",
            "Saved_Audio_Path": getattr(self, "saved_audio_path", ""),
        }
        csv_path = experiment.ROOT / "test_history.csv"
        try:
            log_test_result(csv_path, row)
            log_msg = f" | Đã lưu vào {csv_path.name}"
        except Exception as e:
            log_msg = f" | Lỗi ghi log: {e}"

        self.statusBar().showMessage(
            f"Xong — scenario prompt: {verdict} so với baseline | "
            f"audio {results['duration']:.2f} s{log_msg}")
        self._update_model_status()  # confirm which model was actually used
        self.worker = None

    def _decode_failed(self, message: str) -> None:
        self._set_busy(False)
        QMessageBox.critical(self, "Decode thất bại", message)
        self.statusBar().showMessage(message)
        self.worker = None

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if any(url.toLocalFile().lower().endswith(".wav") or Path(url.toLocalFile()).is_dir()
               for url in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        wav_paths: list[Path] = []
        for url in event.mimeData().urls():
            path = Path(url.toLocalFile())
            if path.is_dir():
                wav_paths.extend(sorted(path.glob("*.wav")))
            elif path.suffix.lower() == ".wav":
                wav_paths.append(path)
        if wav_paths:
            event.acceptProposedAction()
            self._handle_multiple_wavs(wav_paths)

    def closeEvent(self, event) -> None:  # noqa: N802
        self.shutdown()
        super().closeEvent(event)

    def shutdown(self) -> None:
        """Release the mic and let an in-flight CPU decode finish cleanly."""
        self._stop_audio()
        self.meter_timer.stop()
        self.recorder.cancel()
        # Dung va ngat ket noi ESP32 neu dang chay
        if self._esp32_recording:
            try:
                if self._esp32_mic:
                    self._esp32_mic.discard()
            except Exception:
                pass
            self._esp32_recording = False
        if self._esp32_mic and self._esp32_mic.is_connected():
            try:
                self._esp32_mic.disconnect()
            except Exception:
                pass
        self.audio_samples = None
        if self.worker is not None and self.worker.isRunning():
            self.worker.wait(5000)


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = WhisperPromptDashboard()
    window.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
