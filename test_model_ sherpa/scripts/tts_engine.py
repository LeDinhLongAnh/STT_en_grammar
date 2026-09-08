#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tts_engine.py
-------------
Wrapper goi VieNeu-TTS (v3turbo, CPU/ONNX mode) de sinh audio tieng Viet.

API chinh:
  - load_tts()           : Load model VieNeu TTS (goi 1 lan, giu trong bo nho)
  - generate_tts_audio(text) -> np.ndarray  : Sinh audio float32 16kHz mono
  - is_tts_loaded() -> bool

Luu y:
  - VieNeu-TTS v3turbo output 48kHz. Ham nay tu dong resample ve 16kHz
    de co the dung truc tiep voi sherpa-onnx.
  - Neu VieNeu-TTS chua cai dat, ham tra ve mang rong va log canh bao.
"""

from __future__ import annotations

import os
import sys
import threading
import numpy as np
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Duong dan toi thu muc src cua VieNeu-TTS (chinh sua neu can)
# ---------------------------------------------------------------------------
VIENEU_SRC_PATH = r"D:\esp\Test_Model\Test_Model\models\VieNeu-TTS\src"

# Sample rate dau ra cua VieNeu-TTS v3turbo
VIENEU_SR = 48_000
# Sample rate yeu cau cua STT (sherpa-onnx)
TARGET_SR = 16_000


# ---------------------------------------------------------------------------
# Trang thai noi bo
# ---------------------------------------------------------------------------
_tts_instance = None
_tts_voices: list[tuple[str, str]] = []   # [(label, voice_id), ...]
_tts_lock = threading.Lock()
_tts_loaded = False
_tts_error  = ""


# ---------------------------------------------------------------------------
# Ham load VieNeu-TTS (thread-safe, idempotent)
# ---------------------------------------------------------------------------
def load_tts() -> None:
    """Load VieNeu-TTS v3turbo.

    Them VIENEU_SRC_PATH vao sys.path truoc khi import.
    Nen goi trong thread rieng de khong block UI.
    """
    global _tts_instance, _tts_voices, _tts_loaded, _tts_error
    with _tts_lock:
        if _tts_loaded:
            return
        _tts_error = ""

    try:
        # Them duong dan src vao sys.path de import duoc vieneu
        if VIENEU_SRC_PATH not in sys.path:
            sys.path.insert(0, VIENEU_SRC_PATH)

        from vieneu import Vieneu

        # Khoi tao v3turbo (CPU mode dung ONNX, khong can GPU)
        tts = Vieneu(mode="v3turbo")

        # Doc danh sach giong doc co san
        try:
            preset_voices = tts.list_preset_voices()
            voices = preset_voices
        except Exception:
            voices = []

        with _tts_lock:
            _tts_instance = tts
            _tts_voices   = voices
            _tts_loaded   = True

    except ImportError as e:
        _tts_error = (
            f"Khong the import VieNeu-TTS: {e}. "
            "Kiem tra lai VIENEU_SRC_PATH trong tts_engine.py."
        )
        raise RuntimeError(_tts_error) from e
    except Exception as e:
        _tts_error = str(e)
        raise RuntimeError(f"Load VieNeu-TTS that bai: {e}") from e


# ---------------------------------------------------------------------------
# Kiem tra trang thai
# ---------------------------------------------------------------------------
def is_tts_loaded() -> bool:
    with _tts_lock:
        return _tts_loaded


def get_tts_error() -> str:
    with _tts_lock:
        return _tts_error


def list_tts_voices() -> list[tuple[str, str]]:
    """Tra ve danh sach [(label, voice_id)] cua cac giong doc co san."""
    with _tts_lock:
        return list(_tts_voices)


# ---------------------------------------------------------------------------
# Ham chinh: sinh audio tu text
# ---------------------------------------------------------------------------
def generate_tts_audio(text: str, voice: Optional[str] = None) -> np.ndarray:
    """Sinh audio tieng Viet tu `text` dung VieNeu-TTS, resample ve 16kHz mono.

    Args:
        text  : Chuoi van ban tieng Viet.
        voice : Ten giong doc (label hoac voice_id). None de dung giong mac dinh.

    Returns:
        np.ndarray float32 16kHz mono.

    Raises:
        RuntimeError : Neu TTS chua load hoac sinh am loi.
    """
    if not is_tts_loaded():
        raise RuntimeError(
            "VieNeu-TTS chua duoc load. Vui long doi model load xong."
        )
    if not text or not text.strip():
        raise ValueError("Van ban TTS khong duoc de trong.")

    import scipy.signal

    with _tts_lock:
        tts = _tts_instance
        voices = _tts_voices

    try:
        # Chon giong doc
        if voice and voices:
            # voices la list [(label, vid)] hoac [(desc, name)] tuy phien ban VieNeu
            voice_data = None
            for entry in voices:
                # entry co the la tuple (label, vid) hoac (desc, name)
                label = entry[0] if isinstance(entry, (tuple, list)) else str(entry)
                vid   = entry[1] if isinstance(entry, (tuple, list)) else str(entry)
                if voice in (label, vid):
                    try:
                        voice_data = tts.get_preset_voice(vid)
                    except Exception:
                        pass
                    break
            if voice_data is not None:
                audio = tts.infer(text, voice=voice_data)
            else:
                audio = tts.infer(text)
        else:
            # Dung giong mac dinh (VieNeu v3turbo co built-in default speaker)
            audio = tts.infer(text)

    except Exception as e:
        raise RuntimeError(f"VieNeu-TTS sinh am that bai: {e}") from e

    # VieNeu-TTS v3turbo out 48kHz -> resample ve 16kHz
    from math import gcd
    g = gcd(TARGET_SR, VIENEU_SR)
    up   = TARGET_SR // g
    down = VIENEU_SR // g
    audio_mono = audio.flatten().astype(np.float32)
    resampled = scipy.signal.resample_poly(audio_mono, up=up, down=down)
    return resampled.astype(np.float32)
