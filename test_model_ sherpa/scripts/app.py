#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
app.py  (PySide6 desktop version)
----------------------------------
Entrypoint: mo cua so desktop so sanh STT Sherpa-onnx.
  python scripts/app.py

Cau truc:
  MainWindow     : QMainWindow chinh, chua toan bo UI
  STTWorker      : QObject chay stt.transcribe_both() trong QThread,
                   emit signal khi xong -> cap nhat UI an toan
  TTSWorker      : QObject chay tts_eng.generate_tts_audio() trong QThread
  QTimer (2s)    : Poll stt.is_loaded() / tts_eng.is_tts_loaded()
                   tuong duong gr.Timer cua Gradio version
"""

from __future__ import annotations

import os
import sys
import random
import threading
import tempfile
from datetime import datetime
from pathlib import Path

import numpy as np

# ---------------------------------------------------------------------------
# sys.path setup (giu nguyen tu Gradio version)
# ---------------------------------------------------------------------------
SCRIPTS_DIR = Path(__file__).parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import audio_utils    as au
import stt_engine     as stt
import tts_engine     as tts_eng
import results_logger as rl
import homophone_mapper as hm
from mic_recorder import MicRecorder
from esp32_mic_recorder import ESP32MicRecorder

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTextEdit, QLineEdit, QTabWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox,
    QFileDialog, QScrollArea, QSizePolicy, QFrame, QSplitter,
)
from PySide6.QtCore  import Qt, QTimer, QObject, Signal, Slot, QThread
from PySide6.QtGui   import QFont

# ---------------------------------------------------------------------------
# Config / constants
# ---------------------------------------------------------------------------
BASE_DIR      = SCRIPTS_DIR.parent
CONFIG_DIR    = BASE_DIR / "config"
HOTWORDS_FILE = str(CONFIG_DIR / "hotwords.txt")

SAMPLE_SENTENCES = [
    "Xin chao cac ban, hom nay troi dep qua.",
    "Mo hinh nhan dang giong noi tieng Viet dang duoc thu nghiem.",
    "Chan doan benh nhan can kiem tra them xet nghiem mau.",
    "Sherpa onnx la thu vien STT nhanh va hieu qua.",
    "Zipformer la kien truc encoder hien dai cho nhan dang giong noi.",
    "Hotwords giup tang do chinh xac cac tu chuyen nganh trong STT.",
    "Vui long doc to va ro rang de ket qua nhan dang tot nhat.",
    "He thong nhan dang giong noi tieng Viet da duoc cai thien nhieu.",
    "Toi muon dat phong khach san gan trung tam thanh pho.",
    "Bao cao tai chinh quy nay cho thay tang truong 15 phan tram.",
]

DATAFRAME_HEADERS = ["#", "Thoi gian", "Nguon", "Reference", "Pipeline A", "Pipeline B", "WER A", "WER B"]

# ---------------------------------------------------------------------------
# Bien toan cuc (giu nguyen tu Gradio version)
# ---------------------------------------------------------------------------
_current_audio: np.ndarray | None = None
_current_source: str = ""
_current_reference: str = ""
_audio_lock = threading.Lock()


def _set_current_audio(samples: np.ndarray, source: str, reference: str = ""):
    global _current_audio, _current_source, _current_reference
    with _audio_lock:
        _current_audio     = samples
        _current_source    = source
        _current_reference = reference


def _get_current_audio():
    with _audio_lock:
        return _current_audio, _current_source, _current_reference


# ---------------------------------------------------------------------------
# Qt Style Sheet (cung mau voi Gradio CSS)
# ---------------------------------------------------------------------------
QSS = """
QMainWindow, QWidget { background:#f0f2f6; font-family:'Segoe UI'; font-size:13px; }

#header { background:qlineargradient(x1:0,y1:0,x2:1,y2:1,
    stop:0 #1a1a2e, stop:.5 #16213e, stop:1 #0f3460);
    border-radius:10px; padding:14px 22px; }

#header_title { font-size:20px; font-weight:bold; color:#e94560; }
#header_sub   { font-size:12px; color:#bbccdd; }

#section_label { font-size:13px; font-weight:bold; color:#0f3460;
    border-left:4px solid #e94560; padding-left:8px; margin-top:6px; }

#status_label { padding:6px 12px; border-radius:6px;
    font-weight:bold; color:white; background:#e74c3c; }

QPushButton { border-radius:6px; padding:5px 14px; font-size:13px; }

#btn_load    { background:#e94560; color:white; font-weight:bold; }
#btn_load:hover { background:#c0392b; }
#btn_load:disabled { background:#aaa; color:#eee; }

#btn_compare { background:#0f3460; color:white; font-weight:bold; }
#btn_compare:hover { background:#0a2040; }
#btn_compare:disabled { background:#aaa; color:#eee; }

#btn_tts     { background:#16213e; color:white; }
#btn_tts:disabled { background:#aaa; color:#eee; }

#btn_save_hw { background:#27ae60; color:white; }
#btn_save_hw:disabled { background:#aaa; color:#eee; }

#btn_export  { background:#8e44ad; color:white; }
#btn_export:disabled { background:#aaa; color:#eee; }

#btn_start_rec { background:#e74c3c; color:white; }
#btn_start_rec:disabled { background:#aaa; color:#eee; }
#btn_stop_rec  { background:#2c3e50; color:white; }
#btn_stop_rec:disabled { background:#aaa; color:#eee; }

#btn_esp_connect { background:#27ae60; color:white; font-weight:bold; }
#btn_esp_connect:hover { background:#219150; }

