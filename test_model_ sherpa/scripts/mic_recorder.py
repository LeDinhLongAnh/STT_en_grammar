#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# mic_recorder.py
# Ghi am tu microphone khong block UI thread, dung sounddevice.InputStream.
from __future__ import annotations
import threading
import numpy as np

try:
    import sounddevice as sd
    _SD_AVAILABLE = True
except ImportError:
    _SD_AVAILABLE = False


class MicRecorder:
    """Ghi am tu microphone. start() bat dau, stop() tra ve np.ndarray float32 mono 16kHz."""

    def __init__(self):
        self._buffer: list[np.ndarray] = []
        self._lock    = threading.Lock()
        self._stream  = None
        self._recording = False
        self._samplerate = 16000
        self._channels   = 1

    def start(self, samplerate: int = 16000, channels: int = 1) -> None:
        """Bat dau ghi am. Goi stop() sau do de lay audio."""
        if not _SD_AVAILABLE:
            raise RuntimeError("Chua cai sounddevice. Chay: pip install sounddevice")
        if self._recording:
            return
        self._samplerate = samplerate
        self._channels   = channels
        self._buffer     = []

        def _callback(indata, frames, time_info, status):
            if status:
                print(f"[MicRecorder] {status}")
            with self._lock:
                self._buffer.append(indata.copy())

        self._stream = sd.InputStream(
            samplerate=samplerate, channels=channels,
            dtype="float32", callback=_callback, blocksize=1024,
        )
        self._stream.start()
        self._recording = True

    def stop(self) -> np.ndarray:
        """Dung ghi am, tra ve mang float32 mono 16kHz. Mang rong neu chua ghi gi."""
        if not self._recording:
            return np.array([], dtype=np.float32)
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        self._recording = False
        with self._lock:
            buf = list(self._buffer)
            self._buffer = []
        if not buf:
            return np.array([], dtype=np.float32)
        audio = np.concatenate(buf, axis=0)
        if audio.ndim == 2:
            audio = audio.mean(axis=1)
        return audio.astype(np.float32)

    def is_recording(self) -> bool:
        return self._recording

    def discard(self) -> None:
        """Huy ghi am khong can lay du lieu (goi khi dong app giua chung)."""
        if self._recording:
            try:
                if self._stream is not None:
                    self._stream.stop()
                    self._stream.close()
            except Exception:
                pass
            self._stream    = None
            self._recording = False
            with self._lock:
                self._buffer = []
