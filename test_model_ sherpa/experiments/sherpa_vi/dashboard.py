#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Visual A/B/C dashboard for Sherpa-ONNX Zipformer VI.

Mirror of WhisperPromptDashboard but using Sherpa-ONNX with contextual biasing.
3-pass decode: BASELINE (no hotwords) / GLOBAL / AUTO SCENARIO (2-pass).
"""

from __future__ import annotations
import datetime
import io, json, os, sys, threading, traceback, wave
from pathlib import Path
from typing import Any
import numpy as np
import sounddevice as sd
import sherpa_onnx
from PyQt5.QtCore import QThread, QTimer, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QDragEnterEvent, QDropEvent, QFont, QPainter, QPen
from PyQt5.QtWidgets import (
    QApplication, QComboBox, QDialog, QFileDialog, QGridLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QPlainTextEdit, QPushButton, QSplitter, QStatusBar, QVBoxLayout, QWidget,
)
import run_vi as experiment

# Add experiments root to import tts_helpers and result_logger
_EXP_ROOT = Path(__file__).resolve().parents[1]
if str(_EXP_ROOT) not in sys.path:
    sys.path.insert(0, str(_EXP_ROOT))
from tts_helpers import VieNeuTTSWorker
from result_logger import log_test_result, generate_markdown_report

ROOT = Path(__file__).resolve().parent
MODEL_DIR = ROOT.parents[1] / "models" / "sherpa-onnx-zipformer-vi"
SAMPLE_RATE = 16000
MODE_TITLES = {
    "baseline": "1. Khong prompt",
    "global":   "2. Global prompt",
    "scenario": "3. Auto Scenario prompt",
}


class SherpaCache:
    recognizer: Any = None
    model_dir: str = ""


class LoadModelWorker(QThread):
    progress = pyqtSignal(str)
    loaded   = pyqtSignal(str)
    failed   = pyqtSignal(str)

    def __init__(self, cache, model_dir, parent=None):
        super().__init__(parent)
        self.cache = cache
        self.model_dir = model_dir

    def run(self):
        try:
            self.progress.emit(f"Loading Sherpa model from {self.model_dir}...")
            d = Path(self.model_dir)
            rec = sherpa_onnx.OfflineRecognizer.from_transducer(
                encoder=str(d / "encoder.int8.onnx"),
                decoder=str(d / "decoder.onnx"),
                joiner=str(d / "joiner.int8.onnx"),
                tokens=str(d / "tokens.txt"),
                num_threads=2, sample_rate=SAMPLE_RATE, feature_dim=80,
                modeling_unit="bpe",
                bpe_vocab=str(d / "bpe.vocab") if (d / "bpe.vocab").exists() else "",
                decoding_method="modified_beam_search",
                hotwords_file="", hotwords_score=0.0,
            )
            self.cache.recognizer = rec
            self.cache.model_dir = self.model_dir
            self.loaded.emit(self.model_dir)
        except Exception as exc:
            traceback.print_exc()
            self.failed.emit(str(exc))


def _transcribe(model_dir, samples, hotwords_text, score):
    import time, tempfile, os
    d = Path(model_dir)
    hw_file = ""
    tmp = None
    if hotwords_text.strip():
        lines = [ln.strip().upper() for ln in hotwords_text.splitlines() if ln.strip()]
        if lines:
            fd, tmp = tempfile.mkstemp(suffix=".txt", prefix="sherpa_hw_")
            os.close(fd)
            with open(tmp, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            hw_file = tmp
    try:
        t0 = time.time()
        rec = sherpa_onnx.OfflineRecognizer.from_transducer(
            encoder=str(d / "encoder.int8.onnx"),
            decoder=str(d / "decoder.onnx"),
            joiner=str(d / "joiner.int8.onnx"),
            tokens=str(d / "tokens.txt"),
            num_threads=2, sample_rate=SAMPLE_RATE, feature_dim=80,
            modeling_unit="bpe",
            bpe_vocab=str(d / "bpe.vocab") if (d / "bpe.vocab").exists() else "",
            decoding_method="modified_beam_search",
            hotwords_file=hw_file,
            hotwords_score=score if hw_file else 0.0,
        )
        stream = rec.create_stream()
        stream.accept_waveform(SAMPLE_RATE, samples)
        rec.decode_stream(stream)
        return stream.result.text.strip(), time.time() - t0
    finally:
        if tmp and os.path.exists(tmp):
            os.remove(tmp)


class DecodeWorker(QThread):
    progress  = pyqtSignal(str)
    completed = pyqtSignal(object)
    failed    = pyqtSignal(str)

    def __init__(self, model_dir, samples, duration, reference, global_prompt, score, config, parent=None):
        super().__init__(parent)
        self.model_dir     = model_dir
        self.samples       = samples.copy()
        self.duration      = duration
        self.reference     = reference
        self.global_prompt = global_prompt
        self.score         = score
        self.config        = config

    def run(self):
        try:
            results = {"duration": self.duration}

            def decode_raw(prompt, label):
                """Decode STT text and resolve intent."""
                self.progress.emit(f"Đang decode: {label}...")
                text, t = _transcribe(self.model_dir, self.samples, prompt, self.score)
                err, words = experiment.edit_counts(self.reference, text) \
                    if self.reference.strip() else (0, 0)
                res = experiment.resolve_scenario_vi(text, self.config)
                return {
                    "text": text, "seconds": t,
                    "rtf": t / self.duration if self.duration else 0.0,
                    "errors": err, "words": words,
                    "wer": err / words if words else None,
                    "resolution": res,
                }

            # Ô 1: Raw STT
            results["baseline"] = decode_raw("", "1. Không prompt")

            # Ô 2: STT có Global hotwords
            results["global"] = decode_raw(self.global_prompt, "2. Global prompt")

            # Ô 3: Chọn text có confidence cao nhất từ Ô 1 hoặc Ô 2
            self.progress.emit("Đang phân tích ý định từ JSON alias...")
            candidates = [
                (m, results[m]["resolution"])
                for m in ("global", "baseline")
                if results[m]["resolution"].status == "matched"
            ]
            
            scenario_prompt = ""
            auto_id = None
            if candidates:
                routing_source, best_res = max(candidates, key=lambda x: x[1].confidence)
                auto_id = best_res.scenario_id
                scen = experiment.scenario_map(self.config).get(auto_id, {})
                
                # CẢI TIẾN: Lấy danh sách phiên âm (alias) thay vì prompt tiếng Anh gốc
                scenario_prompt = experiment.get_phonetic_hotwords(auto_id, self.config)
                
                self.progress.emit(
                    f"Nhận diện kịch bản: {scen.get('name', auto_id)} từ {routing_source} — decode lại với phonetic hotwords...")
                combined = self.global_prompt + ("\n" + scenario_prompt if scenario_prompt else "")
                
                # Decode lại lần 3 với hotword phiên âm (OAI PHAI, DU TÚP)
                scenario_raw = decode_raw(combined, "3. Auto Scenario")
                
                # CẢI TIẾN: Text Normalization - Dịch phiên âm ngược về chuẩn (OAI PHAI -> WIFI)
                norm_text = experiment.normalize_text(scenario_raw["text"], self.config)
                if norm_text != scenario_raw["text"]:
                    self.progress.emit("Đã chuẩn hóa văn bản (Text Normalization) thành công!")
                    scenario_raw["text"] = norm_text
                    
                # Re-calculate WER after normalization
                err, words = experiment.edit_counts(self.reference, scenario_raw["text"]) \
                    if self.reference.strip() else (0, 0)
                scenario_raw["errors"] = err
                scenario_raw["words"] = words
                scenario_raw["wer"] = err / words if words else None
                
                res_final = scenario_raw["resolution"]
            else:
                self.progress.emit("Chưa đủ tín hiệu nhận kịch bản — hiển thị kết quả từ Global")
                scenario_raw = dict(results["global"])
                res_final = scenario_raw["resolution"]

            results["scenario"] = scenario_raw
            results["auto_scenario_id"] = auto_id
            results["applied_score"]    = self.score
            self.completed.emit(results)
        except Exception as exc:
            traceback.print_exc()
            self.failed.emit(str(exc))


class AudioRecorder:
    def __init__(self):
        self.stream = None
        self.rate = 0.0
        self.chunks: list = []
        self.lock = threading.Lock()

    @property
    def active(self):
        return self.stream is not None

    @property
    def recorded_seconds(self):
        with self.lock:
            count = sum(len(c) for c in self.chunks)
        return count / self.rate if self.rate else 0.0

    def start(self, device):
        if self.active:
            return
        info = sd.query_devices(device, "input")
        self.rate = float(info["default_samplerate"])
        self.chunks = []
        def cb(indata, frames, ti, status):
            if status:
                print(f"audio: {status}", file=sys.stderr)
            with self.lock:
                self.chunks.append(indata[:, 0].copy())
        self.stream = sd.InputStream(
            device=device, samplerate=self.rate, channels=1,
            dtype="float32", callback=cb)
        self.stream.start()

    def stop(self):
        if not self.active:
            raise RuntimeError("not recording")
        s = self.stream
        self.stream = None
        s.stop()
        s.close()
        with self.lock:
            samples = np.concatenate(self.chunks) if self.chunks else np.zeros(0, np.float32)
            self.chunks = []
        if not len(samples):
            raise RuntimeError("microphone returned no samples")
        if self.rate != SAMPLE_RATE:
            factor = self.rate / SAMPLE_RATE
            idx = (np.arange(int(len(samples) / factor)) * factor).astype(int)
            samples = samples[idx]
        return samples.astype(np.float32), len(samples) / SAMPLE_RATE

    def snapshot(self, seconds=2.0, max_points=1800):
        wanted = max(1, int(self.rate * seconds)) if self.rate else max_points
        with self.lock:
            chunks = []
            count = 0
            for chunk in reversed(self.chunks):
                chunks.append(chunk)
                count += len(chunk)
                if count >= wanted:
                    break
        if not chunks:
            return np.zeros(0, dtype=np.float32)
        s = np.concatenate(list(reversed(chunks)))[-wanted:]
        if len(s) > max_points:
            s = s[::max(1, len(s) // max_points)]
        return s.astype(np.float32, copy=False)

    def cancel(self):
        if self.active:
            s = self.stream
            self.stream = None
            s.stop()
            s.close()
            self.chunks = []


class ResultCard(QGroupBox):
    def __init__(self, mode):
        super().__init__(MODE_TITLES[mode])
        layout = QVBoxLayout(self)
        self.transcript = QPlainTextEdit()
        self.transcript.setReadOnly(True)
        self.transcript.setPlaceholderText("Chua decode")
        self.transcript.setMinimumHeight(125)
        self.transcript.setFont(QFont("Segoe UI", 12))
        self.metrics = QLabel("WER -   |   RTF -   |   time -")
        self.metrics.setStyleSheet("color:#64748b;")
        self.route = QLabel("Kich ban: -")
        self.route.setWordWrap(True)
        self.route.setStyleSheet("color:#334155;font-weight:600;")
        layout.addWidget(self.transcript)
        layout.addWidget(self.route)
        layout.addWidget(self.metrics)

    def set_result(self, result, show_route: bool = True):
        self.transcript.setPlainText(result["text"])
        wer = "-" if result["wer"] is None else f"{result['wer'] * 100:.1f}%"
        self.metrics.setText(
            f"WER {wer}   |   RTF {result['rtf']:.3f}   |   {result['seconds']:.2f} s")
        r = result.get("resolution")
        if not show_route or r is None:
            self.route.setText("")
            self.route.setStyleSheet("")
            return
        if r.status == "matched":
            slots_parts = []
            for k, v in r.slots.items():
                val_str = ", ".join(v) if isinstance(v, list) else str(v)
                slots_parts.append(f"{k}={val_str}")
            suf = " | " + " / ".join(slots_parts) if slots_parts else ""
            self.route.setText(
                f"✅ {r.scenario_name}  [{r.canonical_action}]  {r.confidence * 100:.0f}%{suf}")
            self.route.setStyleSheet("color:#15803d;font-weight:700;font-size:13px;")
        else:
            alts = ", ".join(n for n, _ in r.alternatives[:2])
            label = "Mờ hồ" if r.status == "ambiguous" else "Chưa đủ ý"
            self.route.setText(f"⚠️ {label}  —  Ứng viên: {alts}")
            self.route.setStyleSheet("color:#b45309;font-weight:700;")


class WaveformWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.samples = np.zeros(0, dtype=np.float32)
        self.setMinimumHeight(92)

    def set_samples(self, s):
        self.samples = np.asarray(s, dtype=np.float32).copy()
        self.update()

    def paintEvent(self, e):
        del e
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#0f172a"))
        mid = self.height() / 2.0
        p.setPen(QPen(QColor("#334155"), 1))
        p.drawLine(0, int(mid), self.width(), int(mid))
        if len(self.samples) < 2:
            p.end()
            return
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(QPen(QColor("#38bdf8"), 2))
        amp = max(1.0, self.height() * 0.44)
        px, py = 0, int(mid - float(self.samples[0]) * amp)
        denom = max(1, len(self.samples) - 1)
        for i, s in enumerate(self.samples[1:], 1):
            x = int(i * (self.width() - 1) / denom)
            y = int(mid - float(np.clip(s, -1.0, 1.0)) * amp)
            p.drawLine(px, py, x, y)
            px, py = x, y
        p.end()


class SherpaViDashboard(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config   = experiment.load_config()
        self.scenarios = experiment.scenario_map(self.config)
        self.cache    = SherpaCache()
        self.recorder = AudioRecorder()
        self.worker      = None
        self.load_worker = None
        self.wav_path    = None
        self.audio_samples  = None
        self.audio_duration = 0.0
        self.setWindowTitle("Sherpa-ONNX Zipformer VI - Benchmark Lab")
        self.resize(1320, 860)
        self.setAcceptDrops(True)
        self._build_ui()
        self._load_devices()
        self._scenario_changed()
        self._update_model_status()
        self.meter_timer = QTimer(self)
        self.meter_timer.timeout.connect(self._update_meter)
        self.meter_timer.start(50)

    # ----- UI Construction -----

    def _build_ui(self):
        central = QWidget()
        outer   = QVBoxLayout(central)

        title = QLabel("Sherpa-ONNX Zipformer VI + Contextual Biasing")
        title.setStyleSheet("font-size:23px;font-weight:700;color:#0f172a;")
        note = QLabel(
            "Tu dong 2 luot: Global Hotwords -> nhan dien intent "
            "-> nap dung Scenario Hotwords -> decode lai. "
            "O Kich ban ben duoi chi la expected label de test, khong lai model.")
        note.setWordWrap(True)
        note.setStyleSheet("color:#475569;margin-bottom:6px;")
        outer.addWidget(title)
        outer.addWidget(note)

        controls = QGroupBox("Input va kich ban")
        grid = QGridLayout(controls)

        self.model_path_edit = QLineEdit(str(MODEL_DIR))
        self.load_model_button = QPushButton("Load Model")
        self.load_model_button.setFixedWidth(110)
        self.load_model_button.setStyleSheet(
            "QPushButton{background:#0f766e;color:white;font-weight:600;"
            "border-radius:4px;padding:4px 8px;}"
            "QPushButton:disabled{background:#94a3b8;}")
        self.load_model_button.clicked.connect(self._load_model_clicked)
        self.model_status_label = QLabel()
        self.model_status_label.setStyleSheet("font-family:Consolas;font-size:11px;")

        self.scenario_combo = QComboBox()
        for item in sorted(self.config["scenarios"], key=lambda v: v["number"]):
            self.scenario_combo.addItem(f"{item['number']}. {item['name']}", item["id"])
        self.scenario_combo.currentIndexChanged.connect(self._scenario_changed)

        self.example_combo = QComboBox()
        self.example_combo.currentTextChanged.connect(self._example_changed)
        self.device_combo = QComboBox()

        self.score_combo = QComboBox()
        self.score_combo.addItem("1.0 - nhe (it anh huong den acoustic)", 1.0)
        self.score_combo.addItem("1.5 - trung binh (khuyen dung de test)", 1.5)
        self.score_combo.addItem("2.0 - manh hon", 2.0)
        self.score_combo.addItem("3.0 - rat manh, kiem tra carefully", 3.0)
        self.score_combo.setCurrentIndex(1)

        self.reference_edit = QLineEdit()
        self.reference_edit.setPlaceholderText("Reference: cau ban dinh noi (de tinh WER)")
        self.input_label = QLabel("Chua co audio - thu mic hoac chon WAV")
        self.input_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.waveform   = WaveformWidget()
        self.meter_label = QLabel("0.0 s   |   -inf dBFS   |   mic buffer: RAM only")
        self.meter_label.setStyleSheet("color:#64748b;font-family:Consolas;")

        self.open_button   = QPushButton("Chọn WAV…")
        self.tts_button    = QPushButton("🔊 Sinh TTS (VieNeu)")
        self.tts_button.setStyleSheet("QPushButton { font-weight:600; color:#0369a1; }")
        self.record_button = QPushButton("● Thu âm")
        self.play_button   = QPushButton("▶ Nghe lại")
        self.play_button.setStyleSheet("QPushButton { font-weight:600; color:#0f766e; }")
        self.run_button    = QPushButton("Chạy so sánh 3 mode")
        self.run_button.setStyleSheet(
            "QPushButton{background:#2563eb;color:white;padding:9px 16px;"
            "font-weight:600;border-radius:5px;}"
            "QPushButton:disabled{background:#94a3b8;}")
        self.export_button = QPushButton("📊 Xuất báo cáo (CSV/MD)")
        self.export_button.setStyleSheet("QPushButton { font-weight:600; color:#7c3aed; }")
        self.open_button.clicked.connect(self._choose_wav)
        self.tts_button.clicked.connect(self._generate_tts_vieneu)
        self.record_button.clicked.connect(self._toggle_record)
        self.play_button.clicked.connect(self._play_audio)
        self.run_button.clicked.connect(self._run_decode)
        self.export_button.clicked.connect(self._export_report)

        grid.addWidget(QLabel("Sherpa Model"), 0, 0)
        mr = QHBoxLayout()
        mr.addWidget(self.model_path_edit)
        mr.addWidget(self.load_model_button)
        mr.addWidget(self.model_status_label, 1)
        grid.addLayout(mr, 0, 1, 1, 3)
        grid.addWidget(QLabel("Kịch bản"),     1, 0); grid.addWidget(self.scenario_combo, 1, 1, 1, 3)
        grid.addWidget(QLabel("Câu mẫu"),      2, 0); grid.addWidget(self.example_combo,  2, 1, 1, 3)
        grid.addWidget(QLabel("Hotwords score"), 3, 0); grid.addWidget(self.score_combo,  3, 1, 1, 3)
        grid.addWidget(QLabel("Microphone"),   4, 0); grid.addWidget(self.device_combo,   4, 1, 1, 3)
        grid.addWidget(QLabel("Reference"),    5, 0); grid.addWidget(self.reference_edit, 5, 1, 1, 3)
        grid.addWidget(QLabel("Audio"),        6, 0); grid.addWidget(self.input_label,    6, 1, 1, 3)
        meter = QVBoxLayout()
        meter.addWidget(self.waveform)
        meter.addWidget(self.meter_label)
        grid.addLayout(meter, 7, 0, 1, 4)
        buttons = QHBoxLayout()
        for btn in (self.open_button, self.tts_button, self.record_button, self.play_button, self.run_button, self.export_button):
            buttons.addWidget(btn)
        grid.addLayout(buttons, 8, 0, 1, 4)
        outer.addWidget(controls)

        splitter = QSplitter(Qt.Vertical)
        rw = QWidget()
        rl = QHBoxLayout(rw)
        self.cards = {mode: ResultCard(mode) for mode in ("baseline", "global", "scenario")}
        for card in self.cards.values():
            rl.addWidget(card)
        splitter.addWidget(rw)

        prompts = QWidget()
        pg = QGridLayout(prompts)
        self.global_prompt   = QPlainTextEdit(self.config.get("global_prompt", ""))
        self.scenario_prompt = QPlainTextEdit()
        self.global_prompt_label = QLabel("Global Hotwords")
        self.save_prompt_button = QPushButton("💾 Luu Global Hotwords")
        self.save_prompt_button.setStyleSheet(
            "QPushButton{background:#7c3aed;color:white;font-weight:600;"
            "border-radius:4px;padding:4px 10px;}"
            "QPushButton:hover{background:#6d28d9;}"
            "QPushButton:disabled{background:#94a3b8;}")
        self.save_prompt_button.clicked.connect(self._save_global_prompt)
        lr = QHBoxLayout()
        lr.addWidget(self.global_prompt_label, 1)
        lr.addWidget(self.save_prompt_button)
        self.global_prompt.textChanged.connect(self._update_hotwords_count)
        self._update_hotwords_count()
        pg.addLayout(lr, 0, 0)
        pg.addWidget(QLabel("Scenario Hotwords (auto-router tu chon khi chay)"), 0, 1)
        pg.addWidget(self.global_prompt,   1, 0)
        pg.addWidget(self.scenario_prompt, 1, 1)
        splitter.addWidget(prompts)
        splitter.setSizes([360, 250])
        outer.addWidget(splitter, 1)
        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Chon kich ban va thu WAV moi hoac chon WAV mau")

    # ----- Slots -----

    def _update_hotwords_count(self):
        text  = self.global_prompt.toPlainText().strip()
        lines = [ln for ln in text.splitlines() if ln.strip()]
        ver   = str(self.config.get("global_prompt_version", "v1")).upper()
        self.global_prompt_label.setText(f"Global Hotwords {ver} - {len(lines)} dong")
        color = "#15803d" if lines else "#475569"
        self.global_prompt_label.setStyleSheet(f"color:{color};font-weight:700;")

    def _save_global_prompt(self):
        new = self.global_prompt.toPlainText().strip()
        if not new:
            QMessageBox.warning(self, "Khong luu", "Hotwords dang trong.")
            return
        p = experiment.DEFAULT_CONFIG
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:
            QMessageBox.critical(self, "Loi doc file", str(exc))
            return
        raw["global_prompt"] = new
        ver = raw.get("global_prompt_version", "v1")
        if not ver.endswith("-EDITED"):
            ver += "-EDITED"
        raw["global_prompt_version"] = ver
        try:
            p.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            QMessageBox.critical(self, "Loi ghi file", str(exc))
            return
        self.config["global_prompt"] = new
        self.config["global_prompt_version"] = ver
        self._update_hotwords_count()
        self.statusBar().showMessage(f"Da luu Global Hotwords vao {p.name}", 7000)

    def _load_devices(self):
        self.device_combo.clear()
        try:
            di = sd.default.device[0]
            for i, info in enumerate(sd.query_devices()):
                if int(info.get("max_input_channels", 0)) > 0:
                    self.device_combo.addItem(str(info["name"]), i)
                    if i == di:
                        self.device_combo.setCurrentIndex(self.device_combo.count() - 1)
        except Exception as exc:
            self.device_combo.addItem(f"Error: {exc}", None)

    def _scenario_changed(self):
        sid = self.scenario_combo.currentData()
        if not sid:
            return
        scen = self.scenarios.get(sid, {})
        self.scenario_prompt.setPlainText(str(scen.get("prompt", "")))
        examples = [str(v) for v in scen.get("examples", [])]
        self.example_combo.blockSignals(True)
        self.example_combo.clear()
        self.example_combo.addItems(examples)
        self.example_combo.blockSignals(False)
        if examples:
            self.reference_edit.setText(examples[0])

    def _example_changed(self, text):
        if text.strip():
            self.reference_edit.setText(text.strip())

    def _set_wav(self, path):
        self._stop_audio()
        self.audio_samples = None
        self.audio_duration = 0.0
        try:
            samples, dur = experiment.read_wav_to_float32_16k(path)
            self.audio_samples  = samples
            self.audio_duration = dur
            self.wav_path = path.resolve()
            self.source_type = "FILE_WAV"
            self.saved_audio_path = str(self.wav_path)
            self.waveform.set_samples(samples[-32000:] if len(samples) > 32000 else samples)
            self.input_label.setText(str(self.wav_path))
            self.statusBar().showMessage(f"Đã chọn {self.wav_path.name} ({dur:.2f}s)")
        except Exception as exc:
            QMessageBox.critical(self, "Lỗi đọc WAV", str(exc))

    def _choose_wav(self):
        name, _ = QFileDialog.getOpenFileName(
            self, "Chọn WAV 16 kHz", str(ROOT), "WAV audio (*.wav)")
        if name:
            self._set_wav(Path(name))

    def _generate_tts_vieneu(self):
        text = self.reference_edit.text().strip()
        if not text:
            text = self.example_combo.currentText().strip()
            if text:
                self.reference_edit.setText(text)
        if not text:
            QMessageBox.warning(self, "Thiếu văn bản", "Hãy nhập câu cần đọc vào Reference hoặc chọn câu mẫu.")
            return

        self.tts_button.setDisabled(True)
        self.tts_button.setText("⏳ Đang sinh...")
        self.statusBar().showMessage(f"Đang sinh âm thanh VieNeu-TTS cho: '{text}'...")

        self.tts_worker = VieNeuTTSWorker(text, parent=self)
        self.tts_worker.progress.connect(self.statusBar().showMessage)
        self.tts_worker.completed.connect(self._on_tts_completed)
        self.tts_worker.failed.connect(self._on_tts_failed)
        self.tts_worker.start()

    def _on_tts_completed(self, samples: np.ndarray, duration: float):
        self._stop_audio()
        self.tts_button.setEnabled(True)
        self.tts_button.setText("🔊 Sinh TTS (VieNeu)")
        self.audio_samples = samples
        self.audio_duration = duration
        self.wav_path = None
        self.source_type = "TTS_VIENEU"

        import soundfile as sf
        rec_dir = ROOT.parents[1] / "recordings"
        rec_dir.mkdir(parents=True, exist_ok=True)
        t_stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        out_wav = rec_dir / f"vieneu_{t_stamp}.wav"
        try:
            sf.write(str(out_wav), samples, 16000, subtype="PCM_16")
            self.saved_audio_path = str(out_wav)
            save_name = out_wav.name
        except Exception:
            self.saved_audio_path = ""
            save_name = "RAM"

        self.waveform.set_samples(samples[-32000:])
        self.input_label.setText(f"TTS VieNeu: {duration:.2f} s (Đã lưu: {save_name})")
        self.statusBar().showMessage(f"✅ Đã sinh âm VieNeu ({duration:.2f} s) — sẵn sàng decode", 6000)

    def _on_tts_failed(self, err: str):
        self.tts_button.setEnabled(True)
        self.tts_button.setText("🔊 Sinh TTS (VieNeu)")
        QMessageBox.critical(self, "Lỗi VieNeu-TTS", err)
        self.statusBar().showMessage(f"Lỗi VieNeu: {err}")

    def _export_report(self):
        csv_path = ROOT / "test_history.csv"
        md_text = generate_markdown_report(csv_path, "Báo cáo thử nghiệm: Sherpa VI Hotwords vs Không Hotwords")
        md_file = ROOT / "TEST_REPORT.md"
        try:
            md_file.write_text(md_text, encoding="utf-8")
        except Exception:
            pass

        dlg = QDialog(self)
        dlg.setWindowTitle("Báo cáo kết quả thử nghiệm: Hotwords vs Không Hotwords")
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
        open_folder_btn.clicked.connect(lambda: os.startfile(str(ROOT)))
        btn_box.addWidget(open_folder_btn)
        btn_box.addStretch(1)
        close_btn = QPushButton("Đóng")
        close_btn.clicked.connect(dlg.accept)
        btn_box.addWidget(close_btn)
        ly.addLayout(btn_box)
        dlg.exec_()

    def _toggle_record(self):
        if not self.recorder.active:
            try:
                self._stop_audio()
                device = self.device_combo.currentData()
                self.wav_path = None
                self.audio_samples = None
                self.waveform.set_samples(np.zeros(0, dtype=np.float32))
                self.recorder.start(device)
                self.record_button.setText("■ Dừng thu")
                self.record_button.setStyleSheet("background:#dc2626;color:white;padding:7px;")
                self.statusBar().showMessage("Đang thu... hãy nói một câu rồi bấm Dừng thu")
            except Exception as exc:
                QMessageBox.critical(self, "Không mở được microphone", str(exc))
        else:
            try:
                audio, dur = self.recorder.stop()
                self.audio_samples  = audio
                self.audio_duration = dur
                self.wav_path = None
                self.source_type = "MIC"

                # Auto save mic take to recordings
                import soundfile as sf
                rec_dir = ROOT.parents[1] / "recordings"
                rec_dir.mkdir(parents=True, exist_ok=True)
                t_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                saved_wav = rec_dir / f"mic_sherpa_{t_str}.wav"
                try:
                    sf.write(str(saved_wav), audio, 16000, subtype="PCM_16")
                    self.saved_audio_path = str(saved_wav)
                    saved_name = saved_wav.name
                except Exception:
                    self.saved_audio_path = ""
                    saved_name = "RAM"

                self.waveform.set_samples(audio[-32000:])
                self.input_label.setText(
                    f"Microphone buffer: {dur:.2f} s, mono 16 kHz (Đã lưu: {saved_name})")
                self.statusBar().showMessage(
                    f"Đã thu {dur:.1f} giây và lưu {saved_name} — sẵn sàng decode")
            except Exception as exc:
                QMessageBox.critical(self, "Thu âm thất bại", str(exc))
            finally:
                self.record_button.setText("● Thu âm")
                self.record_button.setStyleSheet("")

    def _update_meter(self):
        if not self.recorder.active:
            return
        s    = self.recorder.snapshot()
        self.waveform.set_samples(s)
        rms  = float(np.sqrt(np.mean(np.square(s)))) if len(s) else 0.0
        dbfs = 20.0 * np.log10(max(rms, 1e-8))
        dur  = self.recorder.recorded_seconds
        self.meter_label.setText(
            f"{dur:5.1f} s   |   {dbfs:6.1f} dBFS   |   mic buffer: RAM only")

    def _update_model_status(self):
        md = self.model_path_edit.text().strip()
        if self.cache.model_dir == md and self.cache.recognizer is not None:
            self.model_status_label.setText("✅ Da load - san sang decode")
            self.model_status_label.setStyleSheet(
                "color:#15803d;font-family:Consolas;font-size:11px;font-weight:700;")
        else:
            self.model_status_label.setText("⚠ Chua load - bam Load Model truoc khi chay")
            self.model_status_label.setStyleSheet(
                "color:#b45309;font-family:Consolas;font-size:11px;font-weight:700;")

    def _load_model_clicked(self):
        md = self.model_path_edit.text().strip()
        if self.cache.model_dir == md and self.cache.recognizer is not None:
            QMessageBox.information(self, "San sang", "Model da duoc load roi.")
            return
        self.load_model_button.setDisabled(True)
        self.load_model_button.setText("⏳ Loading...")
        self.model_path_edit.setDisabled(True)
        self.model_status_label.setText("⏳ Dang load model...")
        self.model_status_label.setStyleSheet(
            "color:#1d4ed8;font-family:Consolas;font-size:11px;font-weight:700;")
        self.load_worker = LoadModelWorker(self.cache, md, self)
        self.load_worker.progress.connect(self.statusBar().showMessage)
        self.load_worker.loaded.connect(self._on_model_loaded)
        self.load_worker.failed.connect(self._on_model_load_failed)
        self.load_worker.start()

    def _on_model_loaded(self, md):
        self.load_model_button.setEnabled(True)
        self.load_model_button.setText("↧ Load Model")
        self.model_path_edit.setEnabled(True)
        self._update_model_status()
        self.statusBar().showMessage("✅ Model da load xong - san sang decode", 8000)
        self.load_worker = None

    def _on_model_load_failed(self, msg):
        self.load_model_button.setEnabled(True)
        self.load_model_button.setText("↧ Load Model")
        self.model_path_edit.setEnabled(True)
        self._update_model_status()
        QMessageBox.critical(self, "Load model that bai", msg)
        self.load_worker = None

    def _stop_audio(self):
        if getattr(self, "_is_playing", False):
            try:
                import sounddevice as sd
                sd.stop()
            except Exception:
                pass
            self._on_playback_finished()

    def _play_audio(self):
        if getattr(self, "_is_playing", False):
            self._stop_audio()
            return

        if self.audio_samples is None or len(self.audio_samples) == 0:
            QMessageBox.warning(self, "Trống", "Chưa có âm thanh nào để phát.")
            return
        try:
            import sounddevice as sd
            sd.stop()
            dur = getattr(self, "audio_duration", 0.0)
            if dur <= 0:
                dur = len(self.audio_samples) / float(SAMPLE_RATE)
            sd.play(self.audio_samples, SAMPLE_RATE)
            self._is_playing = True
            self.play_button.setText("⏹ Dừng")
            self.play_button.setStyleSheet("QPushButton { font-weight:600; color:#dc2626; }")
            self.statusBar().showMessage("▶ Đang phát lại âm thanh...", int(dur * 1000) + 500)

            if not hasattr(self, "_play_timer"):
                self._play_timer = QTimer(self)
                self._play_timer.setSingleShot(True)
                self._play_timer.timeout.connect(self._on_playback_finished)
            self._play_timer.stop()
            self._play_timer.start(int(dur * 1000) + 200)
        except Exception as exc:
            self._on_playback_finished()
            QMessageBox.critical(self, "Lỗi phát âm thanh", str(exc))

    def _on_playback_finished(self):
        self._is_playing = False
        if hasattr(self, "_play_timer"):
            self._play_timer.stop()
        self.play_button.setText("▶ Nghe lại")
        self.play_button.setStyleSheet("QPushButton { font-weight:600; color:#0f766e; }")

    def _run_decode(self):
        self._stop_audio()
        if self.audio_samples is None:
            QMessageBox.warning(self, "Thieu audio", "Chon WAV hoac thu am truoc.")
            return
        if not Path(self.model_path_edit.text().strip()).exists():
            QMessageBox.critical(self, "Model khong tim thay",
                                 f"Thu muc model khong ton tai: {self.model_path_edit.text()}")
            return
        self._set_busy(True)
        score = float(self.score_combo.currentData())
        self.cards["scenario"].setTitle(f"3. Auto Scenario ({score}x score)")
        sid = self.scenario_combo.currentData()
        if sid and sid in self.scenarios:
            self.scenarios[sid]["prompt"] = self.scenario_prompt.toPlainText().strip()
        self.worker = DecodeWorker(
            self.model_path_edit.text().strip(),
            self.audio_samples, self.audio_duration,
            self.reference_edit.text(),
            self.global_prompt.toPlainText().strip(),
            score, self.config, self)
        self.worker.progress.connect(self.statusBar().showMessage)
        self.worker.completed.connect(self._decode_done)
        self.worker.failed.connect(self._decode_failed)
        self.worker.start()

    def _set_busy(self, busy):
        for w in (self.run_button, self.open_button, self.tts_button,
                  self.record_button, self.play_button, self.scenario_combo, 
                  self.score_combo, self.load_model_button):
            w.setDisabled(busy)
        self.run_button.setText("Đang decode..." if busy else "Chạy so sánh 3 mode")

    def _decode_done(self, results):
        self._set_busy(False)
        # Ô 1 & 2: chỉ hiện text raw STT, không hiện intent/route
        self.cards["baseline"].set_result(results["baseline"], show_route=False)
        self.cards["global"].set_result(results["global"], show_route=False)
        # Ô 3: hiện kết quả phân tích ý định từ JSON alias
        self.cards["scenario"].set_result(results["scenario"], show_route=True)
        auto_id = results.get("auto_scenario_id")
        if auto_id:
            name = self.scenarios.get(auto_id, {}).get("name", auto_id)
            self.cards["scenario"].setTitle(
                f"3. Auto Scenario: {name} ({results['applied_score']}x)")
        else:
            self.cards["scenario"].setTitle("3. Auto Scenario — Phân tích ý định (JSON alias)")
        be = results["baseline"]["errors"]
        se = results["scenario"]["errors"]
        verdict = "TỐT HƠN" if se < be else "XẤU HƠN" if se > be else "KHÔNG ĐỔI"

        # Log test result automatically to CSV
        row = {
            "Timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Model": "sherpa-onnx-zipformer-vi",
            "Source_Type": getattr(self, "source_type", "UNKNOWN"),
            "Scenario": str(self.scenario_combo.currentData() or ""),
            "Reference": self.reference_edit.text().strip(),
            "Baseline_Text": results["baseline"]["text"],
            "Baseline_WER": f"{results['baseline']['wer']*100:.1f}%" if results['baseline']['wer'] is not None else "0.0%",
            "Global_Text": results["global"]["text"],
            "Global_WER": f"{results['global']['wer']*100:.1f}%" if results['global']['wer'] is not None else "0.0%",
            "Scenario_Text": results["scenario"]["text"],
            "Scenario_WER": f"{results['scenario']['wer']*100:.1f}%" if results['scenario']['wer'] is not None else "0.0%",
            "Prompt_Verdict": verdict,
            "Audio_Duration_s": f"{results['duration']:.2f}",
            "Saved_Audio_Path": getattr(self, "saved_audio_path", ""),
        }
        csv_path = ROOT / "test_history.csv"
        try:
            log_test_result(csv_path, row)
            log_msg = f" | Đã lưu vào {csv_path.name}"
        except Exception as e:
            log_msg = f" | Lỗi ghi log: {e}"

        self.statusBar().showMessage(
            f"Xong — scenario: {verdict} so với baseline | audio {results['duration']:.2f} s{log_msg}")
        self._update_model_status()
        self.worker = None

    def _decode_failed(self, msg):
        self._set_busy(False)
        QMessageBox.critical(self, "Decode that bai", msg)
        self.statusBar().showMessage(msg)
        self.worker = None

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if any(u.toLocalFile().lower().endswith(".wav") for u in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        for url in event.mimeData().urls():
            p = Path(url.toLocalFile())
            if p.suffix.lower() == ".wav":
                self._set_wav(p)
                event.acceptProposedAction()
                break

    def closeEvent(self, event) -> None:
        self.shutdown()
        super().closeEvent(event)

    def shutdown(self) -> None:
        self._stop_audio()
        self.meter_timer.stop()
        self.recorder.cancel()
        self.audio_samples = None
        if self.worker is not None and self.worker.isRunning():
            self.worker.wait(5000)


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = SherpaViDashboard()
    window.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