QGroupBox#group_a { border:2px solid #e94560; border-radius:8px; margin-top:8px; }
QGroupBox#group_a::title { color:#e94560; font-weight:bold; subcontrol-origin:margin; left:10px; }
QGroupBox#group_b { border:2px solid #0f3460; border-radius:8px; margin-top:8px; }
QGroupBox#group_b::title { color:#0f3460; font-weight:bold; subcontrol-origin:margin; left:10px; }

QTableWidget { font-size:12px; gridline-color:#ddd; }
QHeaderView::section { background:#0f3460; color:white; padding:4px; font-weight:bold; }

QTabBar::tab { padding:6px 16px; }
QTabBar::tab:selected { border-bottom:3px solid #e94560; font-weight:bold; }

QTextEdit, QLineEdit { border:1px solid #ccc; border-radius:4px; padding:3px; background:white; }
QTextEdit[readOnly="true"] { background:#f9f9f9; }
"""


# ===========================================================================
# Workers — chay vu tinh toan nang trong QThread phu
# ===========================================================================
class STTWorker(QObject):
    """Chay stt.transcribe_both() trong thread phu, emit signal khi xong."""
    finished = Signal(str, str, str, str, str)   # status, text_a, metric_a, text_b, metric_b
    error    = Signal(str)

    def __init__(self, samples: np.ndarray, source: str, reference: str):
        super().__init__()
        self._samples   = samples
        self._source    = source
        self._reference = reference

    @Slot()
    def run(self):
        try:
            text_a, text_b = stt.transcribe_both(self._samples)
        except Exception as e:
            self.error.emit(f"Loi STT: {e}")
            return

        wer_a = wer_b = cer_a = cer_b = -1.0
        metric_a = metric_b = ""
        if self._reference:
            wer_a = stt.compute_wer(self._reference, text_a)
            wer_b = stt.compute_wer(self._reference, text_b)
            cer_a = stt.compute_cer(self._reference, text_a)
            cer_b = stt.compute_cer(self._reference, text_b)
            metric_a = f"WER: {wer_a:.1%}  |  CER: {cer_a:.1%}"
            metric_b = f"WER: {wer_b:.1%}  |  CER: {cer_b:.1%}"

        rl.append_result(
            source=self._source, pipeline_a=text_a, pipeline_b=text_b,
            reference=self._reference,
            wer_a=wer_a, wer_b=wer_b, cer_a=cer_a, cer_b=cer_b,
        )
        ref_disp = self._reference if self._reference else "(khong co reference)"
        status   = f"So sanh hoan tat ({self._source}). Reference: {ref_disp}"
        self.finished.emit(status, text_a, metric_a, text_b, metric_b)


class TTSWorker(QObject):
    """Chay tts_eng.generate_tts_audio() trong thread phu."""
    finished = Signal(object, str, str)   # samples(np.ndarray), text, status_msg
    error    = Signal(str)

    def __init__(self, text: str):
        super().__init__()
        self._text = text

    @Slot()
    def run(self):
        try:
            samples = tts_eng.generate_tts_audio(self._text)
            dur     = len(samples) / 16000.0
            status  = f"Da tao audio TTS ({dur:.1f}s). San sang so sanh."
            self.finished.emit(samples, self._text, status)
        except Exception as e:
            self.error.emit(f"Loi TTS: {e}")


# ===========================================================================
# Helper: ham doc hotwords (giu nguyen logic tu Gradio version)
# ===========================================================================
def _handle_load_hotwords_file() -> str:
    if os.path.exists(HOTWORDS_FILE):
        with open(HOTWORDS_FILE, "r", encoding="utf-8") as f:
            return f.read()
    return ""


def _handle_save_hotwords(hotwords_text: str) -> str:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with open(HOTWORDS_FILE, "w", encoding="utf-8") as f:
            f.write(hotwords_text.strip() + "\n" if hotwords_text.strip() else "")
        reload_msg = stt.reload_pipeline_b()
        ts    = datetime.now().strftime("%H:%M:%S")
        count = len([l for l in hotwords_text.splitlines() if l.strip()])
        return f"Da luu {count} hotwords vao '{HOTWORDS_FILE}' luc {ts}. {reload_msg}"
    except Exception as e:
        return f"Loi khi luu hotwords: {e}"


# ===========================================================================
# MainWindow
# ===========================================================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("So sanh STT: Baseline vs Context-aware — Sherpa-onnx")
        self.setMinimumSize(1100, 820)
        self.resize(1200, 900)

        # Mic recorder instance
        self._mic = MicRecorder()
        self._esp32_mic = ESP32MicRecorder(port="COM16", baudrate=2000000)

        # Thread references (de tranh GC thu gom khi thread dang chay)
        self._stt_thread: QThread | None = None
        self._tts_thread: QThread | None = None

        # --- Build UI ---
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(12, 12, 12, 12)

        # Scrollable inner area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        inner = QWidget()
        self._inner_layout = QVBoxLayout(inner)
        self._inner_layout.setSpacing(8)
        scroll.setWidget(inner)
        main_layout.addWidget(scroll)

        self._build_header()
        self._build_load_section()
        self._build_audio_tabs()
        self._build_hotwords_section()
        self._build_comparison_section()
        self._build_history_section()
        self._build_export_section()

        # --- QTimer poll (tuong duong gr.Timer 2s cua Gradio version) ---
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(2000)
        self._poll_timer.timeout.connect(self._poll_model_status)

        # Load hotwords khi khoi dong (tuong duong demo.load(...))
        self._txt_hotwords.setPlainText(_handle_load_hotwords_file())
        self._txt_homophones.setPlainText(hm.get_raw_text())

        # Apply QSS
        self.setStyleSheet(QSS)

    # -----------------------------------------------------------------------
    # Build UI helpers
    # -----------------------------------------------------------------------
    def _section_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("section_label")
        return lbl

    def _build_header(self):
        header = QFrame()
        header.setObjectName("header")
        hl = QVBoxLayout(header)
        hl.setContentsMargins(0, 0, 0, 0)
        t = QLabel("So sanh STT: Baseline vs Context-aware")
        t.setObjectName("header_title")
        s = QLabel("Sherpa-onnx Zipformer Vietnamese  •  Pipeline A (khong hotwords) vs Pipeline B (context + hotwords)")
        s.setObjectName("header_sub")
        hl.addWidget(t)
        hl.addWidget(s)
        self._inner_layout.addWidget(header)

    def _build_load_section(self):
        self._inner_layout.addWidget(self._section_label("1. Load Model"))
        row = QHBoxLayout()

        self._btn_load = QPushButton("Load Model")
        self._btn_load.setObjectName("btn_load")
        self._btn_load.setFixedWidth(160)
        self._btn_load.clicked.connect(self._on_load_model)

        self._lbl_status = QLabel("Chua load model")
        self._lbl_status.setObjectName("status_label")
        self._lbl_status.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        row.addWidget(self._btn_load)
        row.addWidget(self._lbl_status, stretch=1)
        self._inner_layout.addLayout(row)

    def _build_audio_tabs(self):
        self._inner_layout.addWidget(self._section_label("2. Nguon audio dau vao"))
        tabs = QTabWidget()

        # ---- Tab TTS ----
        tts_tab = QWidget()
        tl = QVBoxLayout(tts_tab)

        row1 = QHBoxLayout()
        self._txt_tts_input = QTextEdit()
        self._txt_tts_input.setPlaceholderText("Nhap cau van ban tieng Viet...")
        self._txt_tts_input.setMaximumHeight(70)
        self._txt_tts_input.setEnabled(False)
        row1.addWidget(self._txt_tts_input, stretch=4)

        btn_col = QVBoxLayout()
        self._btn_random = QPushButton("Cau ngau nhien")
        self._btn_random.setEnabled(False)
        self._btn_random.clicked.connect(self._on_random_sentence)

        self._btn_gen_tts = QPushButton("Tao audio TTS")
        self._btn_gen_tts.setObjectName("btn_tts")
        self._btn_gen_tts.setEnabled(False)
        self._btn_gen_tts.clicked.connect(self._on_generate_tts)

        self._btn_play_tts = QPushButton("Nghe lai Audio")
        self._btn_play_tts.setEnabled(False)
        self._btn_play_tts.clicked.connect(self._on_play_audio)

        btn_col.addWidget(self._btn_random)
        btn_col.addWidget(self._btn_gen_tts)
        btn_col.addWidget(self._btn_play_tts)
        row1.addLayout(btn_col, stretch=1)
        tl.addLayout(row1)

        self._lbl_tts_status = QLabel("(Chua tao TTS)")
        self._lbl_tts_status.setWordWrap(True)
        tl.addWidget(self._lbl_tts_status)

        ref_row = QHBoxLayout()
        ref_row.addWidget(QLabel("Reference (tu dong):"))
        self._txt_tts_ref = QLineEdit()
        self._txt_tts_ref.setReadOnly(True)
        ref_row.addWidget(self._txt_tts_ref, stretch=1)
        tl.addLayout(ref_row)

        tl.addStretch()
        tabs.addTab(tts_tab, "TTS (Sinh tu van ban)")

        # ---- Tab File ----
        file_tab = QWidget()
        fl = QVBoxLayout(file_tab)

        file_row = QHBoxLayout()
        self._lbl_file_path = QLineEdit()
        self._lbl_file_path.setReadOnly(True)
        self._lbl_file_path.setPlaceholderText("Chua chon file...")
        self._btn_choose_file = QPushButton("Chon file audio...")
        self._btn_choose_file.setEnabled(False)
        self._btn_choose_file.clicked.connect(self._on_choose_file)
        file_row.addWidget(self._lbl_file_path, stretch=3)
        file_row.addWidget(self._btn_choose_file)
        fl.addLayout(file_row)

        ref_row2 = QHBoxLayout()
        ref_row2.addWidget(QLabel("Reference text (tuy chon):"))
        self._txt_file_ref = QLineEdit()
        self._txt_file_ref.setPlaceholderText("Nhap cau dung neu biet...")
        self._txt_file_ref.setEnabled(False)
        self._txt_file_ref.textChanged.connect(
            lambda t: self._txt_ref_display.setText(t))
        ref_row2.addWidget(self._txt_file_ref, stretch=1)
        fl.addLayout(ref_row2)

        self._lbl_file_status = QLabel("(Chua chon file)")
        self._lbl_file_status.setWordWrap(True)
        fl.addWidget(self._lbl_file_status)

        self._btn_use_file = QPushButton("Dung audio nay de so sanh")
        self._btn_use_file.setEnabled(False)
        self._btn_use_file.clicked.connect(self._on_use_file)

        self._btn_play_file = QPushButton("Nghe lai Audio")
        self._btn_play_file.setEnabled(False)
        self._btn_play_file.clicked.connect(self._on_play_audio)

        file_btn_row = QHBoxLayout()
        file_btn_row.addWidget(self._btn_use_file)
        file_btn_row.addWidget(self._btn_play_file)
        fl.addLayout(file_btn_row)
        fl.addStretch()
        tabs.addTab(file_tab, "Upload File Audio")

        # ---- Tab Mic ----
        mic_tab = QWidget()
        ml = QVBoxLayout(mic_tab)

        rec_row = QHBoxLayout()
        self._btn_start_rec = QPushButton("Bat dau ghi am")
        self._btn_start_rec.setObjectName("btn_start_rec")
        self._btn_start_rec.setEnabled(False)
        self._btn_start_rec.clicked.connect(self._on_start_rec)

        self._btn_stop_rec = QPushButton("Dung ghi am")
        self._btn_stop_rec.setObjectName("btn_stop_rec")
        self._btn_stop_rec.setEnabled(False)
        self._btn_stop_rec.clicked.connect(self._on_stop_rec)

        self._lbl_rec_status = QLabel("(Chua ghi am)")
        self._lbl_rec_status.setWordWrap(True)

        rec_row.addWidget(self._btn_start_rec)
        rec_row.addWidget(self._btn_stop_rec)
        rec_row.addWidget(self._lbl_rec_status, stretch=1)
        ml.addLayout(rec_row)

        ref_row3 = QHBoxLayout()
        ref_row3.addWidget(QLabel("Reference text (tuy chon):"))
        self._txt_mic_ref = QLineEdit()
        self._txt_mic_ref.setPlaceholderText("Nhap cau dung neu biet...")
        self._txt_mic_ref.setEnabled(False)
        self._txt_mic_ref.textChanged.connect(
            lambda t: self._txt_ref_display.setText(t))
        ref_row3.addWidget(self._txt_mic_ref, stretch=1)
        ml.addLayout(ref_row3)

        self._btn_use_mic = QPushButton("Dung audio ghi am de so sanh")
        self._btn_use_mic.setEnabled(False)
        self._btn_use_mic.clicked.connect(self._on_use_mic)

        self._btn_play_mic = QPushButton("Nghe lai Audio")
        self._btn_play_mic.setEnabled(False)
        self._btn_play_mic.clicked.connect(self._on_play_audio)

        mic_btn_row = QHBoxLayout()
        mic_btn_row.addWidget(self._btn_use_mic)
        mic_btn_row.addWidget(self._btn_play_mic)
        ml.addLayout(mic_btn_row)
        ml.addStretch()
        tabs.addTab(mic_tab, "Ghi am Mic")

        # ---- Tab ESP32 INMP441 ----
        esp32_tab = QWidget()
        el = QVBoxLayout(esp32_tab)

        esp_conn_row = QHBoxLayout()
        esp_conn_row.addWidget(QLabel("COM Port:"))
        self._txt_esp_port = QLineEdit("COM16")
        self._txt_esp_port.setFixedWidth(90)
        esp_conn_row.addWidget(self._txt_esp_port)

        esp_conn_row.addWidget(QLabel("Baudrate:"))
        self._txt_esp_baud = QLineEdit("2000000")
        self._txt_esp_baud.setFixedWidth(90)
        esp_conn_row.addWidget(self._txt_esp_baud)

        self._btn_esp_connect = QPushButton("Ket noi ESP32")
        self._btn_esp_connect.setObjectName("btn_esp_connect")
        self._btn_esp_connect.clicked.connect(self._on_esp_connect)
        esp_conn_row.addWidget(self._btn_esp_connect)

        self._lbl_esp_conn_status = QLabel("Chua ket noi")
        self._lbl_esp_conn_status.setStyleSheet("color:#e74c3c; font-weight:bold;")
        esp_conn_row.addWidget(self._lbl_esp_conn_status, stretch=1)
        el.addLayout(esp_conn_row)

        esp_rec_row = QHBoxLayout()
        self._btn_start_esp = QPushButton("Bat dau ghi am")
        self._btn_start_esp.setObjectName("btn_start_rec")
        self._btn_start_esp.setEnabled(False)
        self._btn_start_esp.clicked.connect(self._on_start_esp)

        self._btn_stop_esp = QPushButton("Dung ghi am")
        self._btn_stop_esp.setObjectName("btn_stop_rec")
        self._btn_stop_esp.setEnabled(False)
        self._btn_stop_esp.clicked.connect(self._on_stop_esp)

        self._lbl_esp_rec_status = QLabel("(Chua ghi am)")
        self._lbl_esp_rec_status.setWordWrap(True)

        esp_rec_row.addWidget(self._btn_start_esp)
        esp_rec_row.addWidget(self._btn_stop_esp)
        esp_rec_row.addWidget(self._lbl_esp_rec_status, stretch=1)
        el.addLayout(esp_rec_row)

        esp_ref_row = QHBoxLayout()
        esp_ref_row.addWidget(QLabel("Reference text (tuy chon):"))
        self._txt_esp_ref = QLineEdit()
        self._txt_esp_ref.setPlaceholderText("Nhap cau dung neu biet...")
        self._txt_esp_ref.setEnabled(False)
        self._txt_esp_ref.textChanged.connect(
            lambda t: self._txt_ref_display.setText(t))
        esp_ref_row.addWidget(self._txt_esp_ref, stretch=1)
        el.addLayout(esp_ref_row)

        esp_btn_row = QHBoxLayout()
        self._btn_use_esp = QPushButton("Dung audio ESP32 de so sanh")
        self._btn_use_esp.setEnabled(False)
        self._btn_use_esp.clicked.connect(self._on_use_esp)

        self._btn_play_esp = QPushButton("Nghe lai Audio")
        self._btn_play_esp.setEnabled(False)
        self._btn_play_esp.clicked.connect(self._on_play_audio)

        esp_btn_row.addWidget(self._btn_use_esp)
        esp_btn_row.addWidget(self._btn_play_esp)
        el.addLayout(esp_btn_row)

        el.addStretch()
        tabs.addTab(esp32_tab, "ESP32 INMP441")

        self._inner_layout.addWidget(tabs)

    def _build_hotwords_section(self):
        self._inner_layout.addWidget(self._section_label(
            "3. Ngu canh Pipeline B: Hotwords (Boosting) & Tu dong am (Homophones)"))

        ctx_tabs = QTabWidget()

        # ---- Tab 1: Hotwords ----
        tab_hw = QWidget()
        hw_layout = QVBoxLayout(tab_hw)
        hw_layout.setContentsMargins(8, 8, 8, 8)
        self._txt_hotwords = QTextEdit()
        self._txt_hotwords.setPlaceholderText("WIFI :4.5\nLAPTOP :4.5\nSHERPA ONNX :5.0\nSTT :5.0")
        self._txt_hotwords.setMaximumHeight(100)
        self._txt_hotwords.setEnabled(False)
        hw_layout.addWidget(self._txt_hotwords)

        hw_row = QHBoxLayout()
        self._btn_save_hw = QPushButton("Luu hotwords")
        self._btn_save_hw.setObjectName("btn_save_hw")
        self._btn_save_hw.setEnabled(False)
        self._btn_save_hw.clicked.connect(self._on_save_hotwords)

        self._btn_load_hw = QPushButton("Tai hotwords tu file")
        self._btn_load_hw.setEnabled(False)
        self._btn_load_hw.clicked.connect(self._on_load_hotwords)

        self._lbl_hw_status = QLabel("")
        self._lbl_hw_status.setWordWrap(True)

        hw_row.addWidget(self._btn_save_hw)
        hw_row.addWidget(self._btn_load_hw)
        hw_row.addWidget(self._lbl_hw_status, stretch=1)
        hw_layout.addLayout(hw_row)
        ctx_tabs.addTab(tab_hw, "Hotwords (Boosting lúc giải mã)")

        # ---- Tab 2: Tu dong am (Homophones) ----
        tab_homo = QWidget()
        homo_layout = QVBoxLayout(tab_homo)
        homo_layout.setContentsMargins(8, 8, 8, 8)
        self._txt_homophones = QTextEdit()
        self._txt_homophones.setPlaceholderText("Wi-Fi : oai phai, quai phai\nYouTube : diu tup, du tup\nLaptop : lap top")
        self._txt_homophones.setMaximumHeight(100)
        self._txt_homophones.setEnabled(False)
        homo_layout.addWidget(self._txt_homophones)

        homo_row = QHBoxLayout()
        self._btn_save_homo = QPushButton("Luu tu dong am")
        self._btn_save_homo.setObjectName("btn_save_hw")
        self._btn_save_homo.setEnabled(False)
        self._btn_save_homo.clicked.connect(self._on_save_homophones)

        self._btn_load_homo = QPushButton("Tai tu file homophones.txt")
        self._btn_load_homo.setEnabled(False)
        self._btn_load_homo.clicked.connect(self._on_load_homophones)

        self._lbl_homo_status = QLabel("")
        self._lbl_homo_status.setWordWrap(True)

        homo_row.addWidget(self._btn_save_homo)
        homo_row.addWidget(self._btn_load_homo)
        homo_row.addWidget(self._lbl_homo_status, stretch=1)
        homo_layout.addLayout(homo_row)
        ctx_tabs.addTab(tab_homo, "Tu dong am / Phien am (Homophones)")

        self._inner_layout.addWidget(ctx_tabs)

    def _build_comparison_section(self):
        self._inner_layout.addWidget(self._section_label("4. Ket qua so sanh"))

        ref_row = QHBoxLayout()
        ref_row.addWidget(QLabel("Reference:"))
        self._txt_ref_display = QLineEdit()
        self._txt_ref_display.setReadOnly(True)
        self._txt_ref_display.setPlaceholderText("(chua co reference)")
        ref_row.addWidget(self._txt_ref_display, stretch=1)
        self._inner_layout.addLayout(ref_row)

        self._btn_compare = QPushButton("Chay so sanh (A vs B)")
        self._btn_compare.setObjectName("btn_compare")
        self._btn_compare.setEnabled(False)
        self._btn_compare.clicked.connect(self._on_run_comparison)
        self._inner_layout.addWidget(self._btn_compare)

        self._lbl_compare_status = QLabel("")
        self._lbl_compare_status.setWordWrap(True)
        self._inner_layout.addWidget(self._lbl_compare_status)

        # 2 panels ket qua
        res_row = QHBoxLayout()

        grp_a = QGroupBox("Pipeline A — Baseline (khong hotwords)")
        grp_a.setObjectName("group_a")
        ga_l = QVBoxLayout(grp_a)
        self._txt_result_a = QTextEdit()
        self._txt_result_a.setReadOnly(True)
        self._txt_result_a.setMaximumHeight(90)
        self._lbl_metric_a = QLabel("")
        self._lbl_metric_a.setStyleSheet("color:#555; font-size:12px;")
        ga_l.addWidget(self._txt_result_a)
        ga_l.addWidget(self._lbl_metric_a)

        grp_b = QGroupBox("Pipeline B — Context-aware (co hotwords)")
        grp_b.setObjectName("group_b")
        gb_l = QVBoxLayout(grp_b)
        self._txt_result_b = QTextEdit()
        self._txt_result_b.setReadOnly(True)
        self._txt_result_b.setMaximumHeight(90)
        self._lbl_metric_b = QLabel("")
        self._lbl_metric_b.setStyleSheet("color:#555; font-size:12px;")
        gb_l.addWidget(self._txt_result_b)
        gb_l.addWidget(self._lbl_metric_b)

        res_row.addWidget(grp_a)
        res_row.addWidget(grp_b)
        self._inner_layout.addLayout(res_row)

    def _build_history_section(self):
        self._inner_layout.addWidget(self._section_label("5. Lich su ket qua trong phien"))
        self._history_table = QTableWidget(0, len(DATAFRAME_HEADERS))
        self._history_table.setHorizontalHeaderLabels(DATAFRAME_HEADERS)
        self._history_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._history_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._history_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._history_table.setAlternatingRowColors(True)
        self._history_table.setMinimumHeight(150)
        self._inner_layout.addWidget(self._history_table)

    def _build_export_section(self):
        self._inner_layout.addWidget(self._section_label("6. Xuat ket qua"))
        exp_row = QHBoxLayout()
        self._btn_export = QPushButton("Xuat ket qua ra file .md")
        self._btn_export.setObjectName("btn_export")
        self._btn_export.setEnabled(False)
        self._btn_export.clicked.connect(self._on_export_markdown)

        self._lbl_export_status = QLineEdit()
        self._lbl_export_status.setReadOnly(True)
        self._lbl_export_status.setPlaceholderText("Duong dan file sau khi xuat...")

        exp_row.addWidget(self._btn_export)
        exp_row.addWidget(self._lbl_export_status, stretch=3)
        self._inner_layout.addLayout(exp_row)

    # -----------------------------------------------------------------------
    # Enable / disable tat ca widget can khoa khi chua load model
    # (tuong duong _all_interactive() + 13 component cua Gradio version)
    # -----------------------------------------------------------------------
    def _set_all_enabled(self, enabled: bool):
        for w in [
            self._txt_tts_input, self._btn_random, self._btn_gen_tts,
            self._btn_choose_file, self._txt_file_ref, self._btn_use_file,
            self._btn_start_rec, self._txt_mic_ref, self._btn_use_mic,
            self._txt_esp_ref,
            self._txt_hotwords, self._btn_save_hw, self._btn_load_hw,
            self._txt_homophones, self._btn_save_homo, self._btn_load_homo,
            self._btn_compare,
        ]:
            w.setEnabled(enabled)
        if hasattr(self, "_esp32_mic") and self._esp32_mic and self._esp32_mic.is_connected() and not self._esp32_mic.is_recording():
            self._btn_start_esp.setEnabled(enabled)
        self._btn_export.setEnabled(enabled)

    # -----------------------------------------------------------------------
    # Poll QTimer slot (tuong duong handle_poll_status cua Gradio version)
    # -----------------------------------------------------------------------
    @Slot()
    def _poll_model_status(self):
        loaded = stt.is_loaded()
        status_text = stt.get_status()

        if loaded and tts_eng.is_tts_loaded():
            status_text += " | TTS (VieNeu) da san sang"
        elif loaded:
            tts_err = tts_eng.get_tts_error()
            if tts_err:
                status_text += f" | TTS chua san sang: {tts_err[:60]}"
            else:
                status_text += " | TTS dang load..."

        color = "#2ecc71" if loaded else "#e67e22"
        self._lbl_status.setStyleSheet(
            f"padding:6px 12px; border-radius:6px; font-weight:bold; "
            f"color:white; background:{color};"
        )
        self._lbl_status.setText(status_text)
        self._btn_load.setEnabled(not loaded)

        self._set_all_enabled(loaded)

        if loaded and (tts_eng.is_tts_loaded() or bool(tts_eng.get_tts_error())):
            self._poll_timer.stop()

    # -----------------------------------------------------------------------
    # Handler: Load Model (giu nguyen _load_thread logic)
    # -----------------------------------------------------------------------
    @Slot()
    def _on_load_model(self):
        if stt.is_loaded() and tts_eng.is_tts_loaded():
            self._poll_model_status()
            return
        self._btn_load.setEnabled(False)
        self._lbl_status.setText("Dang load model, vui long cho...")
        self._lbl_status.setStyleSheet(
            "padding:6px 12px; border-radius:6px; font-weight:bold; color:white; background:#e67e22;")

        def _load_thread():
            try:
                if not stt.is_loaded():
                    stt.load_models()
                if not tts_eng.is_tts_loaded():
                    try:
                        tts_eng.load_tts()
                    except Exception as e:
                        print(f"[CANH BAO] Load TTS that bai: {e}")
            except Exception as e:
                print(f"[LOI] Load model that bai: {e}")

        t = threading.Thread(target=_load_thread, daemon=True)
        t.start()
        self._poll_timer.start()

    # -----------------------------------------------------------------------
    # Handler: TTS tab
    # -----------------------------------------------------------------------
    @Slot()
    def _on_random_sentence(self):
        self._txt_tts_input.setPlainText(random.choice(SAMPLE_SENTENCES))

    @Slot()
    def _on_generate_tts(self):
        text = self._txt_tts_input.toPlainText().strip()
        if not text:
            self._lbl_tts_status.setText("Vui long nhap van ban truoc khi tao TTS.")
            return
        if not stt.is_loaded():
            self._lbl_tts_status.setText("Model chua load!")
            return

        self._btn_gen_tts.setEnabled(False)
        self._lbl_tts_status.setText("Dang tao TTS...")

        self._tts_thread = QThread()
        worker = TTSWorker(text)
        worker.moveToThread(self._tts_thread)
        self._tts_thread.started.connect(worker.run)
        worker.finished.connect(self._on_tts_done)
        worker.error.connect(self._on_tts_error)
        worker.finished.connect(self._tts_thread.quit)
        worker.error.connect(self._tts_thread.quit)
        self._tts_thread.start()
        self._tts_worker_ref = worker   # giu ref tranh GC

    @Slot(object, str, str)
    def _on_tts_done(self, samples, text, status):
        _set_current_audio(samples, "TTS", text)
        self._lbl_tts_status.setText(status)
        self._txt_tts_ref.setText(text)
        self._txt_ref_display.setText(text)
        self._btn_gen_tts.setEnabled(True)
        self._btn_play_tts.setEnabled(True)

    @Slot(str)
    def _on_tts_error(self, msg):
        self._lbl_tts_status.setText(msg)
        self._btn_gen_tts.setEnabled(True)

    @Slot()
    def _on_play_audio(self):
        samples, source, _ = _get_current_audio()
        if samples is None or len(samples) == 0:
            print("[DEBUG] Khong co audio de play.")
            return
        try:
            import sounddevice as sd
            max_val = np.max(np.abs(samples)) if len(samples) > 0 else 0
            print(f"[DEBUG] Dang play audio tu {source}, max_amp={max_val:.4f}")
            
            # Neu am luong qua nho (thuong la tu mic), tang am luong len
            play_samples = samples.copy()
            if max_val > 0 and max_val < 0.5:
                gain = min(0.8 / max_val, 10.0)
                play_samples = play_samples * gain
                
            sd.play(play_samples, samplerate=16000)
        except Exception as e:
            print(f"[ERROR] Loi phat am: {e}")
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Loi Phat Audio", f"Khong the phat audio: {e}\n\nBan can cai hoac kiem tra sounddevice.")

    # -----------------------------------------------------------------------
    # Handler: File tab
    # -----------------------------------------------------------------------
    @Slot()
    def _on_choose_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Chon file audio", "",
            "Audio Files (*.wav *.mp3 *.flac *.ogg *.m4a);;All Files (*)"
        )
        if path:
            self._lbl_file_path.setText(path)
            self._lbl_file_status.setText(f"Da chon: {Path(path).name}. Bam nut 'Dung audio nay de so sanh' de xac nhan.")

    @Slot()
    def _on_use_file(self):
        path = self._lbl_file_path.text().strip()
        if not path:
            self._lbl_file_status.setText("Chua chon file audio.")
            return
        try:
            samples = au.load_wav_file(path)
            ref     = self._txt_file_ref.text().strip()
            _set_current_audio(samples, "File", ref)
            dur     = len(samples) / 16000.0
            self._lbl_file_status.setText(f"Da load audio ({dur:.1f}s). San sang so sanh.")
            self._txt_ref_display.setText(ref)
            self._btn_play_file.setEnabled(True)
        except Exception as e:
            self._lbl_file_status.setText(f"Loi xu ly file: {e}")

    # -----------------------------------------------------------------------
    # Handler: Mic tab
    # -----------------------------------------------------------------------
    @Slot()
    def _on_start_rec(self):
        try:
            self._mic.start(samplerate=16000, channels=1)
            self._btn_start_rec.setEnabled(False)
            self._btn_stop_rec.setEnabled(True)
            self._btn_use_mic.setEnabled(False)            self._btn_use_mic.setEnabled(False)
            self._lbl_rec_status.setText("\U0001f534 Dang ghi am... (bam 'Dung ghi am' khi xong)")
        except Exception as e:
            self._lbl_rec_status.setText(f"Loi ghi am: {e}")

    @Slot()
    def _on_stop_rec(self):
        samples = self._mic.stop()
        self._btn_start_rec.setEnabled(True)
        self._btn_stop_rec.setEnabled(False)
        if samples is None or len(samples) == 0:
            self._lbl_rec_status.setText("Khong co du lieu ghi am. Thu lai.")
            return
        dur = len(samples) / 16000.0
        ref = self._txt_mic_ref.text().strip()
        _set_current_audio(samples, "Mic", ref)
        self._txt_ref_display.setText(ref)
        self._lbl_rec_status.setText(f"Da ghi am ({dur:.1f}s). San sang so sanh.")
        self._btn_use_mic.setEnabled(True)
        self._btn_play_mic.setEnabled(True)

    @Slot()
    def _on_use_mic(self):
        # Neu da stop roi, _current_audio da duoc set o _on_stop_rec
        samples, source, _ = _get_current_audio()
        if source != "Mic" or samples is None or len(samples) == 0:
            self._lbl_rec_status.setText("Chua co audio ghi am. Vui long ghi am truoc.")

    # -----------------------------------------------------------------------
    # Handler: ESP32 tab
    # -----------------------------------------------------------------------
    @Slot()
    def _on_esp_connect(self):
        if self._esp32_mic and self._esp32_mic.is_connected():
            self._esp32_mic.disconnect()
            self._btn_esp_connect.setText("Ket noi ESP32")
            self._lbl_esp_conn_status.setText("Chua ket noi")
            self._lbl_esp_conn_status.setStyleSheet("color:#e74c3c; font-weight:bold;")
            self._btn_start_esp.setEnabled(False)
            self._btn_stop_esp.setEnabled(False)
            return

        port = self._txt_esp_port.text().strip()
        baud_str = self._txt_esp_baud.text().strip()
        baud = int(baud_str) if baud_str.isdigit() else 2000000
        try:
            self._esp32_mic.connect(port=port, baudrate=baud)
            self._btn_esp_connect.setText("Ngat ket noi")
            self._lbl_esp_conn_status.setText(f"Da ket noi ({port})")
            self._lbl_esp_conn_status.setStyleSheet("color:#2ecc71; font-weight:bold;")
            self._btn_start_esp.setEnabled(stt.is_loaded())
        except Exception as e:
            self._lbl_esp_conn_status.setText(f"Loi: {e}")
            self._lbl_esp_conn_status.setStyleSheet("color:#e74c3c; font-weight:bold;")

    @Slot()
    def _on_start_esp(self):
        try:
            self._esp32_mic.start()
            self._btn_start_esp.setEnabled(False)
            self._btn_stop_esp.setEnabled(True)
            self._btn_use_esp.setEnabled(False)
            self._lbl_esp_rec_status.setText("Dang ghi am tu ESP32... (bam 'Dung ghi am' khi xong)")
        except Exception as e:
            self._lbl_esp_rec_status.setText(f"Loi ghi am: {e}")

    @Slot()
    def _on_stop_esp(self):
        self._lbl_esp_rec_status.setText("Dang xu ly audio...")
        QApplication.processEvents()
        samples = self._esp32_mic.stop()
        self._btn_start_esp.setEnabled(True)
        self._btn_stop_esp.setEnabled(False)
        if samples is None or len(samples) == 0:
            self._lbl_esp_rec_status.setText("Khong co du lieu ghi am. Thu lai.")
            return
        dur = len(samples) / 16000.0
        ref = self._txt_esp_ref.text().strip()
        _set_current_audio(samples, "ESP32", ref)
        self._txt_ref_display.setText(ref)
        self._lbl_esp_rec_status.setText(f"Da ghi am ESP32 ({dur:.1f}s). San sang so sanh.")
        self._btn_use_esp.setEnabled(True)
        self._btn_play_esp.setEnabled(True)

    @Slot()
    def _on_use_esp(self):
        samples, source, _ = _get_current_audio()
        if source != "ESP32" or samples is None or len(samples) == 0:
            self._lbl_esp_rec_status.setText("Chua co audio ESP32. Vui long ghi am truoc.")
        else:
            ref = self._txt_esp_ref.text().strip()
            _set_current_audio(samples, "ESP32", ref)
            self._txt_ref_display.setText(ref)
            self._lbl_esp_rec_status.setText("Da chon audio ESP32 de so sanh.")

    # -----------------------------------------------------------------------
    # Handler: Hotwords
    # -----------------------------------------------------------------------
    @Slot()
    def _on_save_hotwords(self):
        text = self._txt_hotwords.toPlainText()
        msg  = _handle_save_hotwords(text)
        self._lbl_hw_status.setText(msg)

    @Slot()
    def _on_load_hotwords(self):
        self._txt_hotwords.setPlainText(_handle_load_hotwords_file())
        self._lbl_hw_status.setText("Da tai hotwords tu file.")

    @Slot()
    def _on_save_homophones(self):
        text = self._txt_homophones.toPlainText()
        msg  = hm.save_and_reload(text)
        self._lbl_homo_status.setText(msg)

    @Slot()
    def _on_load_homophones(self):
        self._txt_homophones.setPlainText(hm.get_raw_text())
        self._lbl_homo_status.setText("Da tai tu dong am tu file homophones.txt.")

    # -----------------------------------------------------------------------
    # Handler: Chay so sanh (STT)
    # -----------------------------------------------------------------------
    @Slot()
    def _on_run_comparison(self):
        samples, source, reference = _get_current_audio()
        if samples is None or len(samples) == 0:
            self._lbl_compare_status.setText("Chua co audio de so sanh. Vui long chon audio truoc.")
            return
        if not stt.is_loaded():
            self._lbl_compare_status.setText("Model chua load!")
            return

        self._btn_compare.setEnabled(False)
        self._lbl_compare_status.setText("Dang chay STT...")

        self._stt_thread = QThread()
        worker = STTWorker(samples, source, reference)
        worker.moveToThread(self._stt_thread)
        self._stt_thread.started.connect(worker.run)
        worker.finished.connect(self._on_stt_done)
        worker.error.connect(self._on_stt_error)
        worker.finished.connect(self._stt_thread.quit)
        worker.error.connect(self._stt_thread.quit)
        self._stt_thread.start()
        self._stt_worker_ref = worker

    @Slot(str, str, str, str, str)
    def _on_stt_done(self, status, text_a, metric_a, text_b, metric_b):
        self._lbl_compare_status.setText(status)
        self._txt_result_a.setPlainText(text_a)
        self._lbl_metric_a.setText(metric_a)
        self._txt_result_b.setPlainText(text_b)
        self._lbl_metric_b.setText(metric_b)
        self._btn_compare.setEnabled(True)
        self._refresh_history_table()

    @Slot(str)
    def _on_stt_error(self, msg):
        self._lbl_compare_status.setText(msg)
        self._btn_compare.setEnabled(True)

    # -----------------------------------------------------------------------
    # Lam moi bang lich su (tuong duong get_history_table_update())
    # -----------------------------------------------------------------------
    def _refresh_history_table(self):
        rows = rl.get_history_as_table()
        self._history_table.setRowCount(len(rows))
        for r_idx, row in enumerate(rows):
            for c_idx, val in enumerate(row):
                item = QTableWidgetItem(str(val) if val is not None else "")
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self._history_table.setItem(r_idx, c_idx, item)
        self._history_table.scrollToBottom()

    # -----------------------------------------------------------------------
    # Handler: Xuat Markdown
    # -----------------------------------------------------------------------
    @Slot()
    def _on_export_markdown(self):
        history = rl.get_history()
        if not history:
            self._lbl_export_status.setText("Chua co ket qua nao de xuat.")
            return
        try:
            path = rl.export_markdown()
            self._lbl_export_status.setText(path)
        except Exception as e:
            self._lbl_export_status.setText(f"Loi khi xuat file: {e}")

    # -----------------------------------------------------------------------
    # Dong app sach se
    # -----------------------------------------------------------------------
    def closeEvent(self, event):
        # Dung ghi am neu dang chay
        if self._mic.is_recording():
            self._mic.discard()
        if self._esp32_mic and self._esp32_mic.is_recording():
            self._esp32_mic.discard()
        if self._esp32_mic and self._esp32_mic.is_connected():
            self._esp32_mic.disconnect()
        # Dung poll timer
        self._poll_timer.stop()
        # Dung cac QThread dang chay
        for t in [self._stt_thread, self._tts_thread]:
            if t is not None and t.isRunning():
                t.quit()
                t.wait(2000)
        super().closeEvent(event)


# ===========================================================================
# Main
# ===========================================================================
if __name__ == "__main__":
    print("=== STT Comparison App (PySide6 Desktop) ===")
    print(f"Session JSON : {rl.get_session_files()['json']}")
    print(f"Session CSV  : {rl.get_session_files()['csv']}")

    app = QApplication(sys.argv)
    app.setApplicationName("STT Comparison")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
