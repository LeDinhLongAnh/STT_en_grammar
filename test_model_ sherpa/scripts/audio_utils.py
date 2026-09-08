#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
audio_utils.py
--------------
Tien ich doc/ghi va chuan hoa audio ve 16 kHz mono cho STT.

Cac ham chinh:
- load_audio_file(path)         : Doc file .wav/.mp3/... -> (samples_float32, sample_rate)
- resample_to_16k(samples, sr)  : Resample ve 16 kHz mono
- normalize_audio_file(path)    : All-in-one: doc + resample -> np.ndarray float32 16kHz mono
- normalize_audio_from_gradio() : Xu ly input tu Gradio Audio component
- save_wav(path, samples, sr)   : Ghi array ra file .wav
- samples_to_gradio(samples,sr) : Chuyen thanh tuple (sr, int16) cho gr.Audio playback
"""

from __future__ import annotations

import io
import os
import numpy as np
import scipy.signal
import soundfile as sf


# ---------------------------------------------------------------------------
# Hang so cau hinh
# ---------------------------------------------------------------------------
TARGET_SR = 16_000      # Sample rate yeu cau boi sherpa-onnx
TARGET_CHANNELS = 1     # Mono


# ---------------------------------------------------------------------------
# Doc audio tu file path hoac bytes
# ---------------------------------------------------------------------------
def load_audio_file(path: str | os.PathLike) -> tuple[np.ndarray, int]:
    """Doc bat ky file audio nao duoc soundfile ho tro.

    Tra ve:
        samples : np.ndarray float32, shape (N,) neu mono hoac (N, C) neu stereo
        sr      : sample rate goc
    """
    data, sr = sf.read(str(path), dtype="float32", always_2d=False)
    return data, sr


# ---------------------------------------------------------------------------
# Chuyen thanh mono
# ---------------------------------------------------------------------------
def to_mono(samples: np.ndarray) -> np.ndarray:
    """Neu stereo (N, C), trung binh cac kenh -> mono (N,)."""
    if samples.ndim == 2:
        samples = samples.mean(axis=1)
    return samples.astype(np.float32)


# ---------------------------------------------------------------------------
# Resample
# ---------------------------------------------------------------------------
def resample_to_16k(samples: np.ndarray, orig_sr: int) -> np.ndarray:
    """Resample samples float32 tu orig_sr ve 16000 Hz dung scipy.signal.resample_poly.

    Tu dong xu ly truong hop da dung 16kHz (return thang).
    """
    samples = to_mono(samples)
    if orig_sr == TARGET_SR:
        return samples

    from math import gcd
    g = gcd(TARGET_SR, orig_sr)
    up = TARGET_SR // g
    down = orig_sr // g

    resampled = scipy.signal.resample_poly(samples, up=up, down=down)
    return resampled.astype(np.float32)


# ---------------------------------------------------------------------------
# All-in-one: doc file -> float32 16kHz mono
# ---------------------------------------------------------------------------
def normalize_audio_file(path: str | os.PathLike) -> np.ndarray:
    """Doc file audio va tra ve float32 16kHz mono, san sang nap vao sherpa-onnx.

    Raises:
        FileNotFoundError : Neu file khong ton tai.
        RuntimeError      : Neu khong doc duoc file.
    """
    path = str(path)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Khong tim thay file audio: {path}")
    try:
        samples, sr = load_audio_file(path)
    except Exception as e:
        raise RuntimeError(f"Khong the doc file audio '{path}': {e}") from e
    return resample_to_16k(samples, sr)


def normalize_audio_from_gradio(audio_input) -> np.ndarray:
    """Nhan gia tri tu gr.Audio component (tuple hoac path) va tra ve float32 16kHz mono.

    Gradio Audio component co the tra ve:
    - Tuple (sample_rate, np.ndarray) voi dtype int16 hoac float32
    - str (duong dan file tam)
    - None (neu chua co input)
    """
    if audio_input is None:
        raise ValueError("Chua co audio dau vao. Vui long upload file hoac ghi am.")

    # Gradio thuong tra ve (sample_rate, np.ndarray)
    if isinstance(audio_input, tuple):
        sr, samples = audio_input
        samples = samples.astype(np.float32)
        # int16 range: -32768 to 32767 => normalize ve [-1, 1]
        if samples.max() > 1.0 or samples.min() < -1.0:
            samples = samples / 32768.0
        return resample_to_16k(samples, sr)

    # Neu la duong dan file
    if isinstance(audio_input, (str, os.PathLike)):
        return normalize_audio_file(audio_input)

    raise TypeError(f"Dinh dang audio khong duoc ho tro: {type(audio_input)}")


# ---------------------------------------------------------------------------
# Ghi file .wav
# ---------------------------------------------------------------------------
def save_wav(path: str | os.PathLike, samples: np.ndarray, sr: int = TARGET_SR) -> str:
    """Ghi np.ndarray float32 ra file .wav. Tra ve duong dan file da ghi."""
    path = str(path)
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    sf.write(path, samples.astype(np.float32), samplerate=sr)
    return path


def samples_to_gradio(samples: np.ndarray, sr: int = TARGET_SR) -> tuple[int, np.ndarray]:
    """Chuyen np.ndarray float32 thanh tuple (sr, int16) de truyen cho gr.Audio playback."""
    int16 = (samples * 32767.0).clip(-32768, 32767).astype(np.int16)
    return sr, int16


def load_wav_file(path: str) -> np.ndarray:
    """Doc file audio bat ky (wav/mp3/flac) tu duong dan, tra ve float32 16kHz mono.
    Day la ham tien ich moi cho tab File cua desktop app (PySide6),
    tuong duong normalize_audio_file() nhung ten ro hon.
    """
    return normalize_audio_file(path)
