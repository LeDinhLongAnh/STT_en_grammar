#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TTS Helper engines for Whisper (Kokoro - English) and Sherpa VI (VieNeu-TTS - Vietnamese)."""

from __future__ import annotations

import os
import sys
import threading
import torch  # Ensure OpenMP/C10 DLLs are loaded before onnxruntime on Windows
import numpy as np
import scipy.signal
from pathlib import Path
from typing import Optional, Tuple
from PyQt5.QtCore import QThread, pyqtSignal

# ---------------------------------------------------------------------------
# Path configurations
# ---------------------------------------------------------------------------
KOKORO_MODEL_PATH = r"D:\esp\Test_Model\Test_Model\models\kokoro\kokoro-v1.0.int8.onnx"
KOKORO_VOICES_PATH = r"D:\esp\Test_Model\Test_Model\models\kokoro\voices.bin"
VIENEU_SRC_PATH = r"D:\esp\Test_Model\Test_Model\models\VieNeu-TTS\src"

# ---------------------------------------------------------------------------
# Kokoro Engine (English for Whisper)
# ---------------------------------------------------------------------------
class KokoroEngine:
    _instance: Optional["KokoroEngine"] = None
    _lock = threading.Lock()

    def __init__(self):
        self.model = None
        self.voices = []
        self._init_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "KokoroEngine":
        with cls._lock:
            if cls._instance is None:
                cls._instance = KokoroEngine()
            return cls._instance

    def ensure_loaded(self):
        with self._init_lock:
            if self.model is None:
                from kokoro_onnx import Kokoro
                if not os.path.exists(KOKORO_MODEL_PATH):
                    raise FileNotFoundError(f"Kokoro model not found: {KOKORO_MODEL_PATH}")
                if not os.path.exists(KOKORO_VOICES_PATH):
                    raise FileNotFoundError(f"Kokoro voices not found: {KOKORO_VOICES_PATH}")
                self.model = Kokoro(KOKORO_MODEL_PATH, KOKORO_VOICES_PATH)
                try:
                    self.voices = list(self.model.get_voices())
                except Exception:
                    self.voices = list(self.model.voices.keys())

    def synthesize(self, text: str, voice: str = "af_heart", speed: float = 1.0) -> Tuple[np.ndarray, float]:
        self.ensure_loaded()
        if not voice or voice not in self.voices:
            voice = self.voices[0] if self.voices else "af_heart"
        with self._init_lock:
            samples, sr = self.model.create(text, voice=voice, speed=speed, lang="en-us")
        if sr != 16000:
            samples = scipy.signal.resample_poly(samples, up=16000, down=sr).astype(np.float32)
        duration = len(samples) / 16000.0
        return samples, duration


class KokoroTTSWorker(QThread):
    progress = pyqtSignal(str)
    completed = pyqtSignal(object, float)  # (np.ndarray samples, float duration)
    failed = pyqtSignal(str)

    def __init__(self, text: str, voice: str = "af_heart", speed: float = 1.0, parent=None):
        super().__init__(parent)
        self.text = text
        self.voice = voice
        self.speed = speed

    def run(self):
        try:
            self.progress.emit(f"Đang sinh âm TTS (Kokoro: {self.text[:30]}...)...")
            engine = KokoroEngine.get_instance()
            samples, duration = engine.synthesize(self.text, self.voice, self.speed)
            self.completed.emit(samples, duration)
        except Exception as exc:
            import traceback
            traceback.print_exc()
            self.failed.emit(str(exc))


# ---------------------------------------------------------------------------
# VieNeu-TTS Engine (Vietnamese for Sherpa)
# ---------------------------------------------------------------------------
class VieNeuEngine:
    _instance: Optional["VieNeuEngine"] = None
    _lock = threading.Lock()

    def __init__(self):
        self.tts = None
        self.voices = []
        self._voice_ids = {}
        self._init_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "VieNeuEngine":
        with cls._lock:
            if cls._instance is None:
                cls._instance = VieNeuEngine()
            return cls._instance

    def ensure_loaded(self):
        with self._init_lock:
            if self.tts is None:
                if VIENEU_SRC_PATH not in sys.path:
                    sys.path.insert(0, VIENEU_SRC_PATH)
                from vieneu import Vieneu
                self.tts = Vieneu()
                try:
                    preset_voices = self.tts.list_preset_voices()
                    self.voices = [label for label, vid in preset_voices]
                    self._voice_ids = {label: vid for label, vid in preset_voices}
                except Exception:
                    self.voices = []

    def synthesize(self, text: str, voice: Optional[str] = None) -> Tuple[np.ndarray, float]:
        self.ensure_loaded()
        with self._init_lock:
            actual_voice_id = self._voice_ids.get(voice, voice) if voice else None
            if actual_voice_id:
                audio = self.tts.infer(text, voice=actual_voice_id)
            else:
                audio = self.tts.infer(text)
        # Vieneu outputs at 48000 Hz, resample to 16000 Hz for STT
        original_sr = 48000
        target_sr = 16000
        samples = scipy.signal.resample_poly(audio, up=target_sr, down=original_sr).astype(np.float32)
        duration = len(samples) / float(target_sr)
        return samples, duration


class VieNeuTTSWorker(QThread):
    progress = pyqtSignal(str)
    completed = pyqtSignal(object, float)  # (np.ndarray samples, float duration)
    failed = pyqtSignal(str)

    def __init__(self, text: str, voice: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.text = text
        self.voice = voice

    def run(self):
        try:
            self.progress.emit(f"Đang sinh âm TTS (VieNeu: {self.text[:30]}...)...")
            engine = VieNeuEngine.get_instance()
            samples, duration = engine.synthesize(self.text, self.voice)
            self.completed.emit(samples, duration)
        except Exception as exc:
            import traceback
            traceback.print_exc()
            self.failed.emit(str(exc))
