# -*- coding: utf-8 -*-
"""TTS Engine wrapper for VieNeu."""

import sys
import threading
import torch # Fix for OpenMP/C10 DLLs loading before onnxruntime on Windows
import numpy as np
import scipy.signal
from pathlib import Path
from typing import Optional, Tuple, List
from PyQt5.QtCore import QThread, pyqtSignal

# Reuse path config
VIENEU_SRC_PATH = r"D:\esp\Test_Model\Test_Model\models\VieNeu-TTS\src"

class TTSEngine:
    _instance: Optional["TTSEngine"] = None
    _lock = threading.Lock()

    def __init__(self):
        self.tts = None
        self.voices = []
        self._voice_ids = {}
        self._init_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "TTSEngine":
        with cls._lock:
            if cls._instance is None:
                cls._instance = TTSEngine()
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
                    self.voices = ["Default"]

    def synthesize(self, text: str, voice: Optional[str] = None, speed: float = 1.0) -> Tuple[np.ndarray, float]:
        self.ensure_loaded()
        with self._init_lock:
            actual_voice_id = self._voice_ids.get(voice, voice) if voice else None
            
            # The Vieneu API does not directly support speed parameter in infer(),
            # but we can simulate it with librosa or scipy if strictly needed.
            # For now, we will pass it if it supports it, else ignore.
            if actual_voice_id:
                audio = self.tts.infer(text, voice=actual_voice_id)
            else:
                audio = self.tts.infer(text)
                
        original_sr = 48000
        target_sr = 16000
        samples = scipy.signal.resample_poly(audio, up=target_sr, down=original_sr).astype(np.float32)
        
        # Simple speed adjustment by resampling (changes pitch too, but ok for basic STT testing)
        if speed != 1.0:
            samples = scipy.signal.resample(samples, int(len(samples) / speed)).astype(np.float32)
            
        duration = len(samples) / float(target_sr)
        return samples, duration


class TTSWorker(QThread):
    progress = pyqtSignal(str)
    completed = pyqtSignal(object, float, str)  # (samples, duration, voice)
    failed = pyqtSignal(str)

    def __init__(self, text: str, voice: str, speed: float = 1.0, parent=None):
        super().__init__(parent)
        self.text = text
        self.voice = voice
        self.speed = speed

    def run(self):
        try:
            self.progress.emit(f"Sinh TTS ({self.voice}, {self.speed}x): {self.text[:30]}...")
            engine = TTSEngine.get_instance()
            samples, duration = engine.synthesize(self.text, self.voice, self.speed)
            self.completed.emit(samples, duration, self.voice)
        except Exception as exc:
            import traceback
            traceback.print_exc()
            self.failed.emit(str(exc))
